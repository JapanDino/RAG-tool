from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.models import (
    AgentRun,
    AgentToolEvent,
    OrganizationTutorDataPolicy,
    OrganizationTutorDataPolicyEvent,
    TutorDataDeletionEvent,
    User,
)
from backend.app.services import admin_agent as admin_agent_service


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
    return TestClient(app), Session, engine


def _headers(email: str, *, key: str | None = None) -> dict[str, str]:
    headers = {"X-Dev-User": email}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def _bootstrap(client: TestClient) -> int:
    response = client.post("/identity/development/bootstrap", json={})
    assert response.status_code == 201
    return response.json()["organization"]["id"]


def _organization_ref(client: TestClient, organization_id: int) -> str:
    response = client.get(
        f"/agent/v1/admin-organization?organization_id={organization_id}",
        headers=_headers("admin@local.test"),
    )
    assert response.status_code == 200
    return response.json()["organization_ref"]


def _payload(organization_ref: str) -> dict:
    return {
        "contract_version": "agent.v1",
        "message": "Проверь хранение данных и политику",
        "selection": {"organization_ref": organization_ref},
    }


def _execute(client: TestClient, accepted, payload: dict):
    for _ in range(4):
        response = client.post(
            accepted.json()["execute_url"],
            headers=_headers("admin@local.test"),
            json=payload,
        )
        if response.status_code != 200:
            return response
        if response.json()["status"] in {"completed", "abstained", "failed"}:
            return response
    raise AssertionError("administrator policy route did not finish")


def _start(client: TestClient, organization_id: int, *, key: str):
    payload = _payload(_organization_ref(client, organization_id))
    accepted = client.post(
        "/agent/v1/messages",
        headers=_headers("admin@local.test", key=key),
        json=payload,
    )
    assert accepted.status_code == 202
    return payload, accepted, _execute(client, accepted, payload)


