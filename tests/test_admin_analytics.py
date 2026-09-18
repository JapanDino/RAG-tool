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
    ModelInvocationEvent,
    User,
)


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    monkeypatch.delenv("AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS", raising=False)
    monkeypatch.delenv("AGENT_MODEL_OUTPUT_USD_PER_MILLION_TOKENS", raising=False)
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


def _payload(organization_ref: str) -> dict:
    return {
        "contract_version": "agent.v1",
        "message": "Собрать контрольную ленту",
        "selection": {"organization_ref": organization_ref},
    }


def _execute(
    client: TestClient, accepted, payload: dict, email: str = "admin@local.test"
):
    for _ in range(4):
        response = client.post(
            accepted.json()["execute_url"],
            headers=_headers(email),
            json=payload,
        )
        if response.status_code != 200:
            return response
        if response.json()["status"] in {"completed", "abstained", "failed"}:
            return response
    raise AssertionError("administrator analytics did not finish")


def _organization_ref(client: TestClient, organization_id: int) -> str:
    response = client.get(
        f"/agent/v1/admin-organization?organization_id={organization_id}",
        headers=_headers("admin@local.test"),
    )
    assert response.status_code == 200
    return response.json()["organization_ref"]


def _seed_users_and_runs(
    Session,
    *,
    organization_id: int,
    current_users: int,
    previous_users: int,
) -> None:
    now = datetime.now(timezone.utc)
    with Session() as db:
        users = []
        for index in range(max(current_users, previous_users)):
            user = User(
                email=f"analytics-{index}@local.test",
                display_name=f"Analytics {index}",
                is_active=True,
            )
            db.add(user)
            db.flush()
            users.append(user)

        counter = 0
        for period, count, created_at in (
            ("current", current_users, now - timedelta(days=2)),
            ("previous", previous_users, now - timedelta(days=35)),
        ):
            for index, user in enumerate(users[:count]):
                counter += 1
                status = ("completed", "abstained", "failed")[index % 3]
                db.add(
                    AgentRun(
                        public_id=f"seed_{period}_{counter}",
                        conversation_id=f"conv_{period}_{counter}",
                        organization_id=organization_id,
                        course_id=None,
                        user_id=user.id,
                        role="student",
                        product_session_id=None,
                        answer_id=None,
                        module_ref=None,
                        selection_ref=None,
                        input_digest=f"{counter:064x}",
                        contract_version="agent.v1",
                        policy_version="agent-policy.v1",
                        workflow="learner.explain_material.v1",
                        route_state="routed",
                        status=status,
                        idempotency_digest=f"{counter + 1000:064x}",
                        label="seed",
                        recovery_action=None,
                        result_digest=None,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
        db.commit()


def _seed_model_events(Session, *, organization_id: int) -> None:
    now = datetime.now(timezone.utc)
    with Session() as db:
        current = (
            ("succeeded", False, 900, 100, 25),
            ("succeeded", False, 1200, 200, 50),
            ("succeeded", False, 1800, 300, 75),
            ("succeeded", False, 2400, 400, 100),
            ("fallback", True, 9000, 500, 125),
        )
        for status, fallback, latency, input_tokens, output_tokens in current:
            db.add(
                ModelInvocationEvent(
                    organization_id=organization_id,
                    task="course_support",
                    workflow_version="v1",
                    prompt_version="v1",
                    model_alias="school-model",
                    status=status,
                    failure_class="provider_unavailable" if fallback else None,
                    latency_ms=latency,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    validation_passed=not fallback,
                    fallback_used=fallback,
                    created_at=now - timedelta(hours=2),
                )
            )
        db.add(
            ModelInvocationEvent(
                organization_id=organization_id,
                task="course_support",
                workflow_version="v1",
                prompt_version="v1",
                model_alias="school-model",
                status="succeeded",
                failure_class=None,
                latency_ms=700,
                input_tokens=50,
                output_tokens=10,
                validation_passed=True,
                fallback_used=False,
                created_at=now - timedelta(hours=30),
            )
        )
        db.commit()


def _seed_admin_program_run(Session, *, organization_id: int) -> None:
    now = datetime.now(timezone.utc)
    with Session() as db:
        administrator = db.query(User).filter(User.email == "admin@local.test").one()
        db.add(
            AgentRun(
                public_id="seed_admin_program",
                conversation_id="conv_admin_program",
                organization_id=organization_id,
                course_id=None,
                user_id=administrator.id,
                role="administrator",
                product_session_id=None,
                answer_id=None,
                module_ref=None,
                selection_ref=None,
                input_digest="a" * 64,
                contract_version="agent.v1",
                policy_version="agent-policy.v1",
                workflow="program.inspect_map.v1",
                route_state="routed",
                status="completed",
                idempotency_digest="b" * 64,
                label="seed admin program route",
                recovery_action=None,
                result_digest="c" * 64,
                created_at=now - timedelta(days=2),
                updated_at=now - timedelta(days=2),
            )
        )
        db.commit()


def test_admin_gets_privacy_safe_runtime_and_cost_tape(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        _seed_users_and_runs(
            Session,
            organization_id=organization_id,
            current_users=5,
            previous_users=5,
        )
        _seed_model_events(Session, organization_id=organization_id)
        monkeypatch.setenv("AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS", "2")
        monkeypatch.setenv("AGENT_MODEL_OUTPUT_USD_PER_MILLION_TOKENS", "4")

        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-success"),
            json=payload,
        )
        assert accepted.status_code == 202
        completed = _execute(client, accepted, payload)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        result = completed.json()["response"]
        assert result["mode"] == "admin_analytics_brief"
        assert result["read_only"] is True
        assert len(result["segments"]) == 3
        segments = {item["kind"]: item for item in result["segments"]}
        assert segments["adoption"]["state"] == "available"
        assert segments["runtime"]["state"] == "attention"
        assert segments["runtime"]["action_target"] == "model"
        assert segments["cost"]["state"] == "available"
        assert sum(bool(item["action_target"]) for item in result["segments"]) == 1
        assert any("USD" in fact for fact in segments["cost"]["current_facts"])
        serialized = json.dumps(result, ensure_ascii=False).casefold()
        for forbidden in (
            "analytics-0@local.test",
            "school-model",
            "provider_unavailable",
            "course_support",
            "prompt_version",
            "workflow_version",
        ):
            assert forbidden not in serialized

        projected = client.get(
            accepted.json()["status_url"], headers=_headers("admin@local.test")
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
                .order_by(AgentToolEvent.id)
                .all()
            )
            assert row.result_digest and len(row.result_digest) == 64
            assert [(event.tool_name, event.status) for event in events] == [
                ("get_aggregate_adoption_health", "succeeded"),
                ("get_agent_latency_cost_health", "succeeded"),
            ]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_low_cohort_is_indivisibly_suppressed_and_cost_is_not_fabricated(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        _seed_users_and_runs(
            Session,
            organization_id=organization_id,
            current_users=4,
            previous_users=5,
        )
        _seed_admin_program_run(Session, organization_id=organization_id)
        _seed_model_events(Session, organization_id=organization_id)
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-suppressed"),
            json=payload,
        )
        result = _execute(client, accepted, payload).json()["response"]
        segments = {item["kind"]: item for item in result["segments"]}
        adoption = segments["adoption"]
        assert adoption["state"] == "suppressed"
        assert adoption["trend"] == "not_comparable"
        assert adoption["current_facts"] == [
            "Числа текущего окна скрыты полностью",
            "Порог: не менее 5 разных пользователей",
        ]
        assert all("Ранее запусков" not in fact for fact in adoption["previous_facts"])
        assert segments["cost"]["state"] == "unconfigured"
        assert all("USD" not in fact for fact in segments["cost"]["current_facts"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_previous_window_is_independently_suppressed(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        _seed_users_and_runs(
            Session,
            organization_id=organization_id,
            current_users=5,
            previous_users=4,
        )
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-previous-suppressed"),
            json=payload,
        )
        result = _execute(client, accepted, payload).json()["response"]
        adoption = next(
            item for item in result["segments"] if item["kind"] == "adoption"
        )
        assert adoption["state"] == "available"
        assert adoption["trend"] == "not_comparable"
        assert adoption["previous_facts"] == [
            "Предыдущее окно скрыто: порог приватности не достигнут"
        ]
        assert all("4" not in fact for fact in adoption["previous_facts"])
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_analytics_request_excludes_itself_from_no_activity_projection(monkeypatch):
    client, _, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-self-excluded"),
            json=payload,
        )
        result = _execute(client, accepted, payload).json()["response"]
        segments = {item["kind"]: item for item in result["segments"]}
        assert segments["adoption"]["state"] == "no_activity"
        assert segments["adoption"]["current_facts"][0] == "Завершённых запусков: 0"
        assert sum(bool(item["action_target"]) for item in result["segments"]) == 1
        assert segments["adoption"]["action_target"] == "integration"
        assert segments["runtime"]["action_target"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_failed_adoption_source_preserves_runtime_segments(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        _seed_model_events(Session, organization_id=organization_id)

        def unavailable_adoption(*_args, **_kwargs):
            raise SQLAlchemyError("private database detail")

        monkeypatch.setattr(
            "backend.app.services.admin_agent._adoption_snapshot",
            unavailable_adoption,
        )
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-partial"),
            json=payload,
        )
        result = _execute(client, accepted, payload).json()["response"]
        segments = {item["kind"]: item for item in result["segments"]}
        assert result["overall_state"] == "partial"
        assert segments["adoption"]["state"] == "unavailable"
        assert segments["runtime"]["state"] != "unavailable"
        assert segments["cost"]["state"] != "unavailable"
        assert "private database detail" not in json.dumps(result)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_changed_runtime_event_hides_completed_tape(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-stale"),
            json=payload,
        )
        completed = _execute(client, accepted, payload)
        assert completed.json()["status"] == "completed"

        with Session() as db:
            db.add(
                ModelInvocationEvent(
                    organization_id=organization_id,
                    task="hidden-task",
                    workflow_version="v1",
                    prompt_version="v1",
                    model_alias="hidden-model",
                    status="succeeded",
                    failure_class=None,
                    latency_ms=50,
                    input_tokens=1,
                    output_tokens=1,
                    validation_passed=True,
                    fallback_used=False,
                    created_at=datetime.now(timezone.utc),
                )
            )
            db.commit()

        stale = client.get(
            accepted.json()["status_url"], headers=_headers("admin@local.test")
        )
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        assert "изменились" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_changed_exact_cost_rate_hides_tape_even_when_public_price_is_unchanged(
    monkeypatch,
):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        now = datetime.now(timezone.utc)
        with Session() as db:
            db.add(
                ModelInvocationEvent(
                    organization_id=organization_id,
                    task="hidden-task",
                    workflow_version="v1",
                    prompt_version="v1",
                    model_alias="hidden-model",
                    status="succeeded",
                    failure_class=None,
                    latency_ms=50,
                    input_tokens=1,
                    output_tokens=0,
                    validation_passed=True,
                    fallback_used=False,
                    created_at=now,
                )
            )
            db.commit()
        monkeypatch.setenv("AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS", "2")
        monkeypatch.setenv("AGENT_MODEL_OUTPUT_USD_PER_MILLION_TOKENS", "4")
        payload = _payload(_organization_ref(client, organization_id))
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="analytics-rate-stale"),
            json=payload,
        )
        completed = _execute(client, accepted, payload)
        assert completed.json()["status"] == "completed"
        cost = next(
            segment
            for segment in completed.json()["response"]["segments"]
            if segment["kind"] == "cost"
        )
        assert cost["current_facts"][0] == "Оценка: 0,000002 USD"

        monkeypatch.setenv("AGENT_MODEL_INPUT_USD_PER_MILLION_TOKENS", "2.1")
        stale = client.get(
            accepted.json()["status_url"], headers=_headers("admin@local.test")
        )
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        assert "изменились" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
