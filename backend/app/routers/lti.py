from __future__ import annotations

import html
import os
from typing import Literal
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    Course,
    CourseMembership,
    LtiContextBinding,
    LtiLaunchAttempt,
    LtiRegistration,
    LtiSubjectBinding,
    OrganizationMembership,
    User,
)
from ..schemas.lti import (
    DevelopmentLtiBootstrapIn,
    DevelopmentLtiBootstrapOut,
    DevelopmentSimulatorBootstrapIn,
    DevelopmentSimulatorBootstrapOut,
    DevelopmentSimulatorCourseOut,
    DevelopmentSimulatorLaunchOut,
    LtiBindingCandidateResolutionOut,
    LtiBindingCandidateResolveIn,
    LtiBindingReadinessOut,
    LtiPilotHealthOut,
    LtiRegistrationDraftIn,
    LtiRegistrationOut,
    LtiRegistrationReadinessOut,
    LtiRegistrationUpdateIn,
)
from ..services.authorization import (
    Principal,
    development_auth_available,
    get_current_principal,
    require_development_auth,
    require_organization_role,
)
from ..services.canvas_simulator import (
    SIMULATOR_INSTRUCTOR_EMAIL,
    SIMULATOR_LEARNER_EMAIL,
    bootstrap_canvas_simulator,
    canvas_simulator_enabled,
    simulator_launch,
)
from ..services.lti import (
    LtiLaunchError,
    create_login_redirect,
    digest_secret,
    login_http_error,
    validate_launch,
    validate_lti_endpoint,
)
from ..services.lti_binding import (
    LtiBindingError,
    bind_candidate,
    binding_readiness,
    dismiss_candidate,
)
from ..services.lti_development import (
    LOCAL_CLIENT_ID,
    LOCAL_DEPLOYMENT_ID,
    ROLE_URIS,
    decode_login_hint,
    development_role,
    encode_login_hint,
    issue_local_token,
    local_jwks,
    local_subject,
)
from ..services.lti_pilot_health import pilot_launch_health
from ..services.lti_registration import (
    LtiRegistrationConfigurationError,
    LtiRegistrationMutationError,
    create_registration_draft,
    list_production_registrations,
    public_jwks_etag,
    public_tool_jwks,
    readiness_out,
    tool_registration_readiness,
    update_production_registration,
)
from ..services.product_session import (
    clear_product_session_cookie,
    issue_product_session,
    resolve_product_session,
    revoke_product_session,
    session_cookie_policy,
    set_product_session_cookie,
)

router = APIRouter(prefix="/integrations/lti", tags=["lti"])

ROLE_LABELS = {
    "student": "Ученик",
    "instructor": "Преподаватель",
    "program_designer": "Архитектор программы",
    "administrator": "Администратор",
}


def _headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-store, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff",
    }


