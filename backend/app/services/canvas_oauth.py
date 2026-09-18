from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import urlencode, urlparse

from sqlalchemy.orm import Session

from ..models.models import (
    CanvasOAuthAttempt,
    CanvasOAuthConfiguration,
    CanvasOAuthConnection,
    CanvasOAuthEvent,
    Course,
    CourseMembership,
    LtiContextBinding,
    LtiProductSession,
    LtiRegistration,
    Organization,
    OrganizationMembership,
    User,
)
from .authorization import development_auth_available
from .canvas_simulator import canvas_simulator_enabled
from .canvas_sync import CANVAS_READ_SCOPES, CANVAS_SYNC_EXCLUDED_DATA, canvas_target
from .lti_registration import tool_public_origin
from .product_session import token_digest

ATTEMPT_TTL = timedelta(minutes=10)
FAKE_CONNECTION_TTL = timedelta(hours=1)


class CanvasOAuthError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        return_flow_kind: str | None = None,
        return_course_id: int | None = None,
    ):
        super().__init__(code)
        self.code = code
        self.return_flow_kind = return_flow_kind
        self.return_course_id = return_course_id


class EncryptedSecretStore(Protocol):
    """Opaque credential custody. Implementations must encrypt outside this app."""

    def put(self, reference: str, material: bytes) -> None: ...

    def contains(self, reference: str) -> bool: ...

    def delete(self, reference: str) -> None: ...


class UnavailableEncryptedSecretStore:
    def put(self, reference: str, material: bytes) -> None:
        del reference, material
        raise CanvasOAuthError("secret_store_unavailable")

    def contains(self, reference: str) -> bool:
        del reference
        return False

    def delete(self, reference: str) -> None:
        del reference


class InMemoryDevelopmentSecretStore:
    """Process-local fake custody. It is never selected outside safe development."""

    def __init__(self) -> None:
        self._values: dict[str, bytes] = {}
        self._lock = threading.Lock()

    def put(self, reference: str, material: bytes) -> None:
        if not development_auth_available():
            raise CanvasOAuthError("secret_store_unavailable")
        if not reference or not material:
            raise CanvasOAuthError("secret_store_unavailable")
        with self._lock:
            self._values[reference] = bytes(material)

    def contains(self, reference: str) -> bool:
        if not development_auth_available():
            return False
        with self._lock:
            return reference in self._values

    def delete(self, reference: str) -> None:
        with self._lock:
            value = self._values.pop(reference, None)
        if value is not None:
            value = b"\x00" * len(value)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


@dataclass(frozen=True)
class FakeExchangeGrant:
    credential_material: bytes
    granted_scopes: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True)
class CanvasOAuthCompletion:
    result: str
    organization_id: int
    registration_id: int
    flow_kind: str = "admin"
    course_id: int | None = None


class CanvasCodeExchanger(Protocol):
    def exchange(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        oauth_client_id: str,
        requested_scopes: tuple[str, ...],
    ) -> FakeExchangeGrant: ...


class UnavailableCanvasCodeExchanger:
    def exchange(self, **kwargs) -> FakeExchangeGrant:
        del kwargs
        raise CanvasOAuthError("production_connection_disabled")


class FakeCanvasCodeExchanger:
    """Verifies a local code and returns random, non-token fake material."""

    def __init__(self) -> None:
        self._signing_key = secrets.token_bytes(32)

    def issue_code(self, *, state: str, redirect_uri: str) -> str:
        message = f"{state}\n{redirect_uri}".encode()
        return hmac.new(self._signing_key, message, hashlib.sha256).hexdigest()

    def exchange(
        self,
        *,
        code: str,
        state: str,
        redirect_uri: str,
        oauth_client_id: str,
        requested_scopes: tuple[str, ...],
    ) -> FakeExchangeGrant:
        del oauth_client_id
        if not development_auth_available():
            raise CanvasOAuthError("production_connection_disabled")
        expected = self.issue_code(state=state, redirect_uri=redirect_uri)
        if not hmac.compare_digest(code, expected):
            raise CanvasOAuthError("authorization_code_invalid")
        if requested_scopes != CANVAS_READ_SCOPES:
            raise CanvasOAuthError("authorization_scope_mismatch")
        return FakeExchangeGrant(
            credential_material=secrets.token_bytes(32),
            granted_scopes=CANVAS_READ_SCOPES,
            expires_at=_utcnow() + FAKE_CONNECTION_TTL,
        )


