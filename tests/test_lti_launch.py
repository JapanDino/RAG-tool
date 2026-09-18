import inspect
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app, configured_cors
from backend.app.models.base import Base
from backend.app.models.models import (
    Course,
    CourseMembership,
    Dataset,
    LtiBindingCandidate,
    LtiLaunchAttempt,
    LtiLaunchAuditEvent,
    LtiProductSession,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.routers.lti import lti_launch
from backend.app.services import lti as lti_service
from backend.app.services.lti import (
    CONTEXT,
    DEPLOYMENT_ID,
    MESSAGE_TYPE,
    RESOURCE_LINK,
    ROLES,
    TARGET_LINK_URI,
    VERSION,
    validate_lti_endpoint,
)
from backend.app.services.lti_development import (
    LOCAL_KEY_ID,
    local_jwks,
    local_private_key,
)
from backend.app.services.product_session import (
    csrf_token_for_session,
    session_cookie_policy,
    token_digest,
)


class _JwksResponse:
    content = b"local-jwks"

    def raise_for_status(self):
        return None

    def json(self):
        return local_jwks()


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        lti_service.requests, "get", lambda *args, **kwargs: _JwksResponse()
    )
    client = TestClient(app)
    with Session() as db:
        organization = Organization(slug="lti-school", name="Школа LTI")
        dataset = Dataset(name="lti-course")
        db.add_all([organization, dataset])
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            title="Алгоритмы и структуры данных",
            source_type="manual",
        )
        db.add(course)
        db.flush()
        rows = []
        for email, name, role in (
            ("student@lti.test", "Алина Соколова", "student"),
            ("teacher@lti.test", "Михаил Орлов", "instructor"),
            ("designer@lti.test", "Даниил Лебедев", "program_designer"),
            ("admin@lti.test", "Ольга Белова", "administrator"),
        ):
            user = User(email=email, display_name=name, is_active=True)
            db.add(user)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=role,
                    is_active=True,
                )
            )
            if role != "administrator":
                db.add(
                    CourseMembership(
                        organization_id=organization.id,
                        course_id=course.id,
                        user_id=user.id,
                        role=role,
                        is_active=True,
                    )
                )
            rows.append((user.id, email, role))
        db.commit()
        course_id = course.id
    bootstrap = client.post(
        "/integrations/lti/development/bootstrap",
        headers={"X-Dev-User": "admin@lti.test"},
        json={"course_id": course_id, "public_base_url": "http://testserver"},
    )
    assert bootstrap.status_code == 201, bootstrap.text
    return client, Session, engine, bootstrap.json(), rows


def _authorization_request(client, registration_id, subject):
    start = client.get(
        "/integrations/lti/development/start",
        params={"registration_id": registration_id, "subject": subject},
        follow_redirects=False,
    )
    assert start.status_code == 302
    login = client.get(start.headers["location"], follow_redirects=False)
    assert login.status_code == 302
    parsed = urlparse(login.headers["location"])
    return parsed.path, {
        key: values[0] for key, values in parse_qs(parsed.query).items()
    }