def test_admin_gets_default_policy_without_false_cleanup_claim(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        payload, accepted, completed = _start(
            client, organization_id, key="policy-default"
        )
        assert completed.status_code == 200
        body = completed.json()
        assert body["workflow"] == "admin.policy_status.v1"
        assert body["status"] == "completed"
        result = body["response"]
        assert result["mode"] == "admin_policy_status"
        assert result["read_only"] is True
        assert result["overall_state"] == "no_receipt"
        assert result["retention"] == {
            "state": "available",
            "source": "default",
            "retention_days": 90,
            "agent_metadata_retention_days": 30,
            "automatic_purge": True,
            "student_self_delete": True,
            "label": "Учебные данные — до 90 дней",
            "detail": (
                "Действует значение по умолчанию; собственная версия организации "
                "ещё не сохранена."
            ),
        }
        assert result["purge_status"]["state"] == "no_receipt"
        assert "не означает" in result["purge_status"]["detail"]
        assert result["action_label"] == "Показать границы очистки"
        serialized = json.dumps(result, ensure_ascii=False).casefold()
        for forbidden in (
            "actor_user_id",
            "subject_user_id",
            "course_id",
            "prompt",
            "transcript",
            "answer",
        ):
            assert forbidden not in serialized

        projected = client.get(
            accepted.json()["status_url"],
            headers=_headers("admin@local.test"),
        )
        assert projected.status_code == 200
        assert projected.json()["response"] == result
        with Session() as db:
            row = (
                db.query(AgentRun)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            events = (
                db.query(AgentToolEvent)
                .filter(AgentToolEvent.agent_run_id == row.id)
                .all()
            )
            assert [(event.tool_name, event.status) for event in events] == [
                ("get_retention_and_policy_status", "succeeded")
            ]
            assert db.query(OrganizationTutorDataPolicy).count() == 0
            assert db.query(OrganizationTutorDataPolicyEvent).count() == 0
            assert db.query(TutorDataDeletionEvent).count() == 0

        replay = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="policy-default"),
            json=payload,
        )
        assert replay.status_code == 202
        assert replay.json()["run_id"] == accepted.json()["run_id"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_policy_route_uses_latest_safe_organization_receipt(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        now = datetime.now(timezone.utc)
        with Session() as db:
            administrator = (
                db.query(User).filter(User.email == "admin@local.test").one()
            )
            db.add(
                OrganizationTutorDataPolicy(
                    organization_id=organization_id,
                    retention_days=180,
                    version=3,
                    updated_by_user_id=administrator.id,
                )
            )
            db.add(
                TutorDataDeletionEvent(
                    organization_id=organization_id,
                    reason="admin_purge",
                    policy_version=3,
                    answers_deleted=12,
                    feedback_events_deleted=4,
                    agent_runs_deleted=7,
                    cutoff=now - timedelta(days=180),
                    agent_run_cutoff=now - timedelta(days=30),
                    created_at=now - timedelta(hours=2),
                )
            )
            # Newer, person-associated records are outside the aggregate route.
            db.add(
                TutorDataDeletionEvent(
                    organization_id=organization_id,
                    subject_user_id=administrator.id,
                    reason="automatic_retention",
                    policy_version=3,
                    answers_deleted=999,
                    feedback_events_deleted=999,
                    agent_runs_deleted=999,
                    created_at=now,
                )
            )
            db.commit()

        _, _, completed = _start(client, organization_id, key="policy-current")
        result = completed.json()["response"]
        assert result["overall_state"] == "ready"
        assert result["retention"]["source"] == "organization"
        assert result["retention"]["retention_days"] == 180
        assert result["policy_versions"][0]["version"] == "организация · v3"
        assert result["purge_status"]["state"] == "current"
        assert result["purge_status"]["policy_version"] == 3
        assert result["purge_status"]["facts"] == [
            "Ответов удалено: 12",
            "Сигналов обратной связи удалено: 4",
            "Запусков агента удалено: 7",
        ]
        assert "999" not in json.dumps(result, ensure_ascii=False)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_new_identical_receipt_makes_completed_policy_route_stale(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        now = datetime.now(timezone.utc)
        with Session() as db:
            db.add(
                TutorDataDeletionEvent(
                    organization_id=organization_id,
                    reason="automatic_retention",
                    policy_version=0,
                    answers_deleted=1,
                    feedback_events_deleted=2,
                    agent_runs_deleted=3,
                    created_at=now - timedelta(minutes=2),
                )
            )
            db.commit()
        _, accepted, completed = _start(client, organization_id, key="policy-stale")
        assert completed.json()["status"] == "completed"

        with Session() as db:
            db.add(
                TutorDataDeletionEvent(
                    organization_id=organization_id,
                    reason="automatic_retention",
                    policy_version=0,
                    answers_deleted=1,
                    feedback_events_deleted=2,
                    agent_runs_deleted=3,
                    created_at=now,
                )
            )
            db.commit()

        stale = client.get(
            accepted.json()["status_url"],
            headers=_headers("admin@local.test"),
        )
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        assert "изменились" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("failed_source", ("policy", "purge"))
def test_policy_route_preserves_independent_source_on_sql_failure(
    monkeypatch, failed_source
):
    client, _, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)

        def unavailable(*_args, **_kwargs):
            raise SQLAlchemyError("private database detail")

        monkeypatch.setattr(
            admin_agent_service,
            (
                "get_effective_tutor_data_policy"
                if failed_source == "policy"
                else "_latest_safe_purge_projection"
            ),
            unavailable,
        )
        _, _, completed = _start(
            client, organization_id, key=f"policy-partial-{failed_source}"
        )
        assert completed.status_code == 200
        result = completed.json()["response"]
        assert result["overall_state"] == "partial"
        if failed_source == "policy":
            assert result["retention"]["state"] == "unavailable"
            assert result["purge_status"]["state"] == "no_receipt"
        else:
            assert result["retention"]["state"] == "available"
            assert result["purge_status"]["state"] == "unavailable"
        assert "private database detail" not in json.dumps(result)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "email",
    (
        "student@local.test",
        "instructor@local.test",
        "methodologist@local.test",
        "designer@local.test",
    ),
)
def test_non_admin_cannot_start_policy_route_with_admin_reference(monkeypatch, email):
    client, _, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        payload = _payload(_organization_ref(client, organization_id))
        denied = client.post(
            "/agent/v1/messages",
            headers=_headers(
                email, key=f"policy-denied-{email.split('@', maxsplit=1)[0]}"
            ),
            json=payload,
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