_unavailable_store = UnavailableEncryptedSecretStore()
_development_store = InMemoryDevelopmentSecretStore()
_unavailable_exchanger = UnavailableCanvasCodeExchanger()
_development_exchanger = FakeCanvasCodeExchanger()


def get_canvas_secret_store() -> EncryptedSecretStore:
    if development_auth_available():
        return _development_store
    return _unavailable_store


def get_canvas_code_exchanger() -> CanvasCodeExchanger:
    if development_auth_available():
        return _development_exchanger
    return _unavailable_exchanger


def development_code_exchanger() -> FakeCanvasCodeExchanger:
    if not development_auth_available():
        raise CanvasOAuthError("production_connection_disabled")
    return _development_exchanger


def reset_development_canvas_oauth() -> None:
    """Test helper: remove only process-local fake custody."""

    _development_store.clear()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _connection_has_exact_scopes(
    connection: CanvasOAuthConnection | None,
) -> bool:
    try:
        return bool(
            connection
            and frozenset(connection.granted_scopes) == frozenset(CANVAS_READ_SCOPES)
        )
    except (TypeError, ValueError):
        return False


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def validate_canvas_api_origin(value: str) -> str:
    origin = value.strip()
    parsed = urlparse(origin)
    try:
        port = parsed.port
    except ValueError as exc:
        raise CanvasOAuthError("canvas_api_origin_invalid") from exc
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or value != origin
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.params
        or parsed.query
        or parsed.fragment
        or hostname.endswith(".")
        or hostname == "localhost"
        or "%" in origin
    ):
        raise CanvasOAuthError("canvas_api_origin_invalid")
    try:
        hostname.encode("ascii")
    except UnicodeEncodeError as exc:
        raise CanvasOAuthError("canvas_api_origin_invalid") from exc
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if re.fullmatch(r"[0-9.]+", hostname) or len(hostname) > 253:
            raise CanvasOAuthError("canvas_api_origin_invalid")
        labels = hostname.split(".")
        if any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in labels
        ):
            raise CanvasOAuthError("canvas_api_origin_invalid")
    else:
        if address.compressed.lower() != hostname:
            raise CanvasOAuthError("canvas_api_origin_invalid")
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    canonical = f"https://{rendered_host}"
    if port is not None:
        if port == 443:
            raise CanvasOAuthError("canvas_api_origin_invalid")
        canonical = f"{canonical}:{port}"
    if origin != canonical:
        raise CanvasOAuthError("canvas_api_origin_invalid")
    return canonical


def validate_oauth_client_id(value: str) -> str:
    client_id = value.strip()
    if (
        not client_id
        or len(client_id) > 255
        or client_id != value
        or any(character.isspace() for character in client_id)
    ):
        raise CanvasOAuthError("oauth_client_id_invalid")
    return client_id


def canvas_oauth_callback_uri() -> str:
    return f"{tool_public_origin()}/integrations/canvas/oauth/callback"