def _token_from_authorize(client, path, params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    state = re.search(r'name="state" value="([^"]+)"', response.text).group(1)
    token = re.search(r'name="id_token" value="([^"]+)"', response.text).group(1)
    return state, token


def _subject_for(Session, registration_id, email):
    from backend.app.models.models import LtiSubjectBinding

    with Session() as db:
        user = db.query(User).filter(User.email == email).one()
        binding = (
            db.query(LtiSubjectBinding)
            .filter(
                LtiSubjectBinding.registration_id == registration_id,
                LtiSubjectBinding.user_id == user.id,
            )
            .one()
        )
        return binding.platform_subject


def _launch_as(client, Session, registration_id, email):
    subject = _subject_for(Session, registration_id, email)
    path, params = _authorization_request(client, registration_id, subject)
    state, token = _token_from_authorize(client, path, params)
    return client.post(
        "/integrations/lti/launch", data={"state": state, "id_token": token}
    )


@pytest.mark.parametrize(
    ("email", "expected_name", "expected_role"),
    (
        ("student@lti.test", "Алина Соколова", "Ученик"),
        ("teacher@lti.test", "Михаил Орлов", "Преподаватель"),
        ("designer@lti.test", "Даниил Лебедев", "Архитектор программы"),
        ("admin@lti.test", "Ольга Белова", "Администратор"),
    ),
)
def test_bound_learner_and_instructor_complete_local_lti_flow(
    monkeypatch, email, expected_name, expected_role
):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(Session, bootstrap["registration_id"], email)
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        assert params["scope"] == "openid"
        assert params["response_type"] == "id_token"
        assert params["response_mode"] == "form_post"
        assert params["prompt"] == "none"
        assert params["client_id"] == "rag-tool-local"
        assert params["redirect_uri"] == "http://testserver/integrations/lti/launch"

        state, token = _token_from_authorize(client, path, params)
        launched = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert launched.status_code == 200
        assert "Запуск подтверждён" in launched.text
        assert expected_name in launched.text
        assert expected_role in launched.text
        assert "Алгоритмы и структуры данных" in launched.text
        assert "Canvas не изменён" in launched.text
        assert launched.headers["cache-control"].startswith("no-store")

        replay = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert replay.status_code == 403
        assert expected_name not in replay.text
        with Session() as db:
            reasons = [row.reason_code for row in db.query(LtiLaunchAuditEvent).all()]
            assert reasons == ["launch_verified"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    ("email", "destination"),
    (
        ("student@lti.test", "/canvas-companion"),
        ("teacher@lti.test", "?lti=1"),
    ),
)
def test_supported_launch_issues_scoped_http_only_session(
    monkeypatch, email, destination
):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        launched = _launch_as(client, Session, bootstrap["registration_id"], email)
        assert launched.status_code == 200
        assert "Открыть курс" in launched.text
        assert destination in launched.text
        set_cookie = launched.headers["set-cookie"]
        assert "rag_lti_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=lax" in set_cookie
        assert "Path=/" in set_cookie
        assert "Secure" not in set_cookie
        raw_token = client.cookies.get("rag_lti_session")
        assert raw_token and raw_token not in launched.text

        with Session() as db:
            stored = db.query(LtiProductSession).one()
            assert stored.token_digest == token_digest(raw_token)
            assert raw_token not in repr(stored.__dict__)

        context = client.get("/identity/session")
        assert context.status_code == 200, context.text
        payload = context.json()
        assert payload["user"]["email"] == email
        assert payload["course"]["title"] == "Алгоритмы и структуры данных"
        assert payload["csrf_token"] == csrf_token_for_session(raw_token)
        assert context.headers["cache-control"].startswith("no-store")

        me = client.get("/identity/me")
        assert me.status_code == 200, me.text
        assert me.json()["auth_mode"] == "lti_session"
        assert [course["id"] for course in me.json()["courses"]] == [
            payload["course"]["id"]
        ]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("email", ("designer@lti.test", "admin@lti.test"))
def test_unsupported_roles_do_not_receive_product_session(monkeypatch, email):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        launched = _launch_as(client, Session, bootstrap["registration_id"], email)
        assert launched.status_code == 200
        assert "Открыть курс" not in launched.text
        assert "rag_lti_session" not in launched.headers.get("set-cookie", "")
        with Session() as db:
            assert db.query(LtiProductSession).count() == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_verified_unsupported_launch_clears_prior_product_session(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        assert (
            _launch_as(
                client,
                Session,
                bootstrap["registration_id"],
                "student@lti.test",
            ).status_code
            == 200
        )
        assert client.get("/identity/session").status_code == 200

        unsupported = _launch_as(
            client,
            Session,
            bootstrap["registration_id"],
            "admin@lti.test",
        )
        assert unsupported.status_code == 200
        assert "Открыть курс" not in unsupported.text
        assert "Max-Age=0" in unsupported.headers["set-cookie"]
        assert client.get("/identity/session").status_code == 401
        with Session() as db:
            sessions = db.query(LtiProductSession).all()
            assert len(sessions) == 1
            assert sessions[0].revoked_at is not None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_session_is_course_scoped_and_logout_is_csrf_protected(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        launched = _launch_as(
            client,
            Session,
            bootstrap["registration_id"],
            "student@lti.test",
        )
        assert launched.status_code == 200
        context = client.get("/identity/session").json()
        csrf = context["csrf_token"]
        course_id = context["course"]["id"]
        with Session() as db:
            user = db.query(User).filter(User.email == "student@lti.test").one()
            organization = db.query(Organization).one()
            dataset = Dataset(name="other-course")
            db.add(dataset)
            db.flush()
            other = Course(
                organization_id=organization.id,
                dataset_id=dataset.id,
                title="Другой курс",
                source_type="manual",
            )
            db.add(other)
            db.flush()
            db.add(
                CourseMembership(
                    organization_id=organization.id,
                    course_id=other.id,
                    user_id=user.id,
                    role="student",
                    is_active=True,
                )
            )
            db.commit()
            other_id = other.id
            organization_id = organization.id

        assert client.get(f"/courses/{course_id}").status_code == 200
        assert client.get(f"/courses/{other_id}").status_code == 404
        assert (
            client.get(f"/identity/organizations/{organization_id}/members").status_code
            == 404
        )
        assert client.post("/identity/session/logout").status_code == 403
        assert (
            client.post(
                "/identity/session/logout", headers={"X-CSRF-Token": "0" * 64}
            ).status_code
            == 403
        )
        logged_out = client.post(
            "/identity/session/logout", headers={"X-CSRF-Token": csrf}
        )
        assert logged_out.status_code == 204
        assert "Max-Age=0" in logged_out.headers["set-cookie"]
        assert client.get("/identity/session").status_code == 401
        with Session() as db:
            assert db.query(LtiProductSession).one().revoked_at is not None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_session_rechecks_expiry_and_membership(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        assert (
            _launch_as(
                client,
                Session,
                bootstrap["registration_id"],
                "student@lti.test",
            ).status_code
            == 200
        )
        with Session() as db:
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.role == "student")
                .one()
            )
            membership.is_active = False
            db.commit()
        assert client.get("/identity/session").status_code == 401

        with Session() as db:
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.role == "student")
                .one()
            )
            membership.is_active = True
            session = db.query(LtiProductSession).one()
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert client.get("/identity/session").status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_relaunch_revokes_previous_session_and_rejects_cross_session_csrf(
    monkeypatch,
):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        assert (
            _launch_as(
                client,
                Session,
                bootstrap["registration_id"],
                "student@lti.test",
            ).status_code
            == 200
        )
        first_context = client.get("/identity/session").json()
        first_csrf = first_context["csrf_token"]
        assert (
            _launch_as(
                client,
                Session,
                bootstrap["registration_id"],
                "student@lti.test",
            ).status_code
            == 200
        )
        second_context = client.get("/identity/session").json()
        assert second_context["csrf_token"] != first_csrf
        assert (
            client.post(
                "/identity/session/logout",
                headers={"X-CSRF-Token": first_csrf},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/identity/session/logout",
                headers={"X-CSRF-Token": second_context["csrf_token"]},
            ).status_code
            == 204
        )
        with Session() as db:
            sessions = db.query(LtiProductSession).order_by(LtiProductSession.id).all()
            assert len(sessions) == 2
            assert sessions[0].revoked_at is not None
            assert sessions[1].revoked_at is not None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_credentialed_cors_requires_explicit_origins(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    assert configured_cors() == (["*"], False)

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="must be explicit"):
        configured_cors()

    monkeypatch.setenv(
        "CORS_ALLOW_ORIGINS", "https://tool.school.test, https://review.school.test"
    )
    assert configured_cors() == (
        ["https://tool.school.test", "https://review.school.test"],
        True,
    )

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://tool.school.test,*")
    with pytest.raises(RuntimeError, match="exact HTTP"):
        configured_cors()


