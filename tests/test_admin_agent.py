from __future__ import annotations

import json

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
    LtiRegistration,
    Organization,
    OrganizationMembership,
    OrganizationTutorDataPolicy,
    User,
)


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


def _payload(organization_ref: str) -> dict:
    return {
        "contract_version": "agent.v1",
        "message": "Собери операционный маршрут действий",
        "selection": {"organization_ref": organization_ref},
    }


def _execute(client: TestClient, accepted, payload: dict, email: str):
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
    raise AssertionError("administrator route did not finish")


def test_administrator_receives_bounded_read_only_operations_route(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        option = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers("admin@local.test"),
        )
        assert option.status_code == 200
        assert option.headers["cache-control"] == "no-store, max-age=0"
        assert option.json()["organization_id"] == organization_id

        payload = _payload(option.json()["organization_ref"])
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="admin-route-success"),
            json=payload,
        )
        assert accepted.status_code == 202
        completed = _execute(client, accepted, payload, "admin@local.test")
        assert completed.status_code == 200
        result = completed.json()["response"]
        assert completed.json()["status"] == "completed"
        assert result["mode"] == "admin_operations_brief"
        assert result["read_only"] is True
        assert len(result["stations"]) == 4
        assert {item["kind"] for item in result["stations"]} == {
            "canvas_configuration",
            "canvas_launch",
            "model_runtime",
            "data_retention",
        }
        assert 1 <= len(result["priorities"]) <= 3
        serialized = json.dumps(result, ensure_ascii=False).casefold()
        for forbidden in (
            "client_id",
            "deployment_id",
            "api_key",
            "jwks_url",
            "prompt",
            "transcript",
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
            assert row.result_digest and len(row.result_digest) == 64
            assert [(event.tool_name, event.status) for event in events] == [
                ("get_integration_readiness", "succeeded")
            ]
            assert db.query(LtiRegistration).count() == 0
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
def test_non_administrators_cannot_obtain_admin_organization_ref(monkeypatch, email):
    client, _, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        denied = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers(email),
        )
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_signed_organization_ref_is_user_bound_and_membership_is_rechecked(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        owner_ref = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers("admin@local.test"),
        ).json()["organization_ref"]
        with Session() as db:
            peer = User(
                email="peer.admin@local.test",
                display_name="Peer administrator",
                is_active=True,
            )
            db.add(peer)
            db.flush()
            membership = OrganizationMembership(
                organization_id=organization_id,
                user_id=peer.id,
                role="administrator",
                is_active=True,
            )
            db.add(membership)
            db.commit()
            membership_id = membership.id

        payload = _payload(owner_ref)
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("peer.admin@local.test", key="foreign-admin-ref"),
            json=payload,
        )
        assert accepted.status_code == 202
        assert (
            _execute(client, accepted, payload, "peer.admin@local.test").status_code
            == 404
        )

        own_option = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers("peer.admin@local.test"),
        )
        assert own_option.status_code == 200
        with Session() as db:
            db.get(OrganizationMembership, membership_id).is_active = False
            db.commit()
        denied = client.post(
            "/agent/v1/messages",
            headers=_headers("peer.admin@local.test", key="revoked-admin-ref"),
            json=_payload(own_option.json()["organization_ref"]),
        )
        assert denied.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_changed_retention_signal_hides_completed_operations_route(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        option = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers("admin@local.test"),
        ).json()
        payload = _payload(option["organization_ref"])
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="stale-admin-route"),
            json=payload,
        )
        completed = _execute(client, accepted, payload, "admin@local.test")
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        with Session() as db:
            db.add(
                OrganizationTutorDataPolicy(
                    organization_id=organization_id,
                    retention_days=30,
                    version=1,
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
        assert "изменилось" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_multi_organization_administrator_keeps_selected_scope_and_idempotency(
    monkeypatch,
):
    client, Session, engine = _client(monkeypatch)
    try:
        primary_id = _bootstrap(client)
        with Session() as db:
            administrator = (
                db.query(User).filter(User.email == "admin@local.test").one()
            )
            second = Organization(
                slug="second-admin-school", name="Second admin school"
            )
            db.add(second)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=second.id,
                    user_id=administrator.id,
                    role="administrator",
                    is_active=True,
                )
            )
            db.commit()
            second_id = second.id

        primary = client.get(
            f"/agent/v1/admin-organization?organization_id={primary_id}",
            headers=_headers("admin@local.test"),
        )
        selected = client.get(
            f"/agent/v1/admin-organization?organization_id={second_id}",
            headers=_headers("admin@local.test"),
        )
        assert primary.status_code == selected.status_code == 200
        assert primary.json()["organization_ref"] != selected.json()["organization_ref"]

        payload = _payload(selected.json()["organization_ref"])
        first = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="second-org-admin-route"),
            json=payload,
        )
        replay = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="second-org-admin-route"),
            json=payload,
        )
        assert first.status_code == replay.status_code == 202
        assert first.json()["run_id"] == replay.json()["run_id"]
        completed = _execute(client, first, payload, "admin@local.test")
        assert completed.status_code == 200
        assert (
            completed.json()["response"]["organization_name"] == "Second admin school"
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_one_unavailable_projection_preserves_the_other_operations_stations(
    monkeypatch,
):
    client, _, engine = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)

        def unavailable_launches(*_args, **_kwargs):
            raise SQLAlchemyError("simulated bounded read failure")

        monkeypatch.setattr(
            "backend.app.services.admin_agent.pilot_launch_health",
            unavailable_launches,
        )
        option = client.get(
            f"/agent/v1/admin-organization?organization_id={organization_id}",
            headers=_headers("admin@local.test"),
        ).json()
        payload = _payload(option["organization_ref"])
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("admin@local.test", key="partial-admin-route"),
            json=payload,
        )
        completed = _execute(client, accepted, payload, "admin@local.test")
        assert completed.status_code == 200
        result = completed.json()["response"]
        assert completed.json()["status"] == "completed"
        assert result["overall_state"] == "partial"
        assert len(result["stations"]) == 4
        by_kind = {station["kind"]: station for station in result["stations"]}
        assert by_kind["canvas_launch"]["state"] == "unavailable"
        assert by_kind["canvas_configuration"]["state"] != "unavailable"
        assert by_kind["model_runtime"]["state"] != "unavailable"
        assert by_kind["data_retention"]["state"] != "unavailable"
        assert "simulated" not in json.dumps(result)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