def _frontend_origin() -> str:
    default = "http://localhost:3000"
    origin = os.getenv("FRONTEND_PUBLIC_URL", default).strip().rstrip("/")
    parsed = urlparse(origin)
    production = os.getenv("APP_ENV", "development").strip().lower() == "production"
    if (
        parsed.scheme not in ({"https"} if production else {"http", "https"})
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise CanvasOAuthError("frontend_origin_invalid")
    return origin


def canvas_oauth_return_url(
    result: str,
    *,
    organization_id: int | None = None,
    registration_id: int | None = None,
    flow_kind: str = "admin",
    course_id: int | None = None,
) -> str:
    bounded = result if result in {"connected", "denied", "failed"} else "failed"
    if flow_kind == "instructor" and course_id is not None and course_id > 0:
        params = {"lti": "1", "canvas_oauth": bounded}
        return (
            f"{_frontend_origin()}/workspace/courses/{course_id}?"
            f"{urlencode(params)}"
        )
    params: dict[str, str | int] = {"canvas_oauth": bounded}
    if organization_id is not None and registration_id is not None:
        params["organization"] = organization_id
        params["canvas_registration"] = registration_id
    return f"{_frontend_origin()}/workspace/integrations/lti?{urlencode(params)}"


def _registration(
    db: Session, *, organization_id: int, registration_id: int
) -> LtiRegistration:
    row = db.get(LtiRegistration, registration_id)
    if row is None or row.organization_id != organization_id or row.is_development:
        raise CanvasOAuthError("registration_unavailable")
    return row


def _instructor_context(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    product_session_id: int,
    course_id: int,
    raw_session_token: str | None,
    expected_canvas_origin: str | None = None,
    expected_canvas_course_id: str | None = None,
    lock: bool,
    allow_synthetic_target: bool = False,
) -> tuple[Course, str, str] | None:
    if not raw_session_token or len(raw_session_token) > 200:
        return None
    # Keep the PostgreSQL lock order aligned with product-session issuance:
    # registration -> product session -> context rows -> OAuth configuration.
    registration_query = db.query(LtiRegistration).filter(
        LtiRegistration.id == registration_id,
        LtiRegistration.organization_id == organization_id,
        LtiRegistration.is_active.is_(True),
    )
    if lock:
        registration_query = registration_query.with_for_update()
    registration = registration_query.first()
    if registration is None:
        return None

    session_query = db.query(LtiProductSession).filter(
        LtiProductSession.id == product_session_id,
        LtiProductSession.registration_id == registration_id,
        LtiProductSession.user_id == user_id,
        LtiProductSession.course_id == course_id,
        LtiProductSession.role == "instructor",
        LtiProductSession.revoked_at.is_(None),
    )
    if lock:
        session_query = session_query.with_for_update()
    product_session = session_query.first()
    if (
        product_session is None
        or _aware(product_session.expires_at) <= _utcnow()
        or not hmac.compare_digest(
            product_session.token_digest, token_digest(raw_session_token)
        )
    ):
        return None

    organization_query = db.query(Organization).filter(
        Organization.id == organization_id,
        Organization.is_active.is_(True),
    )
    user_query = db.query(User).filter(User.id == user_id, User.is_active.is_(True))
    course_query = db.query(Course).filter(
        Course.id == course_id,
        Course.organization_id == organization_id,
    )
    membership_query = db.query(CourseMembership).filter(
        CourseMembership.organization_id == organization_id,
        CourseMembership.course_id == course_id,
        CourseMembership.user_id == user_id,
        CourseMembership.role == "instructor",
        CourseMembership.is_active.is_(True),
    )
    binding_query = db.query(LtiContextBinding).filter(
        LtiContextBinding.registration_id == registration_id,
        LtiContextBinding.course_id == course_id,
    )
    if lock:
        organization_query = organization_query.with_for_update()
        user_query = user_query.with_for_update()
        course_query = course_query.with_for_update()
        membership_query = membership_query.with_for_update()
        binding_query = binding_query.with_for_update()
    organization = organization_query.first()
    user = user_query.first()
    course = course_query.first()
    membership = membership_query.first()
    binding = binding_query.first()
    if any(
        item is None
        for item in (registration, organization, user, course, membership, binding)
    ):
        return None
    assert course is not None
    target = canvas_target(course)
    if target is None and allow_synthetic_target and canvas_simulator_enabled():
        metadata = (
            course.source_metadata if isinstance(course.source_metadata, dict) else {}
        )
        fixture_id = metadata.get("canvas_simulator_fixture")
        parsed_source = urlparse(course.source_url or "")
        if (
            metadata.get("synthetic") is True
            and fixture_id in {"demo-ai", "demo-review"}
            and course.external_id == f"canvas-simulator:{fixture_id}"
            and parsed_source.scheme == "http"
            and parsed_source.hostname in {"localhost", "127.0.0.1"}
            and parsed_source.username is None
            and parsed_source.password is None
            and parsed_source.path == f"/canvas-simulator/courses/{fixture_id}"
        ):
            target = (f"{parsed_source.scheme}://{parsed_source.netloc}", fixture_id)
    if target is None:
        return None
    canvas_origin, canvas_course_id = target
    if (
        expected_canvas_origin is not None and canvas_origin != expected_canvas_origin
    ) or (
        expected_canvas_course_id is not None
        and canvas_course_id != expected_canvas_course_id
    ):
        return None
    return course, canvas_origin, canvas_course_id


def _completion(attempt: CanvasOAuthAttempt, result: str) -> CanvasOAuthCompletion:
    return CanvasOAuthCompletion(
        result=result,
        organization_id=attempt.organization_id,
        registration_id=attempt.registration_id,
        flow_kind=attempt.flow_kind,
        course_id=attempt.course_id,
    )


def _callback_changed(attempt: CanvasOAuthAttempt) -> CanvasOAuthError:
    return CanvasOAuthError(
        "callback_authorization_changed",
        return_flow_kind=attempt.flow_kind,
        return_course_id=attempt.course_id,
    )


def _callback_error(
    attempt: CanvasOAuthAttempt, error: CanvasOAuthError
) -> CanvasOAuthError:
    if attempt.flow_kind != "instructor":
        return error
    return CanvasOAuthError(
        error.code,
        return_flow_kind=attempt.flow_kind,
        return_course_id=attempt.course_id,
    )


def save_canvas_oauth_configuration(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    actor_user_id: int,
    canvas_api_origin: str,
    oauth_client_id: str,
    expected_version: int | None,
) -> dict:
    _registration(db, organization_id=organization_id, registration_id=registration_id)
    origin = validate_canvas_api_origin(canvas_api_origin)
    client_id = validate_oauth_client_id(oauth_client_id)
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(CanvasOAuthConfiguration.registration_id == registration_id)
        .with_for_update()
        .first()
    )
    if configuration is None:
        if expected_version is not None:
            raise CanvasOAuthError("configuration_conflict")
        configuration = CanvasOAuthConfiguration(
            registration_id=registration_id,
            organization_id=organization_id,
            canvas_api_origin=origin,
            oauth_client_id=client_id,
            version=1,
        )
        db.add(configuration)
    else:
        if expected_version != configuration.version:
            raise CanvasOAuthError("configuration_conflict")
        if (
            configuration.canvas_api_origin == origin
            and configuration.oauth_client_id == client_id
        ):
            return _configuration_out(configuration)
        active_connection = (
            db.query(CanvasOAuthConnection.id)
            .filter(
                CanvasOAuthConnection.registration_id == registration_id,
                CanvasOAuthConnection.revoked_at.is_(None),
            )
            .first()
        )
        if active_connection is not None:
            raise CanvasOAuthError("disconnect_before_configuration_change")
        configuration.canvas_api_origin = origin
        configuration.oauth_client_id = client_id
        configuration.version += 1
    db.add(
        CanvasOAuthEvent(
            organization_id=organization_id,
            registration_id=registration_id,
            actor_user_id=actor_user_id,
            event_type="configured",
        )
    )
    db.commit()
    db.refresh(configuration)
    return _configuration_out(configuration)