def test_credentialed_cors_middleware_does_not_reflect_hostile_origin(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://tool.school.test")
    origins, credentials = configured_cors()
    cors_app = FastAPI()
    cors_app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @cors_app.get("/context")
    def context():
        return {"ok": True}

    with TestClient(cors_app) as cors_client:
        trusted = cors_client.options(
            "/context",
            headers={
                "Origin": "https://tool.school.test",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert trusted.status_code == 200
        assert trusted.headers["access-control-allow-origin"] == (
            "https://tool.school.test"
        )
        assert trusted.headers["access-control-allow-credentials"] == "true"

        hostile = cors_client.options(
            "/context",
            headers={
                "Origin": "https://hostile.example",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert hostile.status_code == 400
        assert "access-control-allow-origin" not in hostile.headers


def test_production_cookie_policy_requires_secure_csrf_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("LTI_SESSION_CSRF_SECRET", raising=False)
    policy = session_cookie_policy()
    assert policy.name == "__Host-rag_lti_session"
    assert policy.secure is True
    assert policy.samesite == "none"
    with pytest.raises(RuntimeError, match="at least 32"):
        csrf_token_for_session("opaque-session")

    monkeypatch.setenv("LTI_SESSION_TTL_MINUTES", "61")
    with pytest.raises(RuntimeError, match="must be 60"):
        session_cookie_policy()


def test_login_state_is_hashed_and_hint_is_not_persisted(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(
            Session, bootstrap["registration_id"], "student@lti.test"
        )
        _, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        with Session() as db:
            attempt = db.query(LtiLaunchAttempt).one()
            serialized = repr(attempt.__dict__)
            assert params["state"] not in serialized
            assert params["nonce"] not in serialized
            assert params["login_hint"] not in serialized
            assert len(attempt.state_digest) == 64
            assert len(attempt.nonce_digest) == 64
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _resign(token, mutate):
    claims = jwt.decode(token, options={"verify_signature": False})
    mutate(claims)
    return jwt.encode(
        claims,
        local_private_key(),
        algorithm="RS256",
        headers={"kid": LOCAL_KEY_ID},
    )


def test_verified_unbound_subject_is_quarantined_then_explicitly_bound(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        registration_id = bootstrap["registration_id"]
        subject = _subject_for(Session, registration_id, "student@lti.test")
        path, params = _authorization_request(client, registration_id, subject)
        state, token = _token_from_authorize(client, path, params)
        with Session() as db:
            registration = db.get(LtiRegistration, registration_id)
            assert registration is not None
            organization_id = registration.organization_id
            binding = (
                db.query(LtiSubjectBinding)
                .filter(
                    LtiSubjectBinding.registration_id == registration_id,
                    LtiSubjectBinding.platform_subject == subject,
                )
                .one()
            )
            user_id = binding.user_id
            db.delete(binding)
            db.commit()

        rejected = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert rejected.status_code == 403
        with Session() as db:
            candidates = db.query(LtiBindingCandidate).all()
            assert len(candidates) == 1
            assert candidates[0].candidate_type == "subject"
            assert candidates[0].platform_identifier == subject

        base = (
            f"/integrations/lti/organizations/{organization_id}"
            f"/registrations/{registration_id}/binding-candidates"
        )
        listed = client.get(base, headers={"X-Dev-User": "admin@lti.test"})
        assert listed.status_code == 200, listed.text
        candidate = listed.json()["candidates"][0]
        assert subject not in listed.text
        bound = client.post(
            f"{base}/{candidate['id']}/bind",
            headers={"X-Dev-User": "admin@lti.test"},
            json={"target_id": user_id},
        )
        assert bound.status_code == 200, bound.text

        path, params = _authorization_request(client, registration_id, subject)
        state, token = _token_from_authorize(client, path, params)
        relaunched = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert relaunched.status_code == 200
        assert "/integrations/lti/development?registration_id=" in relaunched.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_invalid_mandatory_claim_is_not_quarantined(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        registration_id = bootstrap["registration_id"]
        subject = _subject_for(Session, registration_id, "student@lti.test")
        path, params = _authorization_request(client, registration_id, subject)
        state, token = _token_from_authorize(client, path, params)

        rejected = client.post(
            "/integrations/lti/launch",
            data={
                "state": state,
                "id_token": _resign(
                    token, lambda claims: claims.update({"nonce": "wrong-nonce"})
                ),
            },
        )

        assert rejected.status_code == 403
        with Session() as db:
            assert db.query(LtiBindingCandidate).count() == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "mutate",
    (
        lambda c: c.update({"iss": "https://wrong.example"}),
        lambda c: c.update({"aud": "wrong-client"}),
        lambda c: c.update({DEPLOYMENT_ID: "wrong-deployment"}),
        lambda c: c.update({TARGET_LINK_URI: "https://wrong.example/launch"}),
        lambda c: c.update({MESSAGE_TYPE: "LtiDeepLinkingRequest"}),
        lambda c: c.update({VERSION: "1.1.0"}),
        lambda c: c.update({"sub": "unknown-subject"}),
        lambda c: c.update({CONTEXT: {"id": "unknown-context"}}),
        lambda c: c.pop(RESOURCE_LINK),
        lambda c: c.update({ROLES: ["http://example.test/Unknown"]}),
        lambda c: c.update({"nonce": "wrong-nonce"}),
    ),
)
def test_invalid_claims_fail_closed_and_consume_state(monkeypatch, mutate):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(
            Session, bootstrap["registration_id"], "student@lti.test"
        )
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        invalid = _resign(token, mutate)
        rejected = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": invalid}
        )
        assert rejected.status_code == 403
        assert "Алгоритмы" not in rejected.text
        assert "Вернуться к выбору" in rejected.text
        correct_retry = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert correct_retry.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_canvas_role_cannot_replace_internal_membership(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(
            Session, bootstrap["registration_id"], "student@lti.test"
        )
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        elevated = _resign(
            token,
            lambda c: c.update(
                {
                    ROLES: [
                        "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"
                    ]
                }
            ),
        )
        before = None
        with Session() as db:
            user = db.query(User).filter(User.email == "student@lti.test").one()
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.user_id == user.id)
                .one()
            )
            before = membership.role
        response = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": elevated}
        )
        assert response.status_code == 403
        with Session() as db:
            user = db.query(User).filter(User.email == "student@lti.test").one()
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.user_id == user.id)
                .one()
            )
            assert membership.role == before == "student"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_canvas_admin_role_requires_active_internal_org_admin(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(Session, bootstrap["registration_id"], "admin@lti.test")
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        with Session() as db:
            user = db.query(User).filter(User.email == "admin@lti.test").one()
            org_membership = (
                db.query(OrganizationMembership)
                .filter(OrganizationMembership.user_id == user.id)
                .one()
            )
            org_membership.is_active = False
            course = db.query(Course).one()
            db.add(
                CourseMembership(
                    organization_id=course.organization_id,
                    course_id=course.id,
                    user_id=user.id,
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()
        response = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_expired_state_and_wrong_signature_are_rejected(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        subject = _subject_for(
            Session, bootstrap["registration_id"], "student@lti.test"
        )
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        with Session() as db:
            attempt = db.query(LtiLaunchAttempt).one()
            attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert (
            client.post(
                "/integrations/lti/launch", data={"state": state, "id_token": token}
            ).status_code
            == 403
        )

        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        claims = jwt.decode(token, options={"verify_signature": False})
        foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode(
            claims,
            foreign_key,
            algorithm="RS256",
            headers={"kid": LOCAL_KEY_ID},
        )
        assert (
            client.post(
                "/integrations/lti/launch", data={"state": state, "id_token": forged}
            ).status_code
            == 403
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_development_endpoints_disappear_in_production(monkeypatch):
    client, _, engine, bootstrap, _ = _client(monkeypatch)
    try:
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.setenv("AUTH_MODE", "external")
        for path in (
            f"/integrations/lti/development?registration_id={bootstrap['registration_id']}",
            "/integrations/lti/development/jwks",
            "/integrations/lti/development/start?registration_id=1&subject=x",
        ):
            response = client.get(path)
            assert response.status_code == 404
        bootstrap_response = client.post(
            "/integrations/lti/development/bootstrap",
            headers={"X-Dev-User": "admin@lti.test"},
            json={"course_id": 1, "public_base_url": "http://testserver"},
        )
        assert bootstrap_response.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_endpoint_policy_requires_https_and_explicit_private_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "external")
    with pytest.raises(ValueError, match="HTTPS"):
        validate_lti_endpoint(
            "http://canvas.example.edu/api/lti/authorize_redirect",
            allow_development_loopback=False,
        )
    with pytest.raises(ValueError):
        validate_lti_endpoint(
            "https://127.0.0.1/api/lti/security/jwks",
            allow_development_loopback=False,
        )


@pytest.mark.parametrize("address", ["100.64.0.1", "224.0.0.1", "ff02::1"])
def test_endpoint_policy_rejects_non_global_and_multicast_addresses(
    monkeypatch, address
):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "external")
    monkeypatch.setenv("LTI_ALLOWED_HOSTS", "canvas.example.edu")
    monkeypatch.delenv("LTI_ALLOWED_PRIVATE_HOSTS", raising=False)
    monkeypatch.setattr(
        lti_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", (address, 0))],
    )

    with pytest.raises(ValueError):
        validate_lti_endpoint(
            "https://canvas.example.edu/api/lti/security/jwks",
            allow_development_loopback=False,
        )


def test_endpoint_policy_accepts_allowlisted_global_address(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_MODE", "external")
    monkeypatch.setenv("LTI_ALLOWED_HOSTS", "canvas.example.edu")
    monkeypatch.setattr(
        lti_service.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 0))],
    )

    assert validate_lti_endpoint(
        "https://canvas.example.edu/api/lti/security/jwks",
        allow_development_loopback=False,
    ).startswith("https://")


def test_login_refuses_unknown_target_without_disclosure(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        response = client.post(
            "/integrations/lti/login",
            data={
                "iss": "http://testserver/integrations/lti/development/platform",
                "login_hint": "opaque-secret",
                "target_link_uri": "http://testserver/wrong",
                "client_id": "rag-tool-local",
                "lti_deployment_id": "rag-tool-local-school",
            },
        )
        assert response.status_code == 400
        assert "opaque-secret" not in response.text
        assert str(bootstrap["registration_id"]) not in response.text
        unknown_launch = client.post(
            "/integrations/lti/launch",
            data={"state": "unknown-state", "id_token": "unknown-token"},
        )
        assert unknown_launch.status_code == 403
        with Session() as db:
            assert db.query(LtiLaunchAuditEvent).count() == 0
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_launch_runs_off_event_loop_and_platform_posts_bypass_write_key(monkeypatch):
    client, Session, engine, bootstrap, _ = _client(monkeypatch)
    try:
        assert not inspect.iscoroutinefunction(lti_launch)
        subject = _subject_for(
            Session, bootstrap["registration_id"], "student@lti.test"
        )
        path, params = _authorization_request(
            client, bootstrap["registration_id"], subject
        )
        state, token = _token_from_authorize(client, path, params)
        monkeypatch.setenv("API_WRITE_KEY", "local-write-key")
        launched = client.post(
            "/integrations/lti/launch", data={"state": state, "id_token": token}
        )
        assert launched.status_code == 200
        refused_login = client.post(
            "/integrations/lti/login",
            data={"iss": "unknown", "login_hint": "opaque", "target_link_uri": "x"},
        )
        assert refused_login.status_code == 400
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
