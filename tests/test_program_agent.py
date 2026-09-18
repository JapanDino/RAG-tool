from __future__ import annotations

import json

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
    AgentRun,
    AgentToolEvent,
    Competency,
    CourseContribution,
    LearningObjective,
    Organization,
    OrganizationMembership,
    Program,
    ProgramChangeEvent,
    ProgramCourse,
    ProgramPrerequisiteRelation,
    ProgramReviewNote,
    User,
)
from backend.app.schemas.agent_api import AgentProgramRouteCountsOut
from backend.app.schemas.program_intelligence import (
    PrerequisiteEvidenceOut,
    PrerequisiteRelationOut,
    ProgramAuditCountsOut,
    ProgramAuditFindingOut,
    ProgramAuditPreviewOut,
)
from backend.app.services.program_agent import (
    build_program_gap_route,
    build_program_prerequisite_route,
    build_program_route_brief,
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


def _bootstrap_demo(client: TestClient) -> tuple[int, int]:
    bootstrap = client.post("/identity/development/bootstrap", json={})
    assert bootstrap.status_code == 201
    organization_id = bootstrap.json()["organization"]["id"]
    created = client.post(
        f"/organizations/{organization_id}/programs/demo",
        headers=_headers("designer@local.test"),
    )
    assert created.status_code == 201
    return organization_id, created.json()["program_id"]


def _execute(client: TestClient, accepted, payload, email: str):
    transitions = []
    for _ in range(4):
        response = client.post(
            accepted.json()["execute_url"],
            headers=_headers(email),
            json=payload,
        )
        transitions.append(response.status_code)
        if response.status_code != 200:
            return response
        if response.json()["status"] in {"completed", "abstained", "failed"}:
            return response
    raise AssertionError(f"program agent did not finish: {transitions}")


def _program_option(client: TestClient, email: str):
    response = client.get("/agent/v1/programs", headers=_headers(email))
    assert response.status_code == 200
    return response.json()["programs"][0]


def _run_program_evidence_route(
    client: TestClient,
    *,
    email: str,
    message: str,
    program_ref: str,
    key: str,
):
    payload = {
        "contract_version": "agent.v1",
        "message": message,
        "selection": {"program_ref": program_ref},
    }
    accepted = client.post(
        "/agent/v1/messages",
        headers=_headers(email, key=key),
        json=payload,
    )
    assert accepted.status_code == 202, accepted.text
    completed = _execute(client, accepted, payload, email)
    assert completed.status_code == 200, completed.text
    return accepted, completed


def _run_program_review_draft(
    client: TestClient,
    *,
    email: str,
    program_ref: str,
    key: str,
):
    payload = {
        "contract_version": "agent.v1",
        "message": "review note",
        "selection": {"program_ref": program_ref},
    }
    accepted = client.post(
        "/agent/v1/messages",
        headers=_headers(email, key=key),
        json=payload,
    )
    assert accepted.status_code == 202, accepted.text
    completed = _execute(client, accepted, payload, email)
    assert completed.status_code == 200, completed.text
    return accepted, completed


def test_truncated_empty_audit_never_claims_an_all_clear():
    program = Program(
        id=1,
        organization_id=1,
        code="TRUNCATED",
        title="Большая программа",
        version=7,
        is_active=True,
    )
    audit = ProgramAuditPreviewOut(
        program_id=1,
        program_version=7,
        analyzed_competencies=500,
        analyzed_contributions=0,
        analysis_truncated=True,
        findings_truncated=False,
        counts=ProgramAuditCountsOut(
            total=0,
            review=0,
            watch=0,
            coverage_gap=0,
            assessment_gap=0,
            evidence_gap=0,
            duplication_check=0,
            sequence_check=0,
        ),
        findings=[],
    )
    result = build_program_route_brief(
        program=program,
        counts=AgentProgramRouteCountsOut(
            courses=20,
            competencies=501,
            assessed_competencies=0,
            learning_only_competencies=0,
            unmapped_competencies=501,
            missing_evidence_cells=0,
        ),
        audit=audit,
    )
    assert result.analysis_truncated is True
    assert "не полностью" in result.headline
    assert "не видно" not in result.headline


def _audit_finding(kind: str, *, key: str) -> ProgramAuditFindingOut:
    return ProgramAuditFindingOut(
        key=key,
        kind=kind,
        attention="review",
        competency_id=1,
        competency_code="C-01",
        competency_title="Competency",
        title="Review this signal",
        detail="Bounded deterministic detail",
        confidence="high",
        confidence_label="Deterministic rule",
        evidence_status="none",
        evidence=[],
    )


def test_gap_route_skips_sequence_only_findings_and_keeps_a_non_verdict_clear_state():
    program = Program(
        id=1,
        organization_id=1,
        code="ROUTE",
        title="Program",
        version=1,
        is_active=True,
    )
    sequence_only = ProgramAuditPreviewOut(
        program_id=1,
        program_version=1,
        analyzed_competencies=1,
        analyzed_contributions=2,
        analysis_truncated=False,
        findings_truncated=False,
        counts=ProgramAuditCountsOut(
            total=1,
            review=1,
            watch=0,
            coverage_gap=0,
            assessment_gap=0,
            evidence_gap=0,
            duplication_check=0,
            sequence_check=1,
        ),
        findings=[_audit_finding("sequence_check", key="sequence:1")],
    )
    clear_route = build_program_gap_route(program=program, audit=sequence_only)
    assert clear_route.state == "clear"
    assert clear_route.candidate is None
    assert len(clear_route.limitations) >= 2

    sequence_only.findings.append(_audit_finding("coverage_gap", key="coverage:1"))
    selected_route = build_program_gap_route(program=program, audit=sequence_only)
    assert selected_route.state == "candidate"
    assert selected_route.candidate is not None
    assert selected_route.candidate.focus_key == "coverage:1"
    assert selected_route.candidate.candidate_type == "coverage_gap"


def _prerequisite_evidence(
    *,
    competency_id: int,
    course_position: int,
    stage: str,
    evidence_state: str = "live",
) -> PrerequisiteEvidenceOut:
    return PrerequisiteEvidenceOut(
        contribution_id=competency_id,
        competency_id=competency_id,
        course_id=course_position,
        course_title=f"Course {course_position}",
        course_position=course_position,
        stage=stage,
        evidence_state=evidence_state,
        evidence_label="Saved source",
        evidence_excerpt="Untrusted saved evidence excerpt",
        evidence_review_status="not_reviewed",
    )


@pytest.mark.parametrize(
    ("structural_state", "prerequisite_assessment", "target_start", "evidence_status"),
    (
        (
            "needs_evidence",
            None,
            _prerequisite_evidence(
                competency_id=2,
                course_position=2,
                stage="introduced",
                evidence_state="missing",
            ),
            "missing",
        ),
        (
            "order_check",
            _prerequisite_evidence(
                competency_id=1,
                course_position=2,
                stage="assessed",
            ),
            _prerequisite_evidence(
                competency_id=2,
                course_position=1,
                stage="introduced",
            ),
            "declared",
        ),
        (
            "declared_order",
            _prerequisite_evidence(
                competency_id=1,
                course_position=1,
                stage="assessed",
            ),
            _prerequisite_evidence(
                competency_id=2,
                course_position=2,
                stage="introduced",
            ),
            "declared",
        ),
    ),
)
def test_prerequisite_route_preserves_each_explicit_structural_state(
    structural_state,
    prerequisite_assessment,
    target_start,
    evidence_status,
):
    program = Program(
        id=1,
        organization_id=1,
        code="ROUTE",
        title="Program",
        version=1,
        is_active=True,
    )
    relation = PrerequisiteRelationOut(
        id=9,
        program_id=1,
        prerequisite_competency_id=1,
        prerequisite_competency_code="C-01",
        prerequisite_competency_title="First",
        target_competency_id=2,
        target_competency_code="C-02",
        target_competency_title="Second",
        rationale="Author-declared relation",
        structural_state=structural_state,
        structural_state_label="Saved structural state",
        prerequisite_assessment=prerequisite_assessment,
        target_start=target_start,
    )
    route = build_program_prerequisite_route(
        program=program,
        relations=[relation],
        relations_truncated=False,
    )
    assert route.state == "candidate"
    assert route.candidate is not None
    assert route.candidate.candidate_type == structural_state
    assert route.candidate.evidence_status == evidence_status
    assert len(route.candidate.evidence) <= 2
    assert route.candidate.focus_key == "prerequisite:9"


@pytest.mark.parametrize(
    "email",
    (
        "methodologist@local.test",
        "designer@local.test",
        "admin@local.test",
    ),
)
def test_program_roles_receive_one_bounded_gap_candidate(monkeypatch, email):
    client, Session, engine = _client(monkeypatch)
    try:
        _bootstrap_demo(client)
        option = _program_option(client, email)
        accepted, completed = _run_program_evidence_route(
            client,
            email=email,
            message="Проверь пробел программы",
            program_ref=option["program_ref"],
            key=f"program-gap-{email.split('@')[0]}",
        )
        body = completed.json()
        assert body["workflow"] == "program.inspect_gap.v1"
        route = body["response"]
        assert route["mode"] == "program_evidence_route"
        assert route["route_kind"] == "gap"
        assert route["state"] == "candidate"
        assert route["read_only"] is True
        assert route["action_target"] == "audit"
        assert route["candidate"]["candidate_type"] in {
            "coverage_gap",
            "assessment_gap",
            "evidence_gap",
            "duplication_check",
        }
        assert len(route["candidate"]["evidence"]) <= 4
        serialized = json.dumps(route, ensure_ascii=False).lower()
        for forbidden in (
            "student@local.test",
            "expected_answer",
            "transcript",
            "generation_model",
        ):
            assert forbidden not in serialized
        events = client.get(
            accepted.json()["events_url"],
            headers=_headers(email),
        )
        assert events.status_code == 200
        assert [item["type"] for item in events.json()["events"]] == [
            "run.accepted",
            "run.routing",
            "run.tool_running",
            "run.completed",
        ]
        with Session() as db:
            run = (
                db.query(AgentRun)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            event = db.query(AgentToolEvent).filter_by(agent_run_id=run.id).one()
            assert (event.tool_name, event.status, event.failure_class) == (
                "inspect_program_gap",
                "succeeded",
                None,
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "email",
    (
        "methodologist@local.test",
        "designer@local.test",
        "admin@local.test",
    ),
)
def test_program_roles_see_empty_prerequisite_route_without_inference(
    monkeypatch,
    email,
):
    client, _, engine = _client(monkeypatch)
    try:
        _bootstrap_demo(client)
        option = _program_option(client, email)
        _, completed = _run_program_evidence_route(
            client,
            email=email,
            message="Проверь предварительные требования программы",
            program_ref=option["program_ref"],
            key=f"program-prerequisite-empty-{email.split('@')[0]}",
        )
        route = completed.json()["response"]
        assert route["route_kind"] == "prerequisite"
        assert route["state"] == "empty"
        assert route["candidate"] is None
        assert "пока нет" in route["headline"]
        assert route["action_target"] == "prerequisites"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_explicit_prerequisite_route_exposes_two_anchors_and_stales_on_change(
    monkeypatch,
):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        with Session() as db:
            competencies = (
                db.query(Competency)
                .filter(Competency.program_id == program_id)
                .order_by(Competency.position)
                .all()
            )
            relation = ProgramPrerequisiteRelation(
                program_id=program_id,
                prerequisite_competency_id=competencies[0].id,
                target_competency_id=competencies[1].id,
                rationale="Сначала проверяется анализ, затем развивается выбор структуры.",
            )
            db.add(relation)
            db.get(Program, program_id).version += 1
            db.commit()
            relation_id = relation.id
            version = db.get(Program, program_id).version

        email = "designer@local.test"
        option = _program_option(client, email)
        accepted, completed = _run_program_evidence_route(
            client,
            email=email,
            message="Проверь предварительные требования программы",
            program_ref=option["program_ref"],
            key="program-prerequisite-candidate",
        )
        route = completed.json()["response"]
        assert route["state"] == "candidate"
        assert route["candidate"]["candidate_type"] == "order_check"
        assert route["candidate"]["evidence_status"] == "declared"
        assert len(route["candidate"]["evidence"]) == 2
        assert "готовность" in route["limitations"][1]
        with Session() as db:
            event = (
                db.query(AgentToolEvent)
                .join(AgentRun, AgentRun.id == AgentToolEvent.agent_run_id)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            assert event.tool_name == "inspect_prerequisite_path"
            relation = db.get(ProgramPrerequisiteRelation, relation_id)
            relation.rationale = (
                "Изменённое явное обоснование без смены версии программы."
            )
            db.commit()
            assert db.get(Program, program_id).version == version

        stale = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        assert "изменились" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_prerequisite_route_stales_when_a_nonselected_relation_changes(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        with Session() as db:
            competencies = (
                db.query(Competency)
                .filter(Competency.program_id == program_id)
                .order_by(Competency.position)
                .all()
            )
            relations = [
                ProgramPrerequisiteRelation(
                    program_id=program_id,
                    prerequisite_competency_id=competencies[0].id,
                    target_competency_id=competencies[1].id,
                    rationale="First saved relation",
                ),
                ProgramPrerequisiteRelation(
                    program_id=program_id,
                    prerequisite_competency_id=competencies[0].id,
                    target_competency_id=competencies[2].id,
                    rationale="Second saved relation",
                ),
            ]
            db.add_all(relations)
            db.get(Program, program_id).version += 1
            db.commit()
            relation_ids = {relation.id for relation in relations}

        email = "methodologist@local.test"
        option = _program_option(client, email)
        accepted, completed = _run_program_evidence_route(
            client,
            email=email,
            message="prerequisite",
            program_ref=option["program_ref"],
            key="nonselected-prerequisite-source",
        )
        selected_id = int(
            completed.json()["response"]["candidate"]["focus_key"].split(":")[1]
        )
        nonselected_id = (relation_ids - {selected_id}).pop()
        with Session() as db:
            version = db.get(Program, program_id).version
            relation = db.get(ProgramPrerequisiteRelation, nonselected_id)
            relation.rationale = "Changed nonselected saved relation"
            db.commit()
            assert db.get(Program, program_id).version == version

        stale = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_gap_route_stales_when_hidden_evidence_suffix_changes(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        with Session() as db:
            contribution = (
                db.query(CourseContribution)
                .join(Competency, Competency.id == CourseContribution.competency_id)
                .filter(
                    CourseContribution.program_id == program_id,
                    CourseContribution.evidence_type == "learning_objective",
                    Competency.code == "CS-02",
                )
                .first()
            )
            objective = db.get(LearningObjective, contribution.evidence_id)
            objective.text = "A" * 700 + "X"
            db.commit()
            version = db.get(Program, program_id).version

        email = "methodologist@local.test"
        option = _program_option(client, email)
        accepted, completed = _run_program_evidence_route(
            client,
            email=email,
            message="program gap",
            program_ref=option["program_ref"],
            key="hidden-gap-evidence-suffix",
        )
        assert completed.json()["status"] == "completed"
        before = completed.json()["response"]
        with Session() as db:
            contribution = (
                db.query(CourseContribution)
                .join(Competency, Competency.id == CourseContribution.competency_id)
                .filter(
                    CourseContribution.program_id == program_id,
                    CourseContribution.evidence_type == "learning_objective",
                    Competency.code == "CS-02",
                )
                .first()
            )
            objective = db.get(LearningObjective, contribution.evidence_id)
            objective.text = "A" * 700 + "Y"
            db.commit()
            assert db.get(Program, program_id).version == version

        stale = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        excerpt = before["candidate"]["evidence"][0]["excerpt"]
        assert len(excerpt) < 701
        assert set(excerpt) == {"A"}
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "email",
    (
        "methodologist@local.test",
        "designer@local.test",
        "admin@local.test",
    ),
)
def test_program_roles_receive_bounded_read_only_route_brief(monkeypatch, email):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        options = client.get("/agent/v1/programs", headers=_headers(email))
        assert options.status_code == 200
        assert options.headers["cache-control"].startswith("no-store")
        assert len(options.json()["programs"]) == 1
        option = options.json()["programs"][0]
        assert option["program_id"] == program_id
        assert option["program_ref"].startswith(f"program_{program_id}_")

        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key=f"program-route-{email.split('@')[0]}"),
            json=payload,
        )
        assert accepted.status_code == 202, accepted.text
        completed = _execute(client, accepted, payload, email)
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["status"] == "completed"
        assert body["workflow"] == "program.inspect_map.v1"
        brief = body["response"]
        assert brief["mode"] == "program_route_brief"
        assert brief["read_only"] is True
        assert brief["counts"] == {
            "courses": 2,
            "competencies": 3,
            "assessed_competencies": 1,
            "learning_only_competencies": 1,
            "unmapped_competencies": 1,
            "missing_evidence_cells": 0,
        }
        assert 1 <= len(brief["priorities"]) <= 3
        assert {item["kind"] for item in brief["priorities"]} == {
            "assessment_gap",
            "coverage_gap",
        }
        assert all(
            item["review_status"] == "not_reviewed" for item in brief["priorities"]
        )
        assert all("evidence_truncated" in item for item in brief["priorities"])
        serialized = json.dumps(body, ensure_ascii=False).lower()
        for forbidden in (
            "student@local.test",
            "instructor@local.test",
            "expected_answer",
            "transcript",
            "generation_model",
        ):
            assert forbidden not in serialized

        events = client.get(accepted.json()["events_url"], headers=_headers(email))
        assert events.status_code == 200
        with Session() as db:
            run = db.query(AgentRun).filter(AgentRun.public_id == body["run_id"]).one()
            audit = db.query(AgentToolEvent).filter_by(agent_run_id=run.id).one()
            assert audit.tool_name == "get_program_competency_map"
            assert audit.status == "succeeded"
            assert audit.failure_class is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_refs_are_role_bound_and_wrong_roles_fail_closed(monkeypatch):
    client, _, engine = _client(monkeypatch)
    try:
        _bootstrap_demo(client)
        option = client.get(
            "/agent/v1/programs", headers=_headers("methodologist@local.test")
        ).json()["programs"][0]
        for email in ("student@local.test", "instructor@local.test"):
            denied = client.get("/agent/v1/programs", headers=_headers(email))
            assert denied.status_code == 404
            assert denied.json()["error"]["code"] == "ACCESS_DENIED"

        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers("designer@local.test", key="role-bound-program-ref"),
            json=payload,
        )
        assert accepted.status_code == 202
        denied = _execute(client, accepted, payload, "designer@local.test")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    ("message", "expected_workflow"),
    (
        ("program gap", "program.inspect_gap.v1"),
        ("prerequisite", "program.inspect_prerequisite.v1"),
    ),
)
def test_program_evidence_routes_reject_a_ref_signed_for_another_role(
    monkeypatch,
    message,
    expected_workflow,
):
    client, Session, engine = _client(monkeypatch)
    try:
        _bootstrap_demo(client)
        option = _program_option(client, "methodologist@local.test")
        payload = {
            "contract_version": "agent.v1",
            "message": message,
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(
                "designer@local.test", key=f"wrong-role-{expected_workflow}"
            ),
            json=payload,
        )
        assert accepted.status_code == 202
        with Session() as db:
            run = (
                db.query(AgentRun)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            assert run.workflow == expected_workflow
        denied = _execute(client, accepted, payload, "designer@local.test")
        assert denied.status_code == 404
        assert denied.json()["error"]["code"] == "ACCESS_DENIED"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_changed_program_version_hides_completed_snapshot(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        email = "methodologist@local.test"
        option = client.get("/agent/v1/programs", headers=_headers(email)).json()[
            "programs"
        ][0]
        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key="stale-program-snapshot"),
            json=payload,
        )
        completed = _execute(client, accepted, payload, email)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"

        with Session() as db:
            program = db.get(Program, program_id)
            program.version += 1
            db.commit()

        stale = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
        assert "изменилась" in stale.json()["user_state"]["label"]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_changed_evidence_hides_completed_route_without_program_version_change(
    monkeypatch,
):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        email = "methodologist@local.test"
        option = client.get("/agent/v1/programs", headers=_headers(email)).json()[
            "programs"
        ][0]
        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key="evidence-stale-program-route"),
            json=payload,
        )
        completed = _execute(client, accepted, payload, email)
        assert completed.status_code == 200
        assert completed.json()["response"]["counts"]["missing_evidence_cells"] == 0

        with Session() as db:
            version = db.get(Program, program_id).version
            contribution = (
                db.query(CourseContribution)
                .filter(
                    CourseContribution.program_id == program_id,
                    CourseContribution.evidence_type == "learning_objective",
                )
                .first()
            )
            db.delete(db.get(LearningObjective, contribution.evidence_id))
            db.commit()
            assert db.get(Program, program_id).version == version

        stale = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert stale.status_code == 200
        assert stale.json()["status"] == "abstained"
        assert stale.json()["response"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_route_uses_authoritative_audit_and_exposes_review_evidence(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        with Session() as db:
            competency = (
                db.query(Competency)
                .filter(Competency.program_id == program_id, Competency.code == "CS-02")
                .one()
            )
            used_course_id = (
                db.query(CourseContribution.course_id)
                .filter(CourseContribution.competency_id == competency.id)
                .scalar()
            )
            other_course_id = (
                db.query(ProgramCourse.course_id)
                .filter(
                    ProgramCourse.program_id == program_id,
                    ProgramCourse.course_id != used_course_id,
                )
                .scalar()
            )
            db.add(
                CourseContribution(
                    program_id=program_id,
                    competency_id=competency.id,
                    course_id=other_course_id,
                    stage="developed",
                    rationale="Повтор этапа для проверки авторитетного аудита.",
                    evidence_type="manual_note",
                    evidence_id=None,
                )
            )
            db.get(Program, program_id).version += 1
            db.commit()

        email = "methodologist@local.test"
        option = client.get("/agent/v1/programs", headers=_headers(email)).json()[
            "programs"
        ][0]
        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key="authoritative-program-audit"),
            json=payload,
        )
        completed = _execute(client, accepted, payload, email)
        assert completed.status_code == 200
        priorities = completed.json()["response"]["priorities"]
        assert "duplication_check" in {item["kind"] for item in priorities}
        assert all(item["review_status"] == "not_reviewed" for item in priorities)
        assert all(item["evidence_count"] <= 8 for item in priorities)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_multi_organization_user_keeps_selected_program_scope(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id, _ = _bootstrap_demo(client)
        with Session() as db:
            user = db.query(User).filter(User.email == "methodologist@local.test").one()
            second = Organization(slug="second-school", name="Second school")
            db.add(second)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=second.id,
                    user_id=user.id,
                    role="methodologist",
                    is_active=True,
                )
            )
            db.commit()

        email = "methodologist@local.test"
        options = client.get(
            f"/agent/v1/programs?organization_id={organization_id}",
            headers=_headers(email),
        )
        assert options.status_code == 200
        option = options.json()["programs"][0]
        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key="multi-org-program-route"),
            json=payload,
        )
        assert accepted.status_code == 202
        assert (
            _execute(client, accepted, payload, email).json()["status"] == "completed"
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("email", ("designer@local.test", "admin@local.test"))
def test_program_author_can_prepare_and_confirm_a_versioned_review_note(
    monkeypatch,
    email,
):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        option = _program_option(client, email)
        accepted, completed = _run_program_review_draft(
            client,
            email=email,
            program_ref=option["program_ref"],
            key=f"program-review-{email.split('@')[0]}",
        )
        body = completed.json()
        assert body["workflow"] == "program.draft_review_note.v1"
        assert body["status"] == "completed"
        draft = body["response"]
        assert draft["mode"] == "program_review_draft"
        assert draft["state"] == "draft"
        assert draft["draft_ref"].startswith(f"review_{program_id}_")
        assert 40 <= len(draft["content"]) <= 2000
        assert len(draft["candidate"]["evidence"]) <= 4
        assert draft["current_note"] is None
        assert draft["program_changed"] is False
        assert draft["canvas_changed"] is False

        with Session() as db:
            initial_program_version = db.get(Program, program_id).version
            assert db.query(ProgramReviewNote).count() == 0

        edited = (
            draft["content"]
            + "\n\nРешение автора программы: проверить владельца и срок на совете программы."
        )
        save_payload = {
            "draft_ref": draft["draft_ref"],
            "decision": "act",
            "content": edited,
            "expected_version": 0,
            "confirmation": "save_program_review_note",
        }
        saved = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json=save_payload,
        )
        assert saved.status_code == 200, saved.text
        assert saved.headers["cache-control"] == "no-store"
        receipt = saved.json()
        assert receipt["decision"] == "act"
        assert receipt["content"] == edited
        assert receipt["version"] == 1
        assert receipt["program_changed"] is False
        assert receipt["canvas_changed"] is False

        with Session() as db:
            assert db.get(Program, program_id).version == initial_program_version
            note = db.query(ProgramReviewNote).one()
            event = (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.entity_type == "program_review_note")
                .one()
            )
            assert note.content == edited
            assert event.event_metadata["decision"] == "act"
            assert edited not in json.dumps(event.event_metadata, ensure_ascii=False)
            run = (
                db.query(AgentRun)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            tool_event = db.query(AgentToolEvent).filter_by(agent_run_id=run.id).one()
            assert tool_event.tool_name == "draft_program_review_note"

        replay = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json=save_payload,
        )
        assert replay.status_code == 200
        assert replay.json()["version"] == 1
        with Session() as db:
            assert (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.entity_type == "program_review_note")
                .count()
                == 1
            )

        _, current = _run_program_review_draft(
            client,
            email=email,
            program_ref=option["program_ref"],
            key=f"program-review-current-{email.split('@')[0]}",
        )
        current_draft = current.json()["response"]
        assert current_draft["current_note"]["decision"] == "act"
        assert current_draft["current_note"]["content"] == edited
        assert current_draft["current_note"]["version"] == 1

        updated_content = edited + "\n\nПосле совета решение оставлено под наблюдением."
        updated = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json={
                **save_payload,
                "draft_ref": current_draft["draft_ref"],
                "decision": "observe",
                "content": updated_content,
                "expected_version": 1,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        assert updated.json()["decision"] == "observe"
        with Session() as db:
            assert db.get(Program, program_id).version == initial_program_version
            assert (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.entity_type == "program_review_note")
                .count()
                == 2
            )

            contribution = (
                db.query(CourseContribution)
                .join(Competency, Competency.id == CourseContribution.competency_id)
                .filter(
                    CourseContribution.program_id == program_id,
                    CourseContribution.evidence_type == "learning_objective",
                    Competency.code == "CS-02",
                )
                .first()
            )
            objective = db.get(LearningObjective, contribution.evidence_id)
            objective.text = f"{objective.text} Уточнённое основание."
            db.commit()
            assert db.get(Program, program_id).version == initial_program_version

        _, refreshed = _run_program_review_draft(
            client,
            email=email,
            program_ref=option["program_ref"],
            key=f"program-review-new-evidence-{email.split('@')[0]}",
        )
        refreshed_draft = refreshed.json()["response"]
        assert (
            refreshed_draft["source_fingerprint"]
            != updated.json()["source_fingerprint"]
        )
        assert refreshed_draft["current_note"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_review_note_conflicts_fail_closed_and_preserve_the_saved_note(
    monkeypatch,
):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        email = "designer@local.test"
        option = _program_option(client, email)
        _, completed = _run_program_review_draft(
            client,
            email=email,
            program_ref=option["program_ref"],
            key="program-review-conflicts",
        )
        draft = completed.json()["response"]
        first_content = draft["content"] + "\n\nАвтор программы подтвердил наблюдение."
        base = {
            "draft_ref": draft["draft_ref"],
            "decision": "observe",
            "content": first_content,
            "expected_version": 0,
            "confirmation": "save_program_review_note",
        }
        assert (
            client.put(
                f"/programs/{program_id}/review-note",
                headers=_headers(email),
                json=base,
            ).status_code
            == 200
        )

        stale = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json={**base, "content": first_content + " Еще правка."},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == (
            "program_review_note_version_conflict"
        )

        tampered = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json={
                **base,
                "draft_ref": draft["draft_ref"][:-1] + "x",
                "expected_version": 1,
            },
        )
        assert tampered.status_code == 409
        assert tampered.json()["detail"]["code"] == (
            "program_review_note_source_changed"
        )

        denied = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers("methodologist@local.test"),
            json={**base, "expected_version": 1},
        )
        assert denied.status_code == 404
        denied_malformed = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers("methodologist@local.test"),
            json={},
        )
        assert denied_malformed.status_code == 404
        authorized_malformed = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json={},
        )
        assert authorized_malformed.status_code == 422
        with Session() as db:
            db.get(Program, program_id).version += 1
            db.commit()
        changed_source = client.put(
            f"/programs/{program_id}/review-note",
            headers=_headers(email),
            json={**base, "expected_version": 1},
        )
        assert changed_source.status_code == 409
        assert changed_source.json()["detail"]["code"] == (
            "program_review_note_source_changed"
        )
        with Session() as db:
            note = db.query(ProgramReviewNote).one()
            assert note.version == 1
            assert note.content == first_content
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_stale_before_execution_and_legacy_digest_fail_closed(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        _, program_id = _bootstrap_demo(client)
        email = "methodologist@local.test"
        option = client.get("/agent/v1/programs", headers=_headers(email)).json()[
            "programs"
        ][0]
        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(email, key="stale-before-program-execute"),
            json=payload,
        )
        assert accepted.status_code == 202
        with Session() as db:
            db.get(Program, program_id).version += 1
            db.commit()
        denied = _execute(client, accepted, payload, email)
        assert denied.status_code == 404

        with Session() as db:
            row = (
                db.query(AgentRun)
                .filter(AgentRun.public_id == accepted.json()["run_id"])
                .one()
            )
            row.status = "completed"
            row.result_digest = None
            db.commit()
        legacy = client.get(accepted.json()["status_url"], headers=_headers(email))
        assert legacy.status_code == 200
        assert legacy.json()["status"] == "abstained"
        assert legacy.json()["response"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_ref_rejects_same_role_peer_wrong_org_and_inactive_program(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        organization_id, program_id = _bootstrap_demo(client)
        owner_email = "methodologist@local.test"
        option = client.get(
            f"/agent/v1/programs?organization_id={organization_id}",
            headers=_headers(owner_email),
        ).json()["programs"][0]
        with Session() as db:
            peer = User(
                email="second.methodologist@local.test",
                display_name="Second methodologist",
                is_active=True,
            )
            second = Organization(slug="foreign-school", name="Foreign school")
            db.add_all([peer, second])
            db.flush()
            db.add_all(
                [
                    OrganizationMembership(
                        organization_id=organization_id,
                        user_id=peer.id,
                        role="methodologist",
                        is_active=True,
                    ),
                    OrganizationMembership(
                        organization_id=second.id,
                        user_id=peer.id,
                        role="methodologist",
                        is_active=True,
                    ),
                ]
            )
            db.commit()
            second_id = second.id

        payload = {
            "contract_version": "agent.v1",
            "message": "Покажи карту компетенций",
            "selection": {"program_ref": option["program_ref"]},
        }
        accepted = client.post(
            "/agent/v1/messages",
            headers=_headers(
                "second.methodologist@local.test", key="same-role-foreign-ref"
            ),
            json=payload,
        )
        assert accepted.status_code == 202
        assert (
            _execute(
                client,
                accepted,
                payload,
                "second.methodologist@local.test",
            ).status_code
            == 404
        )
        wrong_org = client.get(
            f"/agent/v1/programs?organization_id={second_id}&program_id={program_id}",
            headers=_headers("second.methodologist@local.test"),
        )
        assert wrong_org.status_code == 404

        with Session() as db:
            db.get(Program, program_id).is_active = False
            db.commit()
        inactive = client.post(
            "/agent/v1/messages",
            headers=_headers(owner_email, key="inactive-program-ref"),
            json=payload,
        )
        assert inactive.status_code == 404
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