def _configuration_out(configuration: CanvasOAuthConfiguration) -> dict:
    return {
        "canvas_api_origin": configuration.canvas_api_origin,
        "oauth_client_id": configuration.oauth_client_id,
        "version": configuration.version,
    }


def canvas_oauth_status(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    store: EncryptedSecretStore,
) -> dict:
    _registration(db, organization_id=organization_id, registration_id=registration_id)
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == registration_id,
            CanvasOAuthConfiguration.organization_id == organization_id,
        )
        .first()
    )
    connection = (
        db.query(CanvasOAuthConnection)
        .filter(
            CanvasOAuthConnection.registration_id == registration_id,
            CanvasOAuthConnection.organization_id == organization_id,
            CanvasOAuthConnection.user_id == user_id,
            CanvasOAuthConnection.revoked_at.is_(None),
        )
        .first()
    )
    fake_available = development_auth_available()
    if configuration is None:
        state = "not_configured"
    elif not fake_available:
        state = "production_disabled"
    elif connection is None:
        state = "ready_to_connect"
    elif (
        _aware(connection.expires_at) <= _utcnow()
        or not _connection_has_exact_scopes(connection)
        or not store.contains(connection.vault_reference)
    ):
        state = "reconnect_required"
    else:
        state = "connected"
    return {
        "schema_version": 1,
        "registration_id": registration_id,
        "production_connection_enabled": False,
        "fake_flow_available": fake_available,
        "callback_uri": canvas_oauth_callback_uri(),
        "required_scopes": list(CANVAS_READ_SCOPES),
        "excluded_data": list(CANVAS_SYNC_EXCLUDED_DATA),
        "configuration": _configuration_out(configuration) if configuration else None,
        "connection": {
            "state": state,
            "owner": "current_user",
            "mode": connection.connection_mode if connection else None,
            "granted_scopes": list(connection.granted_scopes) if connection else [],
            "expires_at": connection.expires_at if connection else None,
            "connected_at": connection.connected_at if connection else None,
        },
    }


