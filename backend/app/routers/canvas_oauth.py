from __future__ import annotations

import html
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import Course
from ..schemas.canvas_oauth import (
    CanvasOAuthConfigurationIn,
    CanvasOAuthConfigurationOut,
    CanvasOAuthDisconnectOut,
    CanvasOAuthStartOut,
    CanvasOAuthStatusOut,
    InstructorCanvasOAuthStatusOut,
)
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_course_route_access,
    require_development_auth,
    require_organization_role,
)
from ..services.canvas_oauth import (
    CanvasCodeExchanger,
    CanvasOAuthError,
    EncryptedSecretStore,
    canvas_oauth_return_url,
    canvas_oauth_status,
    complete_canvas_oauth_callback,
    development_authorization_redirect,
    development_code_exchanger,
    disconnect_canvas_oauth,
    disconnect_instructor_canvas_oauth,
    get_canvas_code_exchanger,
    get_canvas_secret_store,
    instructor_canvas_oauth_status,
    save_canvas_oauth_configuration,
    start_canvas_oauth,
    start_instructor_canvas_oauth,
    validate_development_authorization_request,
)
from ..services.product_session import session_cookie_policy

router = APIRouter(prefix="/integrations/canvas/oauth", tags=["canvas-oauth"])
course_router = APIRouter(tags=["canvas-oauth"])


def _headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }


def _api_error(exc: CanvasOAuthError) -> HTTPException:
    statuses = {
        "configuration_conflict": 409,
        "disconnect_before_configuration_change": 409,
        "oauth_configuration_required": 409,
        "oauth_configuration_mismatch": 409,
        "production_connection_disabled": 409,
        "secret_store_unavailable": 503,
        "frontend_origin_invalid": 503,
    }
    messages = {
        "canvas_api_origin_invalid": "Use one exact HTTPS Canvas API origin.",
        "oauth_client_id_invalid": "Use the exact scoped Developer Key Client ID.",
        "configuration_conflict": "The connection configuration changed. Refresh and retry.",
        "disconnect_before_configuration_change": "Disconnect active users before changing this configuration.",
        "oauth_configuration_required": "Save the non-secret Canvas API configuration first.",
        "oauth_configuration_mismatch": "The configured Canvas origin does not match this course.",
        "production_connection_disabled": "Production Canvas authorization is not enabled.",
        "secret_store_unavailable": "Approved credential custody is unavailable.",
    }
    return HTTPException(
        statuses.get(exc.code, 422),
        {
            "code": exc.code,
            "message": messages.get(
                exc.code, "Canvas connection request was rejected."
            ),
        },
    )


def _admin_user(db: Session, principal: Principal, organization_id: int) -> int:
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    if principal.user_id is None:
        raise HTTPException(401, "authenticated user required")
    return principal.user_id


def _instructor_handoff_context(
    request: Request,
    db: Session,
    principal: Principal,
    course_id: int,
) -> tuple[int, int, int, int, str | None]:
    if (
        principal.auth_mode != "lti_session"
        or principal.user_id is None
        or principal.session_id is None
        or principal.registration_id is None
        or principal.course_scope_id != course_id
    ):
        raise HTTPException(404, "resource not found")
    course = db.get(Course, course_id)
    if course is None or course.organization_id is None:
        raise HTTPException(404, "resource not found")
    raw_session = request.cookies.get(session_cookie_policy().name)
    return (
        course.organization_id,
        principal.registration_id,
        principal.user_id,
        principal.session_id,
        raw_session,
    )


