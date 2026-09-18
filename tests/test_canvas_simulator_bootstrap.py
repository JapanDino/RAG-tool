import re
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.models import (
    Chunk,
    Course,
    CourseMembership,
    CourseModule,
    CourseQuestionAnswer,
    Document,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services import lti as lti_service
from backend.app.services.lti_development import local_jwks


class _JwksResponse:
    content = b"synthetic-local-jwks"

    def raise_for_status(self):
        return None

    def json(self):
        return local_jwks()


@pytest.fixture
def simulator_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("CANVAS_SIMULATOR_ENABLED", "true")
    monkeypatch.setenv("CANVAS_SIMULATOR_DATA_MODE", "synthetic")
    monkeypatch.setenv("CANVAS_SIMULATOR_LTI_BASE_URL", "http://testserver")
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", "http://localhost:3000")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
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
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(
        lti_service.requests, "get", lambda *args, **kwargs: _JwksResponse()
    )
    client = TestClient(app)
    yield client, Session, engine
    app.dependency_overrides.clear()
    engine.dispose()


def _bootstrap(client: TestClient):
    return client.post(
        "/integrations/lti/development/simulator/bootstrap",
        json={
            "lti_base_url": "http://testserver",
            "canvas_base_url": "http://localhost:3000",
        },
    )


def _signed_launch(client: TestClient, launch_url: str):
    parsed = urlparse(launch_url)
    started = client.get(
        parsed.path,
        params={key: values[0] for key, values in parse_qs(parsed.query).items()},
        follow_redirects=False,
    )
    assert started.status_code == 302
    login = client.get(started.headers["location"], follow_redirects=False)
    assert login.status_code == 302
    authorization = client.get(login.headers["location"])
    assert authorization.status_code == 200
    state_match = re.search(r'name="state" value="([^"]+)"', authorization.text)
    token_match = re.search(r'name="id_token" value="([^"]+)"', authorization.text)
    assert state_match is not None
    assert token_match is not None
    return client.post(
        "/integrations/lti/launch",
        data={"state": state_match.group(1), "id_token": token_match.group(1)},
    )


def test_simulator_bootstrap_is_exact_idempotent_and_resolvable(simulator_client):
    client, Session, _ = simulator_client
    first = _bootstrap(client)
    assert first.status_code == 201, first.text
    payload = first.json()
    assert payload["version"] == "1"
    assert payload["learner_email"] == "learner@canvas-simulator.test"
    assert payload["instructor_email"] == "instructor@canvas-simulator.test"
    assert [item["fixture_id"] for item in payload["courses"]] == [
        "demo-ai",
        "demo-review",
    ]
    assert len(set(payload["registration_map"].values())) == 2
    first_ids = {
        item["fixture_id"]: (item["course_id"], item["registration_id"])
        for item in payload["courses"]
    }

    second = _bootstrap(client)
    assert second.status_code == 201, second.text
    second_ids = {
        item["fixture_id"]: (item["course_id"], item["registration_id"])
        for item in second.json()["courses"]
    }
    assert second_ids == first_ids

    with Session() as db:
        assert db.query(Organization).count() == 1
        assert db.query(Course).count() == 2
        assert db.query(LtiRegistration).count() == 2
        assert db.query(LtiContextBinding).count() == 2
        assert db.query(LtiSubjectBinding).count() == 4
        assert db.query(CourseMembership).count() == 10
        assert db.query(OrganizationMembership).count() == 5
        assert db.query(User).count() == 5
        assert db.query(CourseModule).count() == 6
        assert db.query(Document).count() == 17
        assert db.query(Chunk).count() == 17
        assert db.query(CourseQuestionAnswer).count() == 8
    for fixture_id, (_, registration_id) in first_ids.items():
        resolved = client.get(f"/integrations/lti/development/simulator/{fixture_id}")
        assert resolved.status_code == 200
        assert resolved.headers["cache-control"].startswith("no-store")
        assert resolved.json()["registration_id"] == registration_id
        assert resolved.json()["actor"] == "learner"
        assert resolved.json()["subject"].endswith("-learner")
        assert resolved.json()["launch_url"].startswith(
            "http://testserver/integrations/lti/development/start?"
        )
        instructor = client.get(
            f"/integrations/lti/development/simulator/{fixture_id}",
            params={"actor": "instructor"},
        )
        assert instructor.status_code == 200
        assert instructor.json()["registration_id"] == registration_id
        assert instructor.json()["course_id"] == resolved.json()["course_id"]
        assert instructor.json()["actor"] == "instructor"
        assert instructor.json()["subject"].endswith("-instructor")
        assert instructor.json()["launch_url"] != resolved.json()["launch_url"]
    assert (
        client.get("/integrations/lti/development/simulator/unknown").status_code == 404
    )
    assert (
        client.get(
            "/integrations/lti/development/simulator/demo-ai",
            params={"actor": "administrator"},
        ).status_code
        == 422
    )

    changed_origin = client.post(
        "/integrations/lti/development/simulator/bootstrap",
        json={
            "lti_base_url": "http://127.0.0.1:8000",
            "canvas_base_url": "http://127.0.0.1:3000",
        },
    )
    assert changed_origin.status_code == 201, changed_origin.text
    changed_ids = {
        item["fixture_id"]: (item["course_id"], item["registration_id"])
        for item in changed_origin.json()["courses"]
    }
    assert changed_ids == first_ids
    with Session() as db:
        assert db.query(LtiRegistration).count() == 2
        assert all(
            registration.issuer.startswith("http://127.0.0.1:8000/")
            for registration in db.query(LtiRegistration).all()
        )


@pytest.mark.parametrize(
    ("fixture_id", "title", "module_titles"),
    (
        (
            "demo-ai",
            "Проектная лаборатория: ИИ-сервисы",
            [
                "00. Старт проекта",
                "01. Данные и поиск",
                "02. Качество и безопасность",
                "03. Защита проекта",
            ],
        ),
        (
            "demo-review",
            "Русский язык: мастерская рецензии",
            [
                "Неделя 1. Читаем как рецензенты",
                "Неделя 2. Собираем текст",
            ],
        ),
    ),
)
def test_each_simulator_fixture_completes_signed_learner_course_map_flow(
    simulator_client, fixture_id, title, module_titles
):
    client, _, _ = simulator_client
    bootstrap = _bootstrap(client)
    assert bootstrap.status_code == 201
    fixture = next(
        item for item in bootstrap.json()["courses"] if item["fixture_id"] == fixture_id
    )
    launched = _signed_launch(client, fixture["launch_url"])
    assert launched.status_code == 200
    assert "Запуск подтверждён" in launched.text
    assert title in launched.text
    assert "Ученик" in launched.text
    assert "/canvas-companion" in launched.text
    assert "rag_lti_session" in launched.headers["set-cookie"]

    course_map = client.get("/course-map")
    assert course_map.status_code == 200, course_map.text
    payload = course_map.json()
    assert payload["course"]["id"] == fixture["course_id"]
    assert payload["course"]["title"] == title
    assert [module["title"] for module in payload["modules"]] == module_titles
    item_types = {
        item["item_type"] for module in payload["modules"] for item in module["items"]
    }
    assert item_types == {"page", "assignment", "file", "external", "section"}


@pytest.mark.parametrize("fixture_id", ("demo-ai", "demo-review"))
def test_each_simulator_fixture_completes_signed_instructor_workspace_flow(
    simulator_client, fixture_id
):
    client, _, _ = simulator_client
    bootstrap = _bootstrap(client)
    assert bootstrap.status_code == 201
    fixture = next(
        item for item in bootstrap.json()["courses"] if item["fixture_id"] == fixture_id
    )

    launched = _signed_launch(client, fixture["instructor_launch_url"])
    assert launched.status_code == 200
    assert "Запуск подтверждён" in launched.text
    assert "Преподаватель" in launched.text
    assert f'/workspace/courses/{fixture["course_id"]}?lti=1' in launched.text
    assert "/canvas-companion" not in launched.text
    assert "rag_lti_session" in launched.headers["set-cookie"]

    identity = client.get("/identity/me")
    assert identity.status_code == 200
    access = next(
        item
        for item in identity.json()["courses"]
        if item["id"] == fixture["course_id"]
    )
    assert "instructor" in access["roles"]
    assert "review_findings" in access["actions"]

    workspace = client.get(f'/courses/{fixture["course_id"]}/teacher-workspace')
    assert workspace.status_code == 200, workspace.text
    assert workspace.json()["course"]["id"] == fixture["course_id"]
    handoff = client.get(f'/courses/{fixture["course_id"]}/canvas-oauth-handoff')
    assert handoff.status_code == 200
    assert handoff.json()["state"] == "production_disabled"
    assert handoff.json()["fake_flow_available"] is False
    assert client.get("/course-map").status_code == 404


@pytest.mark.parametrize(
    ("membership_model", "field"),
    (
        (OrganizationMembership, "organization_id"),
        (CourseMembership, "course_id"),
    ),
)
def test_instructor_resolver_fails_closed_for_inactive_membership(
    simulator_client, membership_model, field
):
    client, Session, _ = simulator_client
    bootstrap = _bootstrap(client)
    assert bootstrap.status_code == 201
    fixture = bootstrap.json()["courses"][0]

    with Session() as db:
        instructor = (
            db.query(User)
            .filter(User.email == "instructor@canvas-simulator.test")
            .one()
        )
        query = db.query(membership_model).filter(
            membership_model.user_id == instructor.id
        )
        if field == "organization_id":
            query = query.filter(
                membership_model.organization_id == bootstrap.json()["organization_id"]
            )
        else:
            query = query.filter(membership_model.course_id == fixture["course_id"])
        membership = query.one()
        membership.is_active = False
        db.commit()

    resolved = client.get(
        f'/integrations/lti/development/simulator/{fixture["fixture_id"]}',
        params={"actor": "instructor"},
    )
    assert resolved.status_code == 404


@pytest.mark.parametrize(
    "payload",
    (
        {
            "lti_base_url": "https://attacker.example",
            "canvas_base_url": "http://localhost:3000",
        },
        {
            "lti_base_url": "http://localhost:8000/path",
            "canvas_base_url": "http://localhost:3000",
        },
        {
            "lti_base_url": "http://user:password@localhost:8000",
            "canvas_base_url": "http://localhost:3000",
        },
    ),
)
def test_simulator_bootstrap_rejects_non_loopback_or_credential_origins(
    simulator_client, payload
):
    client, Session, _ = simulator_client
    response = client.post(
        "/integrations/lti/development/simulator/bootstrap", json=payload
    )
    assert response.status_code == 422
    with Session() as db:
        assert db.query(Course).count() == 0


def test_simulator_endpoints_disappear_without_exact_gate(
    simulator_client, monkeypatch
):
    client, Session, _ = simulator_client
    monkeypatch.setenv("CANVAS_SIMULATOR_DATA_MODE", "canvas")
    assert _bootstrap(client).status_code == 404
    assert (
        client.get("/integrations/lti/development/simulator/demo-ai").status_code == 404
    )
    with Session() as db:
        assert db.query(Course).count() == 0

    monkeypatch.setenv("CANVAS_SIMULATOR_DATA_MODE", "synthetic")
    monkeypatch.setenv("APP_ENV", "production")
    assert _bootstrap(client).status_code == 404


def test_simulator_bootstrap_rejects_unexpected_fields(simulator_client):
    client, _, _ = simulator_client
    response = client.post(
        "/integrations/lti/development/simulator/bootstrap",
        json={
            "lti_base_url": "http://testserver",
            "canvas_base_url": "http://localhost:3000",
            "registration_id": 123,
        },
    )
    assert response.status_code == 422