def start_canvas_oauth(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
) -> dict:
    if not development_auth_available():
        raise CanvasOAuthError("production_connection_disabled")
    _registration(db, organization_id=organization_id, registration_id=registration_id)
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == registration_id,
            CanvasOAuthConfiguration.organization_id == organization_id,
        )
        .first()
    )
    if configuration is None:
        raise CanvasOAuthError("oauth_configuration_required")
    return _create_canvas_oauth_attempt(
        db,
        configuration=configuration,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        flow_kind="admin",
    )


def _create_canvas_oauth_attempt(
    db: Session,
    *,
    configuration: CanvasOAuthConfiguration,
    organization_id: int,
    registration_id: int,
    user_id: int,
    flow_kind: str,
    product_session_id: int | None = None,
    course_id: int | None = None,
    canvas_course_id: str | None = None,
) -> dict:
    state = secrets.token_urlsafe(32)
    expires_at = _utcnow() + ATTEMPT_TTL
    redirect_uri = canvas_oauth_callback_uri()
    attempt = CanvasOAuthAttempt(
        registration_id=registration_id,
        organization_id=organization_id,
        user_id=user_id,
        flow_kind=flow_kind,
        product_session_id=product_session_id,
        course_id=course_id,
        canvas_course_id=canvas_course_id,
        state_digest=_digest(state),
        redirect_uri=redirect_uri,
        canvas_api_origin=configuration.canvas_api_origin,
        oauth_client_id=configuration.oauth_client_id,
        requested_scopes=list(CANVAS_READ_SCOPES),
        expires_at=expires_at,
    )
    db.add(attempt)
    db.commit()
    authorization_url = "/integrations/canvas/oauth/development/authorize?" + urlencode(
        {
            "client_id": configuration.oauth_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": " ".join(CANVAS_READ_SCOPES),
        }
    )
    return {
        "schema_version": 1,
        "authorization_url": authorization_url,
        "expires_at": expires_at,
    }


def instructor_canvas_oauth_status(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    product_session_id: int,
    course_id: int,
    raw_session_token: str | None,
    store: EncryptedSecretStore,
) -> dict:
    context = _instructor_context(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        product_session_id=product_session_id,
        course_id=course_id,
        raw_session_token=raw_session_token,
        allow_synthetic_target=True,
        lock=False,
    )
    if context is None:
        raise CanvasOAuthError("instructor_handoff_unavailable")
    course, canvas_origin, _ = context
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == registration_id,
            CanvasOAuthConfiguration.organization_id == organization_id,
        )
        .first()
    )
    connection = (
        db.query(CanvasOAuthConnection)
        .filter(
            CanvasOAuthConnection.registration_id == registration_id,
            CanvasOAuthConnection.organization_id == organization_id,
            CanvasOAuthConnection.user_id == user_id,
            CanvasOAuthConnection.revoked_at.is_(None),
        )
        .first()
    )
    metadata = (
        course.source_metadata if isinstance(course.source_metadata, dict) else {}
    )
    synthetic_simulator = (
        canvas_simulator_enabled()
        and metadata.get("synthetic") is True
        and metadata.get("canvas_simulator_fixture") in {"demo-ai", "demo-review"}
    )
    fake_available = development_auth_available() and not synthetic_simulator
    if synthetic_simulator:
        state = "production_disabled"
    elif configuration is None:
        state = "configuration_required"
    elif configuration.canvas_api_origin != canvas_origin:
        state = "configuration_mismatch"
    elif not fake_available:
        state = "production_disabled"
    elif connection is None:
        state = "ready_to_connect"
    elif (
        connection.canvas_api_origin != canvas_origin
        or _aware(connection.expires_at) <= _utcnow()
        or not _connection_has_exact_scopes(connection)
        or not store.contains(connection.vault_reference)
    ):
        state = "reconnect_required"
    else:
        state = "connected"
    return {
        "schema_version": 1,
        "state": state,
        "fake_flow_available": fake_available,
        "read_only": True,
        "required_scopes": list(CANVAS_READ_SCOPES),
        "excluded_data": list(CANVAS_SYNC_EXCLUDED_DATA),
        "connection": {
            "mode": connection.connection_mode if connection else None,
            "connected_at": connection.connected_at if connection else None,
            "expires_at": connection.expires_at if connection else None,
        },
    }