@course_router.get(
    "/courses/{course_id}/canvas-oauth-handoff",
    response_model=InstructorCanvasOAuthStatusOut,
)
def instructor_canvas_connection_status(
    course_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_course_route_access),
    store: EncryptedSecretStore = Depends(get_canvas_secret_store),
):
    response.headers.update(_headers())
    organization_id, registration_id, user_id, session_id, raw_session = (
        _instructor_handoff_context(request, db, principal, course_id)
    )
    try:
        return instructor_canvas_oauth_status(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
            product_session_id=session_id,
            course_id=course_id,
            raw_session_token=raw_session,
            store=store,
        )
    except CanvasOAuthError as exc:
        if exc.code == "instructor_handoff_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@course_router.post(
    "/courses/{course_id}/canvas-oauth-handoff/start",
    response_model=CanvasOAuthStartOut,
)
def start_instructor_canvas_connection(
    course_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_course_route_access),
):
    response.headers.update(_headers())
    organization_id, registration_id, user_id, session_id, raw_session = (
        _instructor_handoff_context(request, db, principal, course_id)
    )
    try:
        return start_instructor_canvas_oauth(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
            product_session_id=session_id,
            course_id=course_id,
            raw_session_token=raw_session,
        )
    except CanvasOAuthError as exc:
        if exc.code == "instructor_handoff_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@course_router.post(
    "/courses/{course_id}/canvas-oauth-handoff/disconnect",
    response_model=CanvasOAuthDisconnectOut,
)
def disconnect_instructor_canvas_connection(
    course_id: int,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_course_route_access),
    store: EncryptedSecretStore = Depends(get_canvas_secret_store),
):
    response.headers.update(_headers())
    organization_id, registration_id, user_id, session_id, raw_session = (
        _instructor_handoff_context(request, db, principal, course_id)
    )
    try:
        return disconnect_instructor_canvas_oauth(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
            product_session_id=session_id,
            course_id=course_id,
            raw_session_token=raw_session,
            store=store,
        )
    except CanvasOAuthError as exc:
        if exc.code == "instructor_handoff_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@router.get(
    "/organizations/{organization_id}/registrations/{registration_id}",
    response_model=CanvasOAuthStatusOut,
)
def canvas_connection_status(
    organization_id: int,
    registration_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    store: EncryptedSecretStore = Depends(get_canvas_secret_store),
):
    response.headers.update(_headers())
    user_id = _admin_user(db, principal, organization_id)
    try:
        return canvas_oauth_status(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
            store=store,
        )
    except CanvasOAuthError as exc:
        if exc.code == "registration_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@router.put(
    "/organizations/{organization_id}/registrations/{registration_id}/configuration",
    response_model=CanvasOAuthConfigurationOut,
)
def configure_canvas_connection(
    organization_id: int,
    registration_id: int,
    payload: CanvasOAuthConfigurationIn,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    response.headers.update(_headers())
    user_id = _admin_user(db, principal, organization_id)
    try:
        return save_canvas_oauth_configuration(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            actor_user_id=user_id,
            canvas_api_origin=payload.canvas_api_origin,
            oauth_client_id=payload.oauth_client_id,
            expected_version=payload.expected_version,
        )
    except CanvasOAuthError as exc:
        if exc.code == "registration_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@router.post(
    "/organizations/{organization_id}/registrations/{registration_id}/start",
    response_model=CanvasOAuthStartOut,
)
def start_canvas_connection(
    organization_id: int,
    registration_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    response.headers.update(_headers())
    user_id = _admin_user(db, principal, organization_id)
    try:
        return start_canvas_oauth(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
        )
    except CanvasOAuthError as exc:
        if exc.code == "registration_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


@router.post(
    "/organizations/{organization_id}/registrations/{registration_id}/disconnect",
    response_model=CanvasOAuthDisconnectOut,
)
def disconnect_canvas_connection(
    organization_id: int,
    registration_id: int,
    response: Response,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    store: EncryptedSecretStore = Depends(get_canvas_secret_store),
):
    response.headers.update(_headers())
    user_id = _admin_user(db, principal, organization_id)
    try:
        return disconnect_canvas_oauth(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            user_id=user_id,
            store=store,
        )
    except CanvasOAuthError as exc:
        if exc.code == "registration_unavailable":
            raise HTTPException(404, "resource not found") from exc
        raise _api_error(exc) from exc


def _single_query_value(request: Request, name: str, *, required: bool = True) -> str:
    values = request.query_params.getlist(name)
    if len(values) != 1:
        if not required and not values:
            return ""
        raise HTTPException(400, "invalid authorization request")
    return values[0]


def _require_exact_query(request: Request, allowed: frozenset[str]) -> None:
    if set(request.query_params.keys()) - allowed:
        raise HTTPException(400, "invalid authorization request")


@router.get("/development/authorize", response_class=HTMLResponse)
def development_canvas_authorize(
    request: Request,
    db: Session = Depends(get_db),
):
    require_development_auth()
    _require_exact_query(
        request,
        frozenset(
            {"client_id", "response_type", "redirect_uri", "state", "scope", "decision"}
        ),
    )
    client_id = _single_query_value(request, "client_id")
    response_type = _single_query_value(request, "response_type")
    redirect_uri = _single_query_value(request, "redirect_uri")
    state = _single_query_value(request, "state")
    scope = _single_query_value(request, "scope")
    decision = _single_query_value(request, "decision", required=False)
    try:
        attempt = validate_development_authorization_request(
            db,
            state=state,
            client_id=client_id,
            response_type=response_type,
            redirect_uri=redirect_uri,
            scope=scope,
        )
        if decision:
            location = development_authorization_redirect(
                db,
                state=state,
                client_id=client_id,
                response_type=response_type,
                redirect_uri=redirect_uri,
                scope=scope,
                decision=decision,
                exchanger=development_code_exchanger(),
            )
            return RedirectResponse(location, status_code=302, headers=_headers())
    except CanvasOAuthError as exc:
        raise HTTPException(400, "invalid authorization request") from exc

    base_params = {
        "client_id": client_id,
        "response_type": response_type,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
    }
    allow_url = "?" + urlencode({**base_params, "decision": "allow"})
    deny_url = "?" + urlencode({**base_params, "decision": "deny"})
    scope_labels = {
        "url:GET|/api/v1/courses/:id": "Название и границы текущего курса",
        "url:GET|/api/v1/courses/:course_id/modules": "Структура модулей",
        "url:GET|/api/v1/courses/:course_id/pages": "Страницы курса",
        "url:GET|/api/v1/courses/:course_id/assignments": "Список заданий без работ учеников",
    }
    scopes = "".join(
        f"<li>{html.escape(scope_labels.get(item, item))}</li>"
        for item in attempt.requested_scopes
    )
    technical_scopes = "".join(
        f"<code>{html.escape(item)}</code>" for item in attempt.requested_scopes
    )
    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Тестовое разрешение Canvas</title><style>
:root{{--ink:#15315f;--slate:#5a6f8a;--paper:#f8fbff;--cobalt:#2457d6;--mint:#83d8c7;--yellow:#ffd95a}}
*{{box-sizing:border-box}} body{{margin:0;min-height:100vh;padding:32px 18px;background-color:var(--paper);background-image:linear-gradient(#dce8f5 1px,transparent 1px),linear-gradient(90deg,#dce8f5 1px,transparent 1px);background-size:24px 24px;color:var(--ink);font:16px/1.55 "Segoe UI",sans-serif}}
main{{width:min(760px,100%);margin:5vh auto;background:white;border:2px solid var(--ink);border-radius:7px 28px 7px 28px;box-shadow:9px 10px 0 rgba(36,87,214,.18);overflow:hidden}}
header{{padding:28px 32px;background:linear-gradient(105deg,#e9f4ff,#f2fffb);border-bottom:2px solid var(--ink)}}
.eyebrow{{font:700 12px/1.2 "Cascadia Mono",monospace;text-transform:uppercase;letter-spacing:.1em;color:var(--cobalt)}} h1{{margin:10px 0 8px;font-size:clamp(27px,6vw,42px);line-height:1.05}} p{{margin:0;color:var(--slate)}}
section{{padding:28px 32px}} .route{{display:flex;align-items:center;gap:10px;margin-bottom:24px;font-weight:750}} .route i{{flex:1;border-top:3px dashed var(--cobalt)}} .seal{{display:grid;place-items:center;width:56px;height:56px;border:2px solid var(--ink);border-radius:50%;background:var(--yellow);font:800 12px "Cascadia Mono",monospace;transform:rotate(-4deg)}}
ul{{padding:18px 18px 18px 38px;background:#f2fffb;border-left:5px solid var(--mint)}} li+li{{margin-top:7px}} .boundary{{padding:14px 16px;background:#fff9e9;border:1px solid #e6c85d;color:#66531c}} details{{margin-top:16px;color:var(--slate)}} summary{{width:fit-content;cursor:pointer;color:var(--cobalt);font-weight:750}} code{{display:block;margin-top:7px;overflow-wrap:anywhere;font:11px/1.45 "Cascadia Mono",monospace}}
nav{{display:flex;gap:12px;flex-wrap:wrap;margin-top:24px}} a{{display:inline-flex;min-height:46px;align-items:center;justify-content:center;padding:10px 18px;border:2px solid var(--ink);border-radius:9px;color:var(--ink);font-weight:750;text-decoration:none;box-shadow:3px 3px 0 var(--ink)}} a:first-child{{background:var(--cobalt);color:white}} a:focus-visible{{outline:4px solid var(--yellow);outline-offset:3px}}
@media(max-width:560px){{body{{padding:16px 10px}} header,section{{padding:22px 18px}} nav a{{width:100%}}}}
</style></head><body><main><header><span class="eyebrow">Локальный fake issuer · Canvas не вызывается</span><h1>Разрешить тестовое чтение?</h1><p>Этот экран проверяет только OAuth-маршрут и хранение доступа внутри локальной разработки.</p></header><section><div class="route"><span>Canvas API</span><i></i><span class="seal">OAuth</span><i></i><span>Текущий курс</span></div><strong>Запрашиваются четыре разрешения только на чтение:</strong><ul>{scopes}</ul><p class="boundary">Не входят: пользователи, списки класса, работы учеников, оценки, активность и любые изменения Canvas.</p><details><summary>Проверить точные Canvas scopes</summary>{technical_scopes}</details><nav><a href="{html.escape(allow_url, quote=True)}">Разрешить тест</a><a href="{html.escape(deny_url, quote=True)}">Не разрешать</a></nav></section></main></body></html>"""
    response = HTMLResponse(document, headers=_headers())
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    return response


@router.get("/callback", response_class=HTMLResponse)
def canvas_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
    exchanger: CanvasCodeExchanger = Depends(get_canvas_code_exchanger),
    store: EncryptedSecretStore = Depends(get_canvas_secret_store),
):
    _require_exact_query(request, frozenset({"state", "code", "error"}))
    state = _single_query_value(request, "state")
    code = _single_query_value(request, "code", required=False) or None
    error = _single_query_value(request, "error", required=False) or None
    try:
        completion = complete_canvas_oauth_callback(
            db,
            state=state,
            code=code,
            error=error,
            exchanger=exchanger,
            store=store,
            raw_product_session_token=request.cookies.get(session_cookie_policy().name),
        )
        location = canvas_oauth_return_url(
            completion.result,
            organization_id=completion.organization_id,
            registration_id=completion.registration_id,
            flow_kind=completion.flow_kind,
            course_id=completion.course_id,
        )
    except CanvasOAuthError as exc:
        if exc.code in {"callback_invalid", "production_connection_disabled"}:
            raise HTTPException(400, "invalid authorization callback") from exc
        location = canvas_oauth_return_url(
            "failed",
            flow_kind=exc.return_flow_kind or "admin",
            course_id=exc.return_course_id,
        )
    return RedirectResponse(location, status_code=303, headers=_headers())