def _frontend_course_url(*, course_id: int, role: str) -> str:
    default = "http://localhost:3000"
    base = os.getenv("FRONTEND_PUBLIC_URL", default).strip().rstrip("/")
    parsed = urlparse(base)
    production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    if (
        parsed.scheme not in ({"https"} if production else {"http", "https"})
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("FRONTEND_PUBLIC_URL must be a trusted origin")
    path = (
        "/canvas-companion"
        if role == "student"
        else f"/workspace/courses/{course_id}?lti=1"
    )
    return f"{base}{path}"


def _development_return_url(db: Session, state: str) -> str | None:
    if not development_auth_available() or not state or len(state) > 200:
        return None
    attempt = (
        db.query(LtiLaunchAttempt)
        .filter(LtiLaunchAttempt.state_digest == digest_secret(state))
        .first()
    )
    registration = db.get(LtiRegistration, attempt.registration_id) if attempt else None
    if (
        registration is None
        or not registration.is_development
        or not registration.is_active
    ):
        return None
    return f"/integrations/lti/development?registration_id={registration.id}"


def _page(title: str, content: str, *, status_code: int = 200) -> HTMLResponse:
    document = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; min-height: 100vh; color: #172033; background: #f6f8fc; }}
    main {{ width: min(720px, calc(100% - 32px)); margin: 0 auto; padding: 48px 0; }}
    .eyebrow {{ color: #356ae6; font-weight: 750; letter-spacing: .04em; text-transform: uppercase; font-size: .78rem; }}
    h1 {{ margin: 10px 0 12px; font-size: clamp(1.75rem, 5vw, 2.5rem); line-height: 1.12; }}
    p {{ color: #536078; line-height: 1.6; }}
    .panel {{ margin-top: 24px; padding: 24px; border: 1px solid #dfe5f0; border-radius: 20px; background: #fff; box-shadow: 0 14px 40px rgba(23,32,51,.08); }}
    .status {{ display: inline-flex; gap: 8px; align-items: center; padding: 7px 11px; border-radius: 999px; color: #0b675d; background: #e7f6f2; font-weight: 700; }}
    .status.error {{ color: #8f303b; background: #fdecef; }}
    .trustpath {{ display: grid; grid-template-columns: 1fr 1fr 1fr; margin: 24px 0 4px; padding: 0; list-style: none; }}
    .trustpath li {{ position: relative; padding-top: 24px; color: #536078; font-size: .82rem; font-weight: 700; text-align: center; }}
    .trustpath li::before {{ content: ""; position: absolute; z-index: 2; top: 3px; left: calc(50% - 7px); width: 14px; height: 14px; border: 3px solid #fff; border-radius: 50%; background: #356ae6; box-shadow: 0 0 0 1px #9eabd0; }}
    .trustpath li::after {{ content: ""; position: absolute; top: 9px; left: 50%; width: 100%; height: 2px; background: #b9c6e6; }}
    .trustpath li:last-child::after {{ display: none; }}
    .trustpath .verified::before {{ background: #178c7e; box-shadow: 0 0 0 1px #178c7e; }}
    dl {{ display: grid; grid-template-columns: minmax(120px, 1fr) 2fr; gap: 12px 20px; margin: 24px 0; }}
    dt {{ color: #536078; }} dd {{ margin: 0; font-weight: 680; overflow-wrap: anywhere; }}
    label {{ display: block; margin: 18px 0 8px; font-weight: 700; }}
    select {{ width: 100%; min-height: 48px; padding: 10px 12px; border: 1px solid #aeb8ca; border-radius: 10px; background: white; color: #172033; font: inherit; }}
    a.button, button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 46px; padding: 10px 16px; border: 0; border-radius: 11px; color: #fff; background: #356ae6; font: inherit; font-weight: 750; text-decoration: none; cursor: pointer; }}
    a.secondary {{ color: #244fae; background: #eaf0ff; }}
    a:focus-visible, button:focus-visible, select:focus-visible {{ outline: 3px solid #f0b44d; outline-offset: 3px; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 24px; }}
    .note {{ padding: 14px 16px; border-left: 4px solid #178c7e; background: #eff9f7; border-radius: 8px; }}
    @media (max-width: 520px) {{ main {{ padding: 24px 0; }} .panel {{ padding: 20px; border-radius: 16px; }} dl {{ grid-template-columns: 1fr; gap: 5px; }} dd {{ margin-bottom: 10px; }} .actions a, .actions button {{ width: 100%; }} }}
  </style>
</head>
<body><main>{content}</main></body>
</html>"""
    response = HTMLResponse(document, status_code=status_code, headers=_headers())
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
        "form-action 'self'"
    )
    return response


async def _request_values(request: Request) -> dict[str, str]:
    values = dict(request.query_params)
    if request.method == "POST":
        form = await request.form()
        values.update({key: str(value) for key, value in form.items()})
    return values


@router.get("/configuration", name="lti_public_configuration")
def lti_public_configuration():
    readiness = tool_registration_readiness()
    if not readiness.configuration_ready or readiness.canvas_configuration is None:
        raise HTTPException(503, "LTI tool configuration is unavailable")
    return JSONResponse(
        readiness.canvas_configuration,
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/jwks", name="lti_public_jwks")
def lti_public_jwks(request: Request):
    try:
        jwks, _ = public_tool_jwks()
    except LtiRegistrationConfigurationError as exc:
        raise HTTPException(503, "LTI public keys are unavailable") from exc
    etag = public_jwks_etag(jwks)
    supplied = {
        value.strip().removeprefix("W/")
        for value in request.headers.get("if-none-match", "").split(",")
        if value.strip()
    }
    headers = {
        "Cache-Control": "public, max-age=300",
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }
    if etag in supplied or "*" in supplied:
        return Response(status_code=304, headers=headers)
    return JSONResponse(jwks, headers=headers)


def _registration_mutation_error(
    db: Session, exc: LtiRegistrationMutationError
) -> None:
    db.rollback()
    if exc.code in {"organization_unavailable", "registration_unavailable"}:
        raise HTTPException(404, "resource not found") from exc
    conflicts = {
        "deactivate_before_editing": "Deactivate the registration before editing it.",
        "activate_separately": "Save registration details before activation.",
        "tool_not_production_ready": "The public tool is not production-ready yet.",
        "platform_host_allowlist_missing": (
            "The platform host allow-list is not configured."
        ),
        "authorization_endpoint_untrusted": (
            "The authorization endpoint did not pass trust checks."
        ),
        "jwks_endpoint_untrusted": "The platform key endpoint did not pass trust checks.",
    }
    if exc.code in conflicts:
        raise HTTPException(
            409,
            {"code": exc.code, "message": conflicts[exc.code]},
        ) from exc
    messages = {
        "invalid_identifier": "Identifiers must be exact non-empty values.",
        "invalid_url": "Enter an exact HTTPS URL.",
        "https_required": "Production platform URLs must use HTTPS.",
        "origin_required": "Enter an origin without a path or query.",
        "tool_configuration_unavailable": (
            "Configure the public tool address and keys first."
        ),
    }
    raise HTTPException(
        422,
        {
            "code": exc.code,
            "message": messages.get(exc.code, "Registration data is invalid."),
        },
    ) from exc


@router.get(
    "/organizations/{organization_id}/readiness",
    response_model=LtiRegistrationReadinessOut,
)
def lti_registration_readiness(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    return readiness_out()


@router.get(
    "/organizations/{organization_id}/registrations",
    response_model=list[LtiRegistrationOut],
)
def lti_registrations(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    return list_production_registrations(db, organization_id=organization_id)


@router.get(
    "/organizations/{organization_id}/pilot-health",
    response_model=LtiPilotHealthOut,
)
def lti_pilot_health(
    organization_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    return pilot_launch_health(db, organization_id=organization_id)


@router.post(
    "/organizations/{organization_id}/registrations",
    response_model=LtiRegistrationOut,
    status_code=201,
)
def create_lti_registration(
    organization_id: int,
    payload: LtiRegistrationDraftIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    try:
        result = create_registration_draft(
            db,
            organization_id=organization_id,
            actor_user_id=principal.user_id,
            values=payload.model_dump(),
        )
        db.commit()
        return result
    except LtiRegistrationMutationError as exc:
        _registration_mutation_error(db, exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "registration_duplicate",
                "message": "This Canvas deployment is already registered.",
            },
        ) from exc


@router.patch(
    "/organizations/{organization_id}/registrations/{registration_id}",
    response_model=LtiRegistrationOut,
)
def update_lti_registration(
    organization_id: int,
    registration_id: int,
    payload: LtiRegistrationUpdateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    try:
        result = update_production_registration(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            actor_user_id=principal.user_id,
            changes=payload.model_dump(exclude_unset=True),
        )
        db.commit()
        return result
    except LtiRegistrationMutationError as exc:
        _registration_mutation_error(db, exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "registration_duplicate",
                "message": "This Canvas deployment is already registered.",
            },
        ) from exc


def _binding_error(db: Session, exc: LtiBindingError) -> None:
    db.rollback()
    if exc.code in {
        "registration_not_found",
        "candidate_not_found",
        "target_not_found",
    }:
        raise HTTPException(404, "resource not found") from exc
    raise HTTPException(
        409,
        {
            "code": exc.code,
            "message": "The binding request is no longer available. Refresh and retry.",
        },
    ) from exc


@router.get(
    "/organizations/{organization_id}/registrations/{registration_id}/binding-candidates",
    response_model=LtiBindingReadinessOut,
)
def lti_binding_candidates(
    organization_id: int,
    registration_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    try:
        result = binding_readiness(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
        )
        db.commit()
        return result
    except LtiBindingError as exc:
        _binding_error(db, exc)


@router.post(
    "/organizations/{organization_id}/registrations/{registration_id}/binding-candidates/{candidate_id}/bind",
    response_model=LtiBindingCandidateResolutionOut,
)
def bind_lti_candidate(
    organization_id: int,
    registration_id: int,
    candidate_id: int,
    payload: LtiBindingCandidateResolveIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    try:
        result = bind_candidate(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            candidate_id=candidate_id,
            target_id=payload.target_id,
            actor_user_id=principal.user_id,
        )
        db.commit()
        return result
    except LtiBindingError as exc:
        _binding_error(db, exc)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            409,
            {
                "code": "binding_conflict",
                "message": "This Canvas identifier or target is already bound.",
            },
        ) from exc


@router.post(
    "/organizations/{organization_id}/registrations/{registration_id}/binding-candidates/{candidate_id}/dismiss",
    response_model=LtiBindingCandidateResolutionOut,
)
def dismiss_lti_candidate(
    organization_id: int,
    registration_id: int,
    candidate_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    require_organization_role(
        db, principal, organization_id, frozenset({"administrator"})
    )
    try:
        result = dismiss_candidate(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
            candidate_id=candidate_id,
            actor_user_id=principal.user_id,
        )
        db.commit()
        return result
    except LtiBindingError as exc:
        _binding_error(db, exc)


@router.get("/login", name="lti_login_get", operation_id="lti_login_get")
@router.post("/login", name="lti_login_post", operation_id="lti_login_post")
async def lti_login(request: Request, db: Session = Depends(get_db)):
    values = await _request_values(request)
    deployment_id = values.get("lti_deployment_id") or values.get("deployment_id")
    if (
        values.get("lti_deployment_id")
        and values.get("deployment_id")
        and values["lti_deployment_id"] != values["deployment_id"]
    ):
        raise login_http_error(LtiLaunchError("invalid_login_request"))
    try:
        location = create_login_redirect(
            db,
            issuer=values.get("iss", ""),
            login_hint=values.get("login_hint", ""),
            target_link_uri=values.get("target_link_uri", ""),
            client_id=values.get("client_id"),
            deployment_id=deployment_id,
            lti_message_hint=values.get("lti_message_hint"),
        )
    except LtiLaunchError as exc:
        raise login_http_error(exc) from exc
    return RedirectResponse(location, status_code=302, headers=_headers())


@router.post("/launch", response_class=HTMLResponse, name="lti_launch")
def lti_launch(
    request: Request,
    state: str = Form(default=""),
    id_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    try:
        result = validate_launch(db, state=state, id_token=id_token)
    except LtiLaunchError:
        development_return = _development_return_url(db, state)
        actions = (
            '<div class="actions"><a class="button secondary" '
            f'href="{html.escape(development_return, quote=True)}">'
            "Вернуться к выбору</a></div>"
            if development_return
            else ""
        )
        guidance = (
            "Вернитесь к выбору и запустите локальную проверку ещё раз. Если ошибка "
            "повторится, администратору нужно проверить регистрацию и явные привязки."
            if development_return
            else "Вернитесь в платформу, из которой открыт инструмент, и запустите "
            "его ещё раз. Если ошибка "
            "повторится, администратору нужно проверить регистрацию и явные привязки."
        )
        return _page(
            "Запуск не подтверждён",
            """
<div class="eyebrow">Безопасная граница LTI</div>
<h1>Запуск не подтверждён</h1>
<p>Подпись, одноразовый запрос или заранее настроенные права не прошли проверку. Внутренние данные курса не раскрыты, Canvas не изменён.</p>
<section class="panel" aria-labelledby="failure-state">
  <div id="failure-state" class="status error">Доступ закрыт</div>
  <p>{guidance}</p>
  {actions}
</section>
""".format(
                actions=actions, guidance=html.escape(guidance)
            ),
            status_code=403,
        )
    role_label = ROLE_LABELS[result.role]
    registration = db.get(LtiRegistration, result.registration_id)
    development_return = (
        f"/integrations/lti/development?registration_id={registration.id}"
        if registration is not None
        and registration.is_development
        and registration.is_active
        else None
    )
    issued_session = None
    primary_action = ""
    destination = (
        _frontend_course_url(course_id=result.course_id, role=result.role)
        if result.role in {"student", "instructor"}
        else None
    )
    cookie_name = session_cookie_policy().name
    prior_raw_session = request.cookies.get(cookie_name)
    prior_session = resolve_product_session(db, prior_raw_session)
    if prior_session is not None:
        revoke_product_session(db, prior_session.row.id)
    if result.role in {"student", "instructor"}:
        issued_session = issue_product_session(
            db,
            registration_id=result.registration_id,
            user_id=result.user_id,
            course_id=result.course_id,
            role=result.role,
        )
        primary_action = (
            '<a class="button" '
            f'href="{html.escape(destination, quote=True)}">Открыть курс</a>'
        )
    secondary_action = (
        '<a class="button secondary" '
        f'href="{html.escape(development_return, quote=True)}">'
        "Вернуться к выбору</a>"
        if development_return
        else ""
    )
    actions = (
        f'<div class="actions">{primary_action}{secondary_action}</div>'
        if primary_action or secondary_action
        else ""
    )
    content = f"""
<div class="eyebrow">Безопасная граница LTI</div>
<h1>Запуск подтверждён</h1>
<p>Подписанное сообщение платформы, одноразовый запрос и внутренние права совпали.</p>
<section class="panel" aria-labelledby="launch-state">
  <div id="launch-state" class="status">Проверка пройдена</div>
  <ol class="trustpath" aria-label="Путь доверия"><li class="verified">Платформа</li><li class="verified">Подпись и запрос</li><li class="verified">Курс и роль</li></ol>
  <dl>
    <dt>Пользователь</dt><dd>{html.escape(result.display_name)}</dd>
    <dt>Курс</dt><dd>{html.escape(result.course_title)}</dd>
    <dt>Роль</dt><dd>{html.escape(role_label)}</dd>
  </dl>
  <p class="note"><strong>Canvas не изменён.</strong> Запуск подтвердил доступ только к этому курсу. Сервис не синхронизировал содержимое и ничего не записывал обратно в LMS.</p>
  {actions}
</section>
"""
    response = _page("Запуск подтверждён", content)
    if issued_session is not None:
        set_product_session_cookie(response, issued_session.raw_token)
    elif prior_raw_session is not None:
        clear_product_session_cookie(response)
    return response


@router.post(
    "/development/bootstrap",
    response_model=DevelopmentLtiBootstrapOut,
    status_code=201,
    dependencies=[Depends(require_development_auth)],
)
def development_bootstrap(
    payload: DevelopmentLtiBootstrapIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    course = db.get(Course, payload.course_id)
    if course is None or course.organization_id is None:
        raise HTTPException(404, "resource not found")
    require_organization_role(
        db, principal, course.organization_id, frozenset({"administrator"})
    )
    base = payload.public_base_url.rstrip("/")
    try:
        validate_lti_endpoint(base, allow_development_loopback=True)
    except ValueError as exc:
        raise HTTPException(422, "development base URL must be loopback HTTP") from exc
    parsed_base = urlparse(base)
    if parsed_base.path not in {"", "/"} or parsed_base.query:
        raise HTTPException(422, "development base URL cannot contain a path or query")
    issuer = f"{base}/integrations/lti/development/platform"
    registration = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.issuer == issuer,
            LtiRegistration.client_id == LOCAL_CLIENT_ID,
            LtiRegistration.deployment_id == LOCAL_DEPLOYMENT_ID,
        )
        .first()
    )
    if registration is None:
        registration = LtiRegistration(
            organization_id=course.organization_id,
            issuer=issuer,
            client_id=LOCAL_CLIENT_ID,
            deployment_id=LOCAL_DEPLOYMENT_ID,
            authorization_endpoint=f"{base}/integrations/lti/development/authorize",
            jwks_url=f"{base}/integrations/lti/development/jwks",
            tool_launch_url=f"{base}/integrations/lti/launch",
            is_active=True,
            is_development=True,
        )
        db.add(registration)
        db.flush()
    else:
        if registration.organization_id != course.organization_id:
            raise HTTPException(409, "development registration belongs elsewhere")
        registration.authorization_endpoint = (
            f"{base}/integrations/lti/development/authorize"
        )
        registration.jwks_url = f"{base}/integrations/lti/development/jwks"
        registration.tool_launch_url = f"{base}/integrations/lti/launch"
        registration.is_active = True
        registration.is_development = True

    context = (
        db.query(LtiContextBinding)
        .filter(LtiContextBinding.registration_id == registration.id)
        .first()
    )
    if context is None:
        context = LtiContextBinding(
            registration_id=registration.id,
            course_id=course.id,
            platform_context_id=f"local-context-{course.id}",
        )
        db.add(context)
    elif context.course_id != course.id:
        raise HTTPException(409, "development registration is bound to another course")

    memberships = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.course_id == course.id,
            CourseMembership.organization_id == course.organization_id,
            CourseMembership.is_active.is_(True),
            CourseMembership.role.in_(ROLE_URIS),
        )
        .all()
    )
    admin_user_ids = {
        user_id
        for (user_id,) in db.query(OrganizationMembership.user_id)
        .filter(
            OrganizationMembership.organization_id == course.organization_id,
            OrganizationMembership.role == "administrator",
            OrganizationMembership.is_active.is_(True),
        )
        .all()
    }
    eligible_user_ids = {item.user_id for item in memberships} | admin_user_ids
    bound_users = 0
    for user_id in sorted(eligible_user_ids):
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            continue
        binding = (
            db.query(LtiSubjectBinding)
            .filter(
                LtiSubjectBinding.registration_id == registration.id,
                LtiSubjectBinding.user_id == user.id,
            )
            .first()
        )
        if binding is None:
            db.add(
                LtiSubjectBinding(
                    registration_id=registration.id,
                    user_id=user.id,
                    platform_subject=local_subject(user.id),
                )
            )
        bound_users += 1
    db.commit()
    chooser_url = (
        f"{base}/integrations/lti/development?registration_id={registration.id}"
    )
    return DevelopmentLtiBootstrapOut(
        registration_id=registration.id,
        bound_users=bound_users,
        chooser_url=chooser_url,
    )


@router.post(
    "/development/simulator/bootstrap",
    response_model=DevelopmentSimulatorBootstrapOut,
    status_code=201,
    dependencies=[Depends(require_development_auth)],
)
def development_simulator_bootstrap(
    payload: DevelopmentSimulatorBootstrapIn,
    db: Session = Depends(get_db),
):
    if not canvas_simulator_enabled():
        raise HTTPException(404, "resource not found")
    try:
        organization_id, results = bootstrap_canvas_simulator(
            db,
            lti_base_url=payload.lti_base_url,
            canvas_base_url=payload.canvas_base_url,
        )
        db.commit()
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(404, "resource not found") from exc
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        raise HTTPException(422, "invalid synthetic simulator configuration") from exc
    courses = [
        DevelopmentSimulatorCourseOut(
            fixture_id=result.fixture_id,
            course_id=result.course_id,
            registration_id=result.registration_id,
            learner_subject=result.learner_subject,
            instructor_subject=result.instructor_subject,
            launch_url=result.launch_url,
            instructor_launch_url=result.instructor_launch_url,
            chooser_url=result.chooser_url,
        )
        for result in results
    ]
    return DevelopmentSimulatorBootstrapOut(
        organization_id=organization_id,
        learner_email=SIMULATOR_LEARNER_EMAIL,
        instructor_email=SIMULATOR_INSTRUCTOR_EMAIL,
        courses=courses,
        registration_map={item.fixture_id: item.registration_id for item in courses},
    )


@router.get(
    "/development/simulator/{fixture_id}",
    response_model=DevelopmentSimulatorLaunchOut,
    dependencies=[Depends(require_development_auth)],
)
def development_simulator_launch(
    fixture_id: str,
    actor: Literal["learner", "instructor"] = "learner",
    db: Session = Depends(get_db),
):
    try:
        result = simulator_launch(
            db,
            fixture_id=fixture_id,
            actor=actor,
            lti_base_url=os.getenv(
                "CANVAS_SIMULATOR_LTI_BASE_URL", "http://localhost:8000"
            ),
        )
    except ValueError as exc:
        raise HTTPException(404, "resource not found") from exc
    if result is None:
        raise HTTPException(404, "resource not found")
    response = DevelopmentSimulatorLaunchOut(
        fixture_id=result.fixture_id,
        course_id=result.course_id,
        registration_id=result.registration_id,
        actor=result.actor,
        subject=result.subject,
        launch_url=result.launch_url,
        chooser_url=result.chooser_url,
    )
    return JSONResponse(response.model_dump(), headers=_headers())


@router.get("/development", response_class=HTMLResponse)
def development_chooser(registration_id: int, db: Session = Depends(get_db)):
    require_development_auth()
    registration = db.get(LtiRegistration, registration_id)
    if (
        registration is None
        or not registration.is_development
        or not registration.is_active
    ):
        raise HTTPException(404, "resource not found")
    context = (
        db.query(LtiContextBinding)
        .filter(LtiContextBinding.registration_id == registration.id)
        .first()
    )
    course = db.get(Course, context.course_id) if context else None
    choices = []
    for binding in (
        db.query(LtiSubjectBinding)
        .filter(LtiSubjectBinding.registration_id == registration.id)
        .all()
    ):
        user = db.get(User, binding.user_id)
        if user is None or course is None:
            continue
        role = development_role(db, registration, user.id, course.id)
        if role is None:
            continue
        href = "/integrations/lti/development/start?" + urlencode(
            {"registration_id": registration.id, "subject": binding.platform_subject}
        )
        choices.append(
            f'<option value="{html.escape(href, quote=True)}">'
            f"{html.escape(user.display_name)} — {html.escape(ROLE_LABELS[role])}</option>"
        )
    if not choices:
        inner = """
<div class="eyebrow">Локальная проверка интеграции</div>
<h1>Нет готовых сценариев</h1>
<p>Администратору нужно создать явные привязки активных пользователей и курса.</p>
"""
    else:
        inner = f"""
<div class="eyebrow">Локальная проверка интеграции</div>
<h1>Проверить LTI-запуск локально</h1>
<p>Локальная платформа повторит путь запуска Canvas без подключения к школьной LMS.</p>
<section class="panel">
  <p><strong>Курс:</strong> {html.escape(course.title)}</p>
  <ol class="trustpath" aria-label="Этапы проверки"><li>Платформа</li><li>Подпись</li><li>Курс и роль</li></ol>
  <form method="get" action="/integrations/lti/development/go">
    <label for="scenario">Пользователь и роль</label>
    <select id="scenario" name="target">{''.join(choices)}</select>
    <div class="actions"><button type="submit">Проверить запуск</button></div>
  </form>
  <p class="note"><strong>Только проверка.</strong> Canvas не будет прочитан или изменён.</p>
</section>
"""
    return _page("Локальная проверка LTI", inner)


@router.get("/development/go")
def development_go(target: str):
    require_development_auth()
    parsed = urlparse(target)
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.path != "/integrations/lti/development/start"
    ):
        raise HTTPException(400, "invalid development target")
    return RedirectResponse(target, status_code=303, headers=_headers())


@router.get("/development/start")
def development_start(
    registration_id: int, subject: str, db: Session = Depends(get_db)
):
    require_development_auth()
    registration = db.get(LtiRegistration, registration_id)
    if (
        registration is None
        or not registration.is_development
        or not registration.is_active
    ):
        raise HTTPException(404, "resource not found")
    subject_binding = (
        db.query(LtiSubjectBinding)
        .filter(
            LtiSubjectBinding.registration_id == registration.id,
            LtiSubjectBinding.platform_subject == subject,
        )
        .first()
    )
    context = (
        db.query(LtiContextBinding)
        .filter(LtiContextBinding.registration_id == registration.id)
        .first()
    )
    if subject_binding is None or context is None:
        raise HTTPException(404, "resource not found")
    login_hint = encode_login_hint(
        registration.id, subject, context.platform_context_id
    )
    location = "/integrations/lti/login?" + urlencode(
        {
            "iss": registration.issuer,
            "login_hint": login_hint,
            "target_link_uri": registration.tool_launch_url,
            "client_id": registration.client_id,
            "lti_deployment_id": registration.deployment_id,
        }
    )
    return RedirectResponse(location, status_code=302, headers=_headers())


@router.get("/development/authorize", response_class=HTMLResponse)
def development_authorize(request: Request, db: Session = Depends(get_db)):
    require_development_auth()
    query = request.query_params
    if (
        query.get("scope") != "openid"
        or query.get("response_type") != "id_token"
        or query.get("response_mode") != "form_post"
        or query.get("prompt") != "none"
    ):
        raise HTTPException(400, "invalid authorization request")
    try:
        registration_id, subject, context_id = decode_login_hint(
            query.get("login_hint", "")
        )
    except ValueError as exc:
        raise HTTPException(400, "invalid authorization request") from exc
    registration = db.get(LtiRegistration, registration_id)
    if (
        registration is None
        or not registration.is_development
        or not registration.is_active
        or query.get("client_id") != registration.client_id
        or query.get("redirect_uri") != registration.tool_launch_url
    ):
        raise HTTPException(400, "invalid authorization request")
    state = query.get("state", "")
    nonce = query.get("nonce", "")
    if not state or not nonce or len(state) > 200 or len(nonce) > 200:
        raise HTTPException(400, "invalid authorization request")
    try:
        token = issue_local_token(
            db,
            registration=registration,
            subject=subject,
            context_id=context_id,
            nonce=nonce,
        )
    except ValueError as exc:
        raise HTTPException(400, "invalid authorization request") from exc
    document = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Подтверждение запуска</title></head>
<body onload="document.forms[0].submit()">
<main><h1>Подтверждаем запуск…</h1><p>Локальная платформа передаёт подписанное сообщение инструменту.</p>
<form method="post" action="{html.escape(registration.tool_launch_url, quote=True)}">
<input type="hidden" name="state" value="{html.escape(state, quote=True)}">
<input type="hidden" name="id_token" value="{html.escape(token, quote=True)}">
<button type="submit">Продолжить</button></form></main></body></html>"""
    response = HTMLResponse(document, headers=_headers())
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "form-action 'self' http://localhost:* http://127.0.0.1:* http://testserver"
    )
    return response


@router.get("/development/jwks")
def development_jwks():
    require_development_auth()
    return JSONResponse(local_jwks(), headers=_headers())