def start_instructor_canvas_oauth(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    product_session_id: int,
    course_id: int,
    raw_session_token: str | None,
) -> dict:
    if not development_auth_available():
        raise CanvasOAuthError("production_connection_disabled")
    context = _instructor_context(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        product_session_id=product_session_id,
        course_id=course_id,
        raw_session_token=raw_session_token,
        lock=True,
    )
    if context is None:
        db.rollback()
        raise CanvasOAuthError("instructor_handoff_unavailable")
    _, canvas_origin, canvas_course_id = context
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == registration_id,
            CanvasOAuthConfiguration.organization_id == organization_id,
        )
        .with_for_update()
        .first()
    )
    if configuration is None:
        db.rollback()
        raise CanvasOAuthError("oauth_configuration_required")
    if configuration.canvas_api_origin != canvas_origin:
        db.rollback()
        raise CanvasOAuthError("oauth_configuration_mismatch")
    return _create_canvas_oauth_attempt(
        db,
        configuration=configuration,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        flow_kind="instructor",
        product_session_id=product_session_id,
        course_id=course_id,
        canvas_course_id=canvas_course_id,
    )


def validate_development_authorization_request(
    db: Session,
    *,
    state: str,
    client_id: str,
    response_type: str,
    redirect_uri: str,
    scope: str,
) -> CanvasOAuthAttempt:
    if not development_auth_available():
        raise CanvasOAuthError("production_connection_disabled")
    if not state or len(state) > 200:
        raise CanvasOAuthError("authorization_request_invalid")
    attempt = (
        db.query(CanvasOAuthAttempt)
        .filter(CanvasOAuthAttempt.state_digest == _digest(state))
        .first()
    )
    if (
        attempt is None
        or attempt.consumed_at is not None
        or _aware(attempt.expires_at) <= _utcnow()
        or response_type != "code"
        or client_id != attempt.oauth_client_id
        or redirect_uri != attempt.redirect_uri
        or scope != " ".join(CANVAS_READ_SCOPES)
        or tuple(attempt.requested_scopes) != CANVAS_READ_SCOPES
    ):
        raise CanvasOAuthError("authorization_request_invalid")
    return attempt


def _connection_owner_is_active(
    db: Session, *, organization_id: int, user_id: int, lock: bool
) -> bool:
    user_query = db.query(User.id).filter(User.id == user_id, User.is_active.is_(True))
    membership_query = db.query(OrganizationMembership.id).filter(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.user_id == user_id,
        OrganizationMembership.role == "administrator",
        OrganizationMembership.is_active.is_(True),
    )
    if lock:
        user_query = user_query.with_for_update()
        membership_query = membership_query.with_for_update()
    return user_query.first() is not None and membership_query.first() is not None


def _attempt_owner_is_active(
    db: Session,
    *,
    attempt: CanvasOAuthAttempt,
    raw_product_session_token: str | None,
    lock: bool,
) -> bool:
    if attempt.flow_kind == "admin":
        return _connection_owner_is_active(
            db,
            organization_id=attempt.organization_id,
            user_id=attempt.user_id,
            lock=lock,
        )
    if (
        attempt.flow_kind != "instructor"
        or attempt.product_session_id is None
        or attempt.course_id is None
        or attempt.canvas_course_id is None
    ):
        return False
    return (
        _instructor_context(
            db,
            organization_id=attempt.organization_id,
            registration_id=attempt.registration_id,
            user_id=attempt.user_id,
            product_session_id=attempt.product_session_id,
            course_id=attempt.course_id,
            raw_session_token=raw_product_session_token,
            expected_canvas_origin=attempt.canvas_api_origin,
            expected_canvas_course_id=attempt.canvas_course_id,
            lock=lock,
        )
        is not None
    )


