"""Single-platform LTI 1.3 pilot. Only administrator-configured endpoints are used."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from functools import lru_cache
from urllib.parse import urlparse

import jwt
from fastapi import Header, HTTPException
from redis import Redis
from redis.exceptions import RedisError

CLAIM = "https://purl.imsglobal.org/spec/lti/claim/"
TEACHER_ROLES = {
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper",
}
LEARNER_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner"


def settings(*, registered: bool = True) -> dict:
    names = (
        "LTI_ISSUER",
        "LTI_CLIENT_ID",
        "LTI_DEPLOYMENT_ID",
        "LTI_AUTH_URL",
        "LTI_JWKS_URL",
        "PUBLIC_BASE_URL",
        "LTI_ALLOWED_COURSE_IDS",
        "CANVAS_URL",
    )
    cfg = {name: os.getenv(name, "").strip() for name in names}
    required = names if registered else ("PUBLIC_BASE_URL", "CANVAS_URL")
    if any(not cfg[name] for name in required):
        raise HTTPException(503, "LTI is not configured; contact the administrator")
    for name in (
        "LTI_ISSUER",
        "LTI_AUTH_URL",
        "LTI_JWKS_URL",
        "PUBLIC_BASE_URL",
        "CANVAS_URL",
    ):
        if not cfg[name] and not registered:
            continue
        parsed = urlparse(cfg[name])
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise HTTPException(503, "LTI requires valid HTTPS configuration")
    cfg["PUBLIC_BASE_URL"] = cfg["PUBLIC_BASE_URL"].rstrip("/")
    cfg["CANVAS_URL"] = cfg["CANVAS_URL"].rstrip("/")
    if urlparse(cfg["PUBLIC_BASE_URL"]).path:
        raise HTTPException(
            503, "PUBLIC_BASE_URL must be an HTTPS origin without a path"
        )
    return cfg


@lru_cache(maxsize=1)
def redis_client() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
    )


def key(kind: str, token: str) -> str:
    return f"portal:{kind}:" + hashlib.sha256(token.encode()).hexdigest()


def put_token(kind: str, value: dict, ttl: int) -> str:
    token = secrets.token_urlsafe(32)
    try:
        redis_client().setex(key(kind, token), ttl, json.dumps(value))
    except RedisError:
        raise HTTPException(503, "Session service unavailable") from None
    return token


def consume_state(token: str) -> dict:
    try:
        value = redis_client().getdel(key("state", token))
    except RedisError:
        raise HTTPException(503, "Session service unavailable") from None
    if not value:
        raise HTTPException(
            401, "LTI state expired or already used; launch again from Canvas"
        )
    return json.loads(value)


@lru_cache(maxsize=4)
def jwks_client(url: str):
    return jwt.PyJWKClient(url, timeout=10, lifespan=300)


def validate_launch(encoded: str, state: dict, cfg: dict) -> dict:
    try:
        signing_key = jwks_client(cfg["LTI_JWKS_URL"]).get_signing_key_from_jwt(encoded)
        claims = jwt.decode(
            encoded,
            signing_key.key,
            algorithms=["RS256"],
            audience=cfg["LTI_CLIENT_ID"],
            issuer=cfg["LTI_ISSUER"],
            options={"require": ["iss", "aud", "exp", "iat", "sub", "nonce"]},
            leeway=30,
        )
        aud = claims["aud"]
        if ((isinstance(aud, list) and len(aud) > 1) or "azp" in claims) and claims.get(
            "azp"
        ) != cfg["LTI_CLIENT_ID"]:
            raise ValueError("azp")
        if claims["nonce"] != state["nonce"]:
            raise ValueError("nonce")
        expected = {
            "deployment_id": cfg["LTI_DEPLOYMENT_ID"],
            "version": "1.3.0",
            "message_type": "LtiResourceLinkRequest",
            "target_link_uri": cfg["PUBLIC_BASE_URL"] + "/lti/launch",
        }
        for name, value in expected.items():
            if claims.get(CLAIM + name) != value:
                raise ValueError(name)
        context = claims[CLAIM + "context"]
        if not isinstance(context.get("id"), str) or not context["id"]:
            raise ValueError("context")
        if not claims[CLAIM + "resource_link"].get("id"):
            raise ValueError("resource_link")
        course_id = str(claims[CLAIM + "custom"]["canvas_course_id"])
        allowed = {v.strip() for v in cfg["LTI_ALLOWED_COURSE_IDS"].split(",")}
        if not course_id.isdigit() or course_id not in allowed:
            raise ValueError("course not enabled for pilot")
        roles = claims[CLAIM + "roles"]
        if not isinstance(roles, list) or not all(
            isinstance(role, str) for role in roles
        ):
            raise ValueError("roles")
        role = (
            "teacher"
            if TEACHER_ROLES.intersection(roles)
            else "student"
            if LEARNER_ROLE in roles
            else None
        )
        if role is None:
            raise ValueError("unsupported role")
        return {
            "context_id": context["id"],
            "course_id": int(course_id),
            "role": role,
            "subject": claims["sub"],
            "title": str(context.get("title") or "Курс Canvas")[:200],
        }
    except (jwt.PyJWTError, ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(
            401, "Invalid LTI launch or course not enabled for pilot"
        ) from None


def current_session(authorization: str | None = Header(default=None)) -> dict:
    if (
        not authorization
        or not authorization.startswith("Bearer ")
        or len(authorization) > 256
    ):
        raise HTTPException(401, "Launch this tool from Canvas")
    try:
        raw = redis_client().get(key("session", authorization[7:]))
    except RedisError:
        raise HTTPException(503, "Session service unavailable") from None
    if not raw:
        raise HTTPException(401, "Session expired; launch again from Canvas")
    return json.loads(raw)


def require_teacher(session: dict) -> None:
    if session["role"] != "teacher":
        raise HTTPException(403, "Teacher access required")


def rate_limit(session: dict, action: str, limit: int) -> None:
    identity = f"{session['course_id']}:{session['subject']}:{action}"
    try:
        client = redis_client()
        # Atomic counter and expiry, also when several workers receive requests together.
        count = client.eval(
            "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],3600) end; return n",
            1,
            key("limit", identity),
        )
    except RedisError:
        raise HTTPException(503, "Rate limit service unavailable") from None
    if count > limit:
        raise HTTPException(429, "Hourly limit reached; try again later")
