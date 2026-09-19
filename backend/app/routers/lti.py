from __future__ import annotations

import hashlib
import json
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..services import lti_security as security

router = APIRouter(prefix="/lti", tags=["LTI"])


@router.get("/config")
def registration():
    cfg = security.settings(registered=False)
    base = cfg["PUBLIC_BASE_URL"]
    return {
        "title": "Помощник курса",
        "description": "Чат по материалам курса, анализ Блума и обратная связь",
        "oidc_initiation_url": base + "/lti/login",
        "target_link_uri": base + "/lti/launch",
        "scopes": [],
        "public_jwk_url": base + "/lti/jwks",
        "custom_fields": {"canvas_course_id": "$Canvas.course.id"},
        "extensions": [
            {
                "domain": base.split("//", 1)[1],
                "platform": "canvas.instructure.com",
                "settings": {
                    "privacy_level": "anonymous",
                    "placements": [
                        {
                            "placement": "course_navigation",
                            "message_type": "LtiResourceLinkRequest",
                            "target_link_uri": base + "/lti/launch",
                            "text": "Помощник курса",
                            "enabled": True,
                            "windowTarget": "_blank",
                        }
                    ],
                },
            }
        ],
    }


@router.get("/jwks")
def public_keys():
    # This pilot does not call signed LTI services (AGS/NRPS) or Deep Linking.
    # Its public key is generated for registration, never the Canvas validation key.
    import os
    from pathlib import Path

    path = os.getenv("LTI_PUBLIC_JWKS_PATH", "")
    if not path:
        raise HTTPException(503, "Tool registration key not configured")
    try:
        jwks = json.loads(Path(path).read_text(encoding="utf-8"))
        keys = jwks["keys"]
        if not keys or any("d" in item or item.get("kty") != "RSA" for item in keys):
            raise ValueError()
        # Return only public RSA fields even if the file was configured incorrectly.
        return {
            "keys": [
                {k: item[k] for k in ("kty", "kid", "use", "alg", "n", "e")}
                for item in keys
            ]
        }
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Tool registration key invalid") from None


@router.api_route("/login", methods=["GET", "POST"])
async def login(request: Request):
    cfg = security.settings()
    params = await request.form() if request.method == "POST" else request.query_params
    if (
        params.get("iss") != cfg["LTI_ISSUER"]
        or params.get("client_id", cfg["LTI_CLIENT_ID"]) != cfg["LTI_CLIENT_ID"]
    ):
        raise HTTPException(400, "Unrecognized LTI platform")
    if (
        not params.get("login_hint")
        or params.get("target_link_uri") != cfg["PUBLIC_BASE_URL"] + "/lti/launch"
    ):
        raise HTTPException(400, "Invalid login request")
    nonce = secrets.token_urlsafe(32)
    state = security.put_token("state", {"nonce": nonce}, 300)
    query = {
        "scope": "openid",
        "response_type": "id_token",
        "response_mode": "form_post",
        "prompt": "none",
        "client_id": cfg["LTI_CLIENT_ID"],
        "redirect_uri": cfg["PUBLIC_BASE_URL"] + "/lti/launch",
        "login_hint": params["login_hint"],
        "nonce": nonce,
        "state": state,
    }
    if params.get("lti_message_hint"):
        query["lti_message_hint"] = params["lti_message_hint"]
    response = RedirectResponse(
        cfg["LTI_AUTH_URL"] + "?" + urlencode(query),
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        "lti_login",
        state,
        max_age=300,
        httponly=True,
        secure=True,
        samesite="none",
        path="/lti",
    )
    return response


@router.post("/launch")
async def launch(request: Request, db: Annotated[Session, Depends(get_db)]):
    cfg = security.settings()
    form = await request.form()
    encoded, state_token = form.get("id_token"), form.get("state")
    if (
        not isinstance(encoded, str)
        or not isinstance(state_token, str)
        or len(encoded) > 50000
        or len(state_token) > 128
    ):
        raise HTTPException(400, "Missing or oversized LTI launch")
    if not secrets.compare_digest(request.cookies.get("lti_login", ""), state_token):
        raise HTTPException(
            401, "LTI browser state mismatch; launch in a new tab from Canvas"
        )
    state = security.consume_state(state_token)
    identity = security.validate_launch(encoded, state, cfg)
    binding = hashlib.sha256(
        json.dumps(
            [
                cfg["LTI_ISSUER"],
                cfg["LTI_CLIENT_ID"],
                cfg["LTI_DEPLOYMENT_ID"],
                identity["context_id"],
            ]
        ).encode()
    ).hexdigest()
    # Serialize first launches for the same context; all binding writes share one transaction.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": int(binding[:15], 16)}
    )
    course = (
        db.execute(
            text(
                "SELECT id, dataset_id, canvas_course_id FROM portal_courses WHERE binding=:binding"
            ),
            {"binding": binding},
        )
        .mappings()
        .first()
    )
    if course is None:
        dataset = db.execute(
            text("INSERT INTO datasets(name) VALUES (:name) RETURNING id"),
            {"name": "lti:" + binding},
        ).scalar_one()
        course = (
            db.execute(
                text(
                    "INSERT INTO portal_courses(binding,canvas_course_id,title,dataset_id) VALUES (:binding,:cid,:title,:ds) RETURNING id,dataset_id,canvas_course_id"
                ),
                {
                    "binding": binding,
                    "cid": identity["course_id"],
                    "title": identity["title"],
                    "ds": dataset,
                },
            )
            .mappings()
            .one()
        )
    if course["canvas_course_id"] != identity["course_id"]:
        raise HTTPException(401, "Course context mismatch")
    db.commit()
    session = {
        **identity,
        "course_id": course["id"],
        "canvas_course_id": identity["course_id"],
        "dataset_id": course["dataset_id"],
    }
    token = security.put_token("session", session, 3600)
    script_nonce = secrets.token_urlsafe(24)
    # Token stays out of URLs, referrers and cookies. Launch in a new tab to avoid iframe storage restrictions.
    html = f'''<!doctype html><html lang="ru"><meta charset="utf-8"><title>Помощник курса</title>
<p id="status">Открываем помощника курса…</p>
<script nonce="{script_nonce}">try {{ sessionStorage.setItem("canvas_portal_token", {json.dumps(token)}); location.replace("/portal"); }}
catch (e) {{ document.getElementById("status").textContent="Браузер запретил хранилище. Запустите инструмент из Canvas в новой вкладке."; }}</script></html>'''
    response = HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": f"default-src 'none'; script-src 'nonce-{script_nonce}'; frame-ancestors {cfg['CANVAS_URL']}",
        },
    )
    response.delete_cookie(
        "lti_login", path="/lti", secure=True, httponly=True, samesite="none"
    )
    return response