def development_authorization_redirect(
    db: Session,
    *,
    state: str,
    client_id: str,
    response_type: str,
    redirect_uri: str,
    scope: str,
    decision: str,
    exchanger: FakeCanvasCodeExchanger,
) -> CanvasOAuthCompletion:
    validate_development_authorization_request(
        db,
        state=state,
        client_id=client_id,
        response_type=response_type,
        redirect_uri=redirect_uri,
        scope=scope,
    )
    if decision == "deny":
        params = {"error": "access_denied", "state": state}
    elif decision == "allow":
        params = {
            "code": exchanger.issue_code(state=state, redirect_uri=redirect_uri),
            "state": state,
        }
    else:
        raise CanvasOAuthError("authorization_request_invalid")
    return f"{redirect_uri}?{urlencode(params)}"


def complete_canvas_oauth_callback(
    db: Session,
    *,
    state: str,
    code: str | None,
    error: str | None,
    exchanger: CanvasCodeExchanger,
    store: EncryptedSecretStore,
    raw_product_session_token: str | None = None,
) -> CanvasOAuthCompletion:
    if not development_auth_available():
        raise CanvasOAuthError("production_connection_disabled")
    if (
        not state
        or len(state) > 200
        or bool(code) == bool(error)
        or (error is not None and error != "access_denied")
    ):
        raise CanvasOAuthError("callback_invalid")
    attempt = (
        db.query(CanvasOAuthAttempt)
        .filter(CanvasOAuthAttempt.state_digest == _digest(state))
        .with_for_update()
        .first()
    )
    now = _utcnow()
    if (
        attempt is None
        or attempt.consumed_at is not None
        or _aware(attempt.expires_at) <= now
        or tuple(attempt.requested_scopes) != CANVAS_READ_SCOPES
        or attempt.redirect_uri != canvas_oauth_callback_uri()
    ):
        raise CanvasOAuthError("callback_invalid")
    configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == attempt.registration_id,
            CanvasOAuthConfiguration.organization_id == attempt.organization_id,
        )
        .first()
    )
    registration = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.id == attempt.registration_id,
            LtiRegistration.organization_id == attempt.organization_id,
        )
        .first()
    )
    if (
        registration is None
        or (
            registration.is_development
            and not (attempt.flow_kind == "instructor" and development_auth_available())
        )
        or configuration is None
        or configuration.canvas_api_origin != attempt.canvas_api_origin
        or configuration.oauth_client_id != attempt.oauth_client_id
    ):
        attempt.consumed_at = now
        db.commit()
        if attempt.flow_kind == "instructor":
            raise _callback_changed(attempt)
        raise CanvasOAuthError("callback_invalid")
    if not _attempt_owner_is_active(
        db,
        attempt=attempt,
        raw_product_session_token=raw_product_session_token,
        lock=False,
    ):
        attempt.consumed_at = now
        db.commit()
        raise _callback_changed(attempt)
    attempt.consumed_at = now
    db.commit()
    if error == "access_denied":
        return _completion(attempt, "denied")
    assert code is not None
    try:
        grant = exchanger.exchange(
            code=code,
            state=state,
            redirect_uri=attempt.redirect_uri,
            oauth_client_id=attempt.oauth_client_id,
            requested_scopes=tuple(attempt.requested_scopes),
        )
    except CanvasOAuthError as exc:
        raise _callback_error(attempt, exc) from exc

    # Lock the owner context before configuration everywhere. Start and
    # disconnect use this same order, preventing callback/start inversion.
    owner_is_active = _attempt_owner_is_active(
        db,
        attempt=attempt,
        raw_product_session_token=raw_product_session_token,
        lock=True,
    )
    current_configuration = (
        db.query(CanvasOAuthConfiguration)
        .filter(
            CanvasOAuthConfiguration.registration_id == attempt.registration_id,
            CanvasOAuthConfiguration.organization_id == attempt.organization_id,
        )
        .with_for_update()
        .populate_existing()
        .first()
    )
    if (
        current_configuration is None
        or current_configuration.canvas_api_origin != attempt.canvas_api_origin
        or current_configuration.oauth_client_id != attempt.oauth_client_id
        or not owner_is_active
    ):
        db.rollback()
        raise _callback_changed(attempt)
    reference = f"canvas-fake-{secrets.token_urlsafe(24)}"
    try:
        store.put(reference, grant.credential_material)
    except CanvasOAuthError as exc:
        db.rollback()
        raise _callback_error(attempt, exc) from exc
    prior_reference: str | None = None
    try:
        connection = (
            db.query(CanvasOAuthConnection)
            .filter(
                CanvasOAuthConnection.registration_id == attempt.registration_id,
                CanvasOAuthConnection.user_id == attempt.user_id,
            )
            .with_for_update()
            .first()
        )
        if connection is None:
            connection = CanvasOAuthConnection(
                registration_id=attempt.registration_id,
                organization_id=attempt.organization_id,
                user_id=attempt.user_id,
                canvas_api_origin=attempt.canvas_api_origin,
                granted_scopes=list(grant.granted_scopes),
                vault_reference=reference,
                connection_mode="fake_development",
                expires_at=grant.expires_at,
                connected_at=now,
            )
            db.add(connection)
        else:
            prior_reference = connection.vault_reference
            connection.canvas_api_origin = attempt.canvas_api_origin
            connection.granted_scopes = list(grant.granted_scopes)
            connection.vault_reference = reference
            connection.connection_mode = "fake_development"
            connection.expires_at = grant.expires_at
            connection.connected_at = now
            connection.revoked_at = None
        db.add(
            CanvasOAuthEvent(
                organization_id=attempt.organization_id,
                registration_id=attempt.registration_id,
                actor_user_id=attempt.user_id,
                event_type="connected",
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        store.delete(reference)
        raise
    if prior_reference and prior_reference != reference:
        store.delete(prior_reference)
    return _completion(attempt, "connected")


def disconnect_canvas_oauth(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    store: EncryptedSecretStore,
    allow_development_registration: bool = False,
) -> dict:
    if allow_development_registration and development_auth_available():
        registration = db.get(LtiRegistration, registration_id)
        if registration is None or registration.organization_id != organization_id:
            raise CanvasOAuthError("registration_unavailable")
    else:
        _registration(
            db,
            organization_id=organization_id,
            registration_id=registration_id,
        )
    connection = (
        db.query(CanvasOAuthConnection)
        .filter(
            CanvasOAuthConnection.registration_id == registration_id,
            CanvasOAuthConnection.organization_id == organization_id,
            CanvasOAuthConnection.user_id == user_id,
            CanvasOAuthConnection.revoked_at.is_(None),
        )
        .with_for_update()
        .first()
    )
    if connection is None:
        return {"schema_version": 1, "state": "disconnected"}
    connection.revoked_at = _utcnow()
    reference = connection.vault_reference
    db.add(
        CanvasOAuthEvent(
            organization_id=organization_id,
            registration_id=registration_id,
            actor_user_id=user_id,
            event_type="disconnected",
        )
    )
    db.commit()
    store.delete(reference)
    return {"schema_version": 1, "state": "disconnected"}


def disconnect_instructor_canvas_oauth(
    db: Session,
    *,
    organization_id: int,
    registration_id: int,
    user_id: int,
    product_session_id: int,
    course_id: int,
    raw_session_token: str | None,
    store: EncryptedSecretStore,
) -> dict:
    context = _instructor_context(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        product_session_id=product_session_id,
        course_id=course_id,
        raw_session_token=raw_session_token,
        lock=True,
    )
    if context is None:
        db.rollback()
        raise CanvasOAuthError("instructor_handoff_unavailable")
    return disconnect_canvas_oauth(
        db,
        organization_id=organization_id,
        registration_id=registration_id,
        user_id=user_id,
        store=store,
        allow_development_registration=True,
    )
