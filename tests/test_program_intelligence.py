import json

import pytest
from pydantic import ValidationError

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
    AssessmentItem,
    Competency,
    Course,
    CourseContribution,
    Dataset,
    LearningObjective,
    Organization,
    OrganizationMembership,
    Program,
    ProgramChangeEvent,
    ProgramCourse,
    ProgramPrerequisiteRelation,
    User,
)
from backend.app.schemas.program_intelligence import (
    CourseContributionUpsertIn,
    ProgramCourseOrderIn,
)
from backend.app.services import program_intelligence
from backend.app.services.program_intelligence import (
    ProgramScopeDenied,
    create_demo_program,
    upsert_course_contribution,
)


def _client(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
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
    return TestClient(app), engine, Session


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def _bootstrap(client: TestClient) -> int:
    response = client.post("/identity/development/bootstrap", json={})
    assert response.status_code == 201
    return response.json()["organization"]["id"]


def test_demo_program_map_roles_states_and_content_safety(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        created = client.post(
            f"/organizations/{organization_id}/programs/demo",
            headers=_headers("designer@local.test"),
        )
        assert created.status_code == 201
        assert created.json() == {
            "program_id": created.json()["program_id"],
            "created": True,
            "courses_created": 2,
            "competencies_created": 3,
            "contributions_created": 3,
        }
        program_id = created.json()["program_id"]
        repeated = client.post(
            f"/organizations/{organization_id}/programs/demo",
            headers=_headers("designer@local.test"),
        )
        assert repeated.status_code == 201
        assert repeated.json()["created"] is False
        assert repeated.json()["program_id"] == program_id

        for email in (
            "designer@local.test",
            "methodologist@local.test",
            "admin@local.test",
        ):
            listing = client.get(
                f"/organizations/{organization_id}/programs",
                headers=_headers(email),
            )
            assert listing.status_code == 200
            assert [item["id"] for item in listing.json()] == [program_id]
            program_map = client.get(
                f"/programs/{program_id}/map",
                headers=_headers(email),
            )
            assert program_map.status_code == 200

        for email in ("instructor@local.test", "student@local.test"):
            denied = client.get(
                f"/organizations/{organization_id}/programs",
                headers=_headers(email),
            )
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"
            denied_map = client.get(
                f"/programs/{program_id}/map",
                headers=_headers(email),
            )
            assert denied_map.status_code == 404

        payload = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("designer@local.test"),
        ).json()
        assert payload["counts"] == {
            "competencies": 3,
            "courses": 2,
            "mapped_cells": 3,
            "assessed_competencies": 1,
            "learning_only_competencies": 1,
            "unmapped_competencies": 1,
            "missing_evidence_cells": 0,
        }
        assert [item["position"] for item in payload["courses"]] == [1, 2]
        assert [item["code"] for item in payload["competencies"]] == [
            "CS-01",
            "CS-02",
            "CS-03",
        ]
        assert [item["coverage_state"] for item in payload["competencies"]] == [
            "assessed",
            "learning_only",
            "unmapped",
        ]
        stages = {
            item["stage"]
            for competency in payload["competencies"]
            for item in competency["contributions"]
        }
        assert stages == {"introduced", "developed", "assessed"}
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "development seed answer must never leave the backend" not in serialized
        assert "expected_answer" not in serialized

        with Session() as db:
            event = db.query(ProgramChangeEvent).one()
            assert event.event_type == "development_demo_created"
            assert event.event_metadata == {
                "competencies": 3,
                "courses": 2,
                "contributions": 3,
            }
            assert "excerpt" not in event.event_metadata
            assert "rationale" not in event.event_metadata
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_authoring_version_scope_and_missing_evidence(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        whitespace_program = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={"code": "blank-title", "title": "   \t  "},
        )
        assert whitespace_program.status_code == 422
        created = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={
                "code": "data-track",
                "title": "Траектория анализа данных",
                "description": "Карта развития аналитических компетенций.",
            },
        )
        assert created.status_code == 201
        assert created.json()["code"] == "DATA-TRACK"
        assert created.json()["version"] == 1
        program_id = created.json()["id"]

        duplicate = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={"code": "DATA-TRACK", "title": "Duplicate"},
        )
        assert duplicate.status_code == 409
        methodologist_write = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("methodologist@local.test"),
            json={
                "expected_version": 1,
                "code": "DA-01",
                "title": "Интерпретировать данные",
                "position": 1,
            },
        )
        assert methodologist_write.status_code == 404
        whitespace_competency = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "code": "DA-BLANK",
                "title": "   \t  ",
                "position": 1,
            },
        )
        assert whitespace_competency.status_code == 422
        competency = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "code": "DA-01",
                "title": "Интерпретировать данные",
                "description": "Проверять выводы по исходным данным.",
                "position": 1,
            },
        )
        assert competency.status_code == 201
        assert competency.json()["program_version"] == 2
        competency_id = competency.json()["id"]
        stale = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "code": "DA-02",
                "title": "Устаревшая запись",
                "position": 2,
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "program_version_conflict"

        with Session() as db:
            designer = db.query(User).filter(User.email == "designer@local.test").one()
            dataset = Dataset(name="program-authoring-course")
            db.add(dataset)
            db.flush()
            course = Course(
                organization_id=organization_id,
                dataset_id=dataset.id,
                title="Введение в анализ данных",
                description="Проверка выводов на данных.",
                source_type="manual",
            )
            db.add(course)
            db.flush()
            objective = LearningObjective(
                course_id=course.id,
                text="Проверять, подтверждается ли аналитический вывод исходными данными.",
                normalized_text="validate inference from data",
                bloom_vector=[],
                top_bloom_levels=["evaluate"],
                extraction_method="test",
                confidence=0.91,
                review_status="confirmed",
            )
            other_org = Organization(
                slug="other-program-org",
                name="Other program org",
                is_active=True,
            )
            other_dataset = Dataset(name="other-program-course")
            db.add_all([objective, other_org, other_dataset])
            db.flush()
            other_course = Course(
                organization_id=other_org.id,
                dataset_id=other_dataset.id,
                title="Other organization course",
                source_type="manual",
            )
            db.add(other_course)
            db.flush()
            other_objective = LearningObjective(
                course_id=other_course.id,
                text="Evidence from another organization.",
                normalized_text="other evidence",
                bloom_vector=[],
                top_bloom_levels=[],
                extraction_method="test",
                confidence=1.0,
                review_status="confirmed",
            )
            db.add(other_objective)
            db.commit()
            designer_id = designer.id
            course_id = course.id
            objective_id = objective.id
            other_course_id = other_course.id
            other_objective_id = other_objective.id

        contribution = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "competency_id": competency_id,
                "course_id": course_id,
                "course_position": 1,
                "stage": "developed",
                "rationale": "Курс развивает проверку аналитических выводов на данных.",
                "evidence_type": "learning_objective",
                "evidence_id": objective_id,
            },
        )
        assert contribution.status_code == 200
        assert contribution.json()["program_version"] == 3
        assert contribution.json()["evidence"]["state"] == "live"

        whitespace_rationale = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 3,
                "competency_id": competency_id,
                "course_id": course_id,
                "course_position": 1,
                "stage": "developed",
                "rationale": "              ",
                "evidence_type": "manual_note",
            },
        )
        assert whitespace_rationale.status_code == 422

        with Session() as db:
            bad_course = CourseContributionUpsertIn(
                expected_version=3,
                competency_id=competency_id,
                course_id=other_course_id,
                course_position=2,
                stage="introduced",
                rationale="This unrelated course must never be attached to the program.",
                evidence_type="learning_objective",
                evidence_id=other_objective_id,
            )
            with pytest.raises(ProgramScopeDenied):
                upsert_course_contribution(
                    db,
                    program_id=program_id,
                    actor_user_id=designer_id,
                    payload=bad_course,
                )
            bad_evidence = CourseContributionUpsertIn(
                expected_version=3,
                competency_id=competency_id,
                course_id=course_id,
                course_position=1,
                stage="assessed",
                rationale="Evidence from another organization must not validate this mapping.",
                evidence_type="learning_objective",
                evidence_id=other_objective_id,
            )
            with pytest.raises(ProgramScopeDenied):
                upsert_course_contribution(
                    db,
                    program_id=program_id,
                    actor_user_id=designer_id,
                    payload=bad_evidence,
                )
            db.expire_all()
            assert db.get(Program, program_id).version == 3
            assert db.query(CourseContribution).count() == 1
            events = (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.program_id == program_id)
                .order_by(ProgramChangeEvent.id)
                .all()
            )
            assert [event.version for event in events] == [1, 2, 3]
            assert [event.event_type for event in events] == [
                "program_created",
                "competency_created",
                "course_contribution_created",
            ]
            event_payload = json.dumps(
                [event.event_metadata for event in events], ensure_ascii=False
            )
            assert "Проверять, подтверждается ли" not in event_payload
            assert "Курс развивает проверку" not in event_payload
            db.query(LearningObjective).filter(
                LearningObjective.id == objective_id
            ).delete()
            db.commit()

        missing = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        assert missing.status_code == 200
        payload = missing.json()
        assert payload["counts"]["missing_evidence_cells"] == 1
        evidence = payload["competencies"][0]["contributions"][0]["evidence"]
        assert evidence["state"] == "missing"
        assert evidence["review_status"] == "missing"

        invalid_manual = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 3,
                "competency_id": competency_id,
                "course_id": course_id,
                "course_position": 1,
                "stage": "developed",
                "rationale": "Manual notes cannot point at opaque evidence identifiers.",
                "evidence_type": "manual_note",
                "evidence_id": 999,
            },
        )
        assert invalid_manual.status_code == 422
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_course_order_is_explicit_and_position_conflicts_are_atomic(
    monkeypatch,
):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        program = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={"code": "route-order", "title": "Explicit route order"},
        )
        assert program.status_code == 201
        program_id = program.json()["id"]
        competency = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "code": "ROUTE-01",
                "title": "Trace the course route",
                "position": 1,
            },
        )
        assert competency.status_code == 201
        competency_id = competency.json()["id"]

        with Session() as db:
            first_dataset = Dataset(name="route-order-first")
            second_dataset = Dataset(name="route-order-second")
            db.add_all([first_dataset, second_dataset])
            db.flush()
            lower_id_course = Course(
                organization_id=organization_id,
                dataset_id=first_dataset.id,
                title="Created first, taught second",
                source_type="manual",
            )
            higher_id_course = Course(
                organization_id=organization_id,
                dataset_id=second_dataset.id,
                title="Created second, taught first",
                source_type="manual",
            )
            db.add_all([lower_id_course, higher_id_course])
            db.commit()
            lower_id = lower_id_course.id
            higher_id = higher_id_course.id
        assert lower_id < higher_id

        first_stop = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "competency_id": competency_id,
                "course_id": higher_id,
                "course_position": 1,
                "stage": "introduced",
                "rationale": "This course intentionally starts the declared route.",
                "evidence_type": "manual_note",
            },
        )
        assert first_stop.status_code == 200
        second_stop = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 3,
                "competency_id": competency_id,
                "course_id": lower_id,
                "course_position": 2,
                "stage": "developed",
                "rationale": "This earlier-created course intentionally comes second.",
                "evidence_type": "manual_note",
            },
        )
        assert second_stop.status_code == 200

        program_map = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        assert program_map.status_code == 200
        assert [course["id"] for course in program_map.json()["courses"]] == [
            higher_id,
            lower_id,
        ]
        assert [course["position"] for course in program_map.json()["courses"]] == [
            1,
            2,
        ]
        assert [
            contribution["course_id"]
            for contribution in program_map.json()["competencies"][0]["contributions"]
        ] == [higher_id, lower_id]

        conflicting_position = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 4,
                "competency_id": competency_id,
                "course_id": lower_id,
                "course_position": 1,
                "stage": "assessed",
                "rationale": "A contribution must not silently reorder the program.",
                "evidence_type": "manual_note",
            },
        )
        assert conflicting_position.status_code == 409
        assert (
            conflicting_position.json()["detail"]["code"]
            == "program_course_position_conflict"
        )
        with Session() as db:
            assert db.get(Program, program_id).version == 4
            assert [
                row.position
                for row in db.query(ProgramCourse)
                .filter(ProgramCourse.program_id == program_id)
                .order_by(ProgramCourse.position)
            ] == [1, 2]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_visual_authoring_context_and_course_order_are_safe(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        program = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={
                "code": "visual-route",
                "title": "Visual route authoring",
                "description": "A real program assembled without manual API calls.",
            },
        )
        assert program.status_code == 201
        program_id = program.json()["id"]

        with Session() as db:
            first_dataset = Dataset(name="visual-authoring-first")
            second_dataset = Dataset(name="visual-authoring-second")
            other_dataset = Dataset(name="visual-authoring-other")
            other_org = Organization(
                slug="visual-authoring-other",
                name="Other authoring organization",
                is_active=True,
            )
            db.add_all([first_dataset, second_dataset, other_dataset, other_org])
            db.flush()
            first_course = Course(
                organization_id=organization_id,
                dataset_id=first_dataset.id,
                title="A course created first",
                description="First course description " + ("x" * 600),
                source_type="manual",
            )
            second_course = Course(
                organization_id=organization_id,
                dataset_id=second_dataset.id,
                title="B course created second",
                description="Second course description",
                source_type="manual",
            )
            other_course = Course(
                organization_id=other_org.id,
                dataset_id=other_dataset.id,
                title="Other organization course",
                source_type="manual",
            )
            db.add_all([first_course, second_course, other_course])
            db.flush()
            objective = LearningObjective(
                course_id=first_course.id,
                text="Explain how the first course introduces the competency.",
                normalized_text="first course objective",
                bloom_vector=[],
                top_bloom_levels=["understand"],
                extraction_method="test",
                confidence=0.88,
                review_status="confirmed",
            )
            assessment = AssessmentItem(
                course_id=second_course.id,
                assessment_type="project",
                title="Evidence-backed project",
                text="Demonstrate the competency in a constrained project.",
                expected_answer="private expected answer",
                bloom_vector=[],
                top_bloom_levels=["apply"],
                extraction_method="test",
                confidence=0.92,
                review_status="confirmed",
            )
            db.add_all([objective, assessment])
            db.commit()
            first_course_id = first_course.id
            second_course_id = second_course.id
            other_course_id = other_course.id

        for email in ("designer@local.test", "admin@local.test"):
            context = client.get(
                f"/programs/{program_id}/authoring-context",
                headers=_headers(email),
            )
            assert context.status_code == 200
            assert context.json()["program_version"] == 1
            assert context.json()["courses_truncated"] is False
            assert {course["id"] for course in context.json()["courses"]} == {
                first_course_id,
                second_course_id,
            }
            assert all(
                course["in_program"] is False for course in context.json()["courses"]
            )
            first_summary = next(
                course
                for course in context.json()["courses"]
                if course["id"] == first_course_id
            )
            assert len(first_summary["description"]) == 500

        for email in (
            "methodologist@local.test",
            "instructor@local.test",
            "student@local.test",
        ):
            denied = client.get(
                f"/programs/{program_id}/authoring-context",
                headers=_headers(email),
            )
            assert denied.status_code == 404

        objective_options = client.get(
            f"/programs/{program_id}/courses/{first_course_id}/evidence-options",
            headers=_headers("designer@local.test"),
        )
        assert objective_options.status_code == 200
        assert objective_options.json()["options"][0]["evidence_type"] == (
            "learning_objective"
        )
        assessment_options = client.get(
            f"/programs/{program_id}/courses/{second_course_id}/evidence-options",
            headers=_headers("designer@local.test"),
        )
        assert assessment_options.status_code == 200
        assert assessment_options.json()["options"][0]["evidence_type"] == (
            "assessment_item"
        )
        serialized_options = json.dumps(assessment_options.json(), ensure_ascii=False)
        assert "private expected answer" not in serialized_options
        assert "expected_answer" not in serialized_options
        cross_org_options = client.get(
            f"/programs/{program_id}/courses/{other_course_id}/evidence-options",
            headers=_headers("designer@local.test"),
        )
        assert cross_org_options.status_code == 404

        duplicate_ids = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "course_ids": [first_course_id, first_course_id],
            },
        )
        assert duplicate_ids.status_code == 422
        ordered = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "course_ids": [second_course_id, first_course_id],
            },
        )
        assert ordered.status_code == 200
        assert ordered.json()["changed"] is True
        assert ordered.json()["program_version"] == 2
        assert [course["id"] for course in ordered.json()["courses"]] == [
            second_course_id,
            first_course_id,
        ]
        no_op = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "course_ids": [second_course_id, first_course_id],
            },
        )
        assert no_op.status_code == 200
        assert no_op.json()["changed"] is False
        assert no_op.json()["program_version"] == 2

        omission = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={"expected_version": 2, "course_ids": [first_course_id]},
        )
        assert omission.status_code == 409
        assert omission.json()["detail"]["code"] == "program_course_removal_denied"
        cross_org_order = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "course_ids": [
                    second_course_id,
                    first_course_id,
                    other_course_id,
                ],
            },
        )
        assert cross_org_order.status_code == 404
        stale = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "course_ids": [first_course_id, second_course_id],
            },
        )
        assert stale.status_code == 409

        competency = client.post(
            f"/programs/{program_id}/competencies",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "code": "VR-01",
                "title": "Trace a safe program route",
                "position": 1,
            },
        )
        assert competency.status_code == 201
        contribution = client.put(
            f"/programs/{program_id}/contributions",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 3,
                "competency_id": competency.json()["id"],
                "course_id": second_course_id,
                "course_position": 1,
                "stage": "introduced",
                "rationale": "The selected course introduces the declared route safely.",
                "evidence_type": "manual_note",
            },
        )
        assert contribution.status_code == 200
        reordered = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 4,
                "course_ids": [first_course_id, second_course_id],
            },
        )
        assert reordered.status_code == 200
        assert reordered.json()["program_version"] == 5
        final_map = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        assert final_map.status_code == 200
        assert [course["id"] for course in final_map.json()["courses"]] == [
            first_course_id,
            second_course_id,
        ]
        assert final_map.json()["counts"]["mapped_cells"] == 1
        assert (
            final_map.json()["competencies"][0]["contributions"][0]["course_id"]
            == second_course_id
        )

        with Session() as db:
            assert db.get(Program, program_id).version == 5
            events = (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.program_id == program_id)
                .order_by(ProgramChangeEvent.id)
                .all()
            )
            assert [event.version for event in events] == [1, 2, 3, 4, 5]
            assert [event.event_type for event in events].count(
                "program_course_order_changed"
            ) == 2
            event_payload = json.dumps(
                [event.event_metadata for event in events], ensure_ascii=False
            )
            assert "First course description" not in event_payload
            assert "Evidence-backed project" not in event_payload
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_course_order_limit_matches_authoring_context():
    payload = ProgramCourseOrderIn(expected_version=1, course_ids=list(range(1, 501)))
    assert len(payload.course_ids) == 500
    with pytest.raises(ValidationError):
        ProgramCourseOrderIn(expected_version=1, course_ids=list(range(1, 502)))


def test_program_audit_preview_is_bounded_inspectable_and_read_only(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        created = client.post(
            f"/organizations/{organization_id}/programs",
            headers=_headers("designer@local.test"),
            json={"code": "AUDIT", "title": "Program audit preview"},
        )
        assert created.status_code == 201
        program_id = created.json()["id"]

        with Session() as db:
            datasets = [Dataset(name=f"program-audit-{index}") for index in range(3)]
            db.add_all(datasets)
            db.flush()
            courses = [
                Course(
                    organization_id=organization_id,
                    dataset_id=dataset.id,
                    title=title,
                    description="Program audit course",
                    source_type="manual",
                )
                for dataset, title in zip(
                    datasets,
                    ("Assessment first", "Learning middle", "Learning later"),
                )
            ]
            db.add_all(courses)
            db.flush()
            db.add_all(
                ProgramCourse(
                    program_id=program_id,
                    course_id=course.id,
                    position=position,
                )
                for position, course in enumerate(courses, start=1)
            )
            competencies = [
                Competency(
                    program_id=program_id,
                    code=code,
                    title=title,
                    position=position,
                )
                for position, (code, title) in enumerate(
                    (
                        ("AUD-01", "Unmapped competency"),
                        ("AUD-02", "No assessment"),
                        ("AUD-03", "Missing evidence"),
                        ("AUD-04", "Sequence check"),
                        ("AUD-05", "Repeated introduction"),
                        ("AUD-06", "Normal progression"),
                        ("AUD-07", "Repeated assessment only"),
                        ("AUD-08", "Repeated development"),
                    ),
                    start=1,
                )
            ]
            db.add_all(competencies)
            db.flush()
            objective = LearningObjective(
                course_id=courses[2].id,
                text="Learning evidence " + ("x" * 700),
                normalized_text="learning evidence",
                bloom_vector=[],
                top_bloom_levels=["understand"],
                extraction_method="test",
                confidence=0.58,
                review_status="unreviewed",
            )
            assessment = AssessmentItem(
                course_id=courses[0].id,
                assessment_type="project",
                title="Assessment evidence",
                text="Assess the declared competency.",
                expected_answer="private program audit answer",
                bloom_vector=[],
                top_bloom_levels=["apply"],
                extraction_method="test",
                confidence=0.91,
                review_status="confirmed",
            )
            db.add_all([objective, assessment])
            db.flush()
            db.add_all(
                [
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[1].id,
                        course_id=courses[1].id,
                        stage="introduced",
                        rationale="This course introduces the competency explicitly.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[2].id,
                        course_id=courses[1].id,
                        stage="assessed",
                        rationale="The source was removed after this mapping was saved.",
                        evidence_type="learning_objective",
                        evidence_id=999999,
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[3].id,
                        course_id=courses[0].id,
                        stage="assessed",
                        rationale="Assessment is declared before the learning course.",
                        evidence_type="assessment_item",
                        evidence_id=assessment.id,
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[3].id,
                        course_id=courses[2].id,
                        stage="introduced",
                        rationale="The later course introduces the assessed competency.",
                        evidence_type="learning_objective",
                        evidence_id=objective.id,
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[4].id,
                        course_id=courses[0].id,
                        stage="introduced",
                        rationale="The first course declares an introduction.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[4].id,
                        course_id=courses[1].id,
                        stage="introduced",
                        rationale="The second course repeats the introduction.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[4].id,
                        course_id=courses[2].id,
                        stage="assessed",
                        rationale="The later course assesses the competency.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[5].id,
                        course_id=courses[0].id,
                        stage="introduced",
                        rationale="The first course introduces the progression.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[5].id,
                        course_id=courses[1].id,
                        stage="developed",
                        rationale="The second course develops the progression.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[5].id,
                        course_id=courses[2].id,
                        stage="assessed",
                        rationale="The third course assesses the progression.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[6].id,
                        course_id=courses[0].id,
                        stage="assessed",
                        rationale="The first course assesses the competency.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[6].id,
                        course_id=courses[1].id,
                        stage="assessed",
                        rationale="The second course reassesses the competency.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[7].id,
                        course_id=courses[0].id,
                        stage="developed",
                        rationale="The first course develops the competency.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[7].id,
                        course_id=courses[1].id,
                        stage="developed",
                        rationale="The second course repeats development.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=program_id,
                        competency_id=competencies[7].id,
                        course_id=courses[2].id,
                        stage="assessed",
                        rationale="The final course assesses the competency.",
                        evidence_type="manual_note",
                    ),
                ]
            )
            duplicate_introduction_id = competencies[4].id
            normal_progression_id = competencies[5].id
            repeated_assessment_id = competencies[6].id
            duplicate_development_id = competencies[7].id
            other_org = Organization(
                slug="program-audit-other",
                name="Program audit other organization",
                is_active=True,
            )
            db.add(other_org)
            db.flush()
            other_program = Program(
                organization_id=other_org.id,
                code="OTHER",
                title="Other program",
                version=1,
                is_active=True,
            )
            db.add(other_program)
            db.commit()
            other_program_id = other_program.id

        baseline = None
        for email in (
            "methodologist@local.test",
            "designer@local.test",
            "admin@local.test",
        ):
            response = client.get(
                f"/programs/{program_id}/audit-preview",
                headers=_headers(email),
            )
            assert response.status_code == 200
            baseline = baseline or response.json()
            assert response.json() == baseline
        assert baseline is not None
        assert baseline["program_version"] == 1
        assert baseline["analysis_truncated"] is False
        assert baseline["findings_truncated"] is False
        assert baseline["counts"] == {
            "total": 6,
            "review": 3,
            "watch": 3,
            "coverage_gap": 1,
            "assessment_gap": 1,
            "evidence_gap": 1,
            "duplication_check": 2,
            "sequence_check": 1,
        }
        assert {finding["kind"] for finding in baseline["findings"]} == {
            "coverage_gap",
            "assessment_gap",
            "evidence_gap",
            "duplication_check",
            "sequence_check",
        }
        assert all(
            finding["review_status"] == "not_reviewed" and finding["confidence_label"]
            for finding in baseline["findings"]
        )
        missing = next(
            finding
            for finding in baseline["findings"]
            if finding["kind"] == "evidence_gap"
        )
        assert missing["evidence_status"] == "missing"
        assert missing["evidence"][0]["evidence_state"] == "missing"
        sequence = next(
            finding
            for finding in baseline["findings"]
            if finding["kind"] == "sequence_check"
        )
        assert sequence["confidence"] == "medium"
        assert [item["course_position"] for item in sequence["evidence"]] == [1, 3]
        duplication = [
            finding
            for finding in baseline["findings"]
            if finding["kind"] == "duplication_check"
        ]
        assert [finding["key"] for finding in duplication] == [
            f"duplication_check:{duplicate_introduction_id}",
            f"duplication_check:{duplicate_development_id}",
        ]
        assert all(finding["attention"] == "watch" for finding in duplication)
        assert all(finding["confidence"] == "medium" for finding in duplication)
        assert all(
            [item["course_position"] for item in finding["evidence"]] == [1, 2]
            for finding in duplication
        )
        assert all("спираль" in finding["detail"] for finding in duplication)
        assert not any(
            finding["kind"] == "duplication_check"
            and finding["competency_id"]
            in {normal_progression_id, repeated_assessment_id}
            for finding in baseline["findings"]
        )
        assert (
            max(
                len(item["evidence_excerpt"])
                for finding in baseline["findings"]
                for item in finding["evidence"]
            )
            <= 500
        )
        serialized = json.dumps(baseline, ensure_ascii=False)
        assert "private program audit answer" not in serialized
        assert "expected_answer" not in serialized
        assert "model_info" not in serialized

        repeated = client.get(
            f"/programs/{program_id}/audit-preview",
            headers=_headers("methodologist@local.test"),
        )
        assert repeated.json() == baseline
        monkeypatch.setattr(program_intelligence, "PROGRAM_AUDIT_EVIDENCE_LIMIT", 1)
        evidence_bounded = client.get(
            f"/programs/{program_id}/audit-preview",
            headers=_headers("methodologist@local.test"),
        )
        bounded_duplication = [
            finding
            for finding in evidence_bounded.json()["findings"]
            if finding["kind"] == "duplication_check"
        ]
        assert all(finding["evidence_truncated"] for finding in bounded_duplication)
        assert all(len(finding["evidence"]) == 1 for finding in bounded_duplication)
        monkeypatch.setattr(program_intelligence, "PROGRAM_AUDIT_EVIDENCE_LIMIT", 8)
        for email in (
            "instructor@local.test",
            "student@local.test",
        ):
            denied = client.get(
                f"/programs/{program_id}/audit-preview",
                headers=_headers(email),
            )
            assert denied.status_code == 404
        cross_org = client.get(
            f"/programs/{other_program_id}/audit-preview",
            headers=_headers("designer@local.test"),
        )
        assert cross_org.status_code == 404

        with Session() as db:
            assert db.get(Program, program_id).version == 1
            assert (
                db.query(ProgramChangeEvent)
                .filter(ProgramChangeEvent.program_id == program_id)
                .count()
                == 1
            )

        monkeypatch.setattr(program_intelligence, "AUTHORING_COURSE_LIMIT", 2)
        course_truncated = client.get(
            f"/programs/{program_id}/audit-preview",
            headers=_headers("methodologist@local.test"),
        )
        assert course_truncated.status_code == 200
        assert course_truncated.json()["analysis_truncated"] is True
        assert not any(
            finding["kind"] == "sequence_check"
            for finding in course_truncated.json()["findings"]
        )
        monkeypatch.setattr(program_intelligence, "AUTHORING_COURSE_LIMIT", 500)
        monkeypatch.setattr(program_intelligence, "PROGRAM_AUDIT_FINDING_LIMIT", 2)
        bounded = client.get(
            f"/programs/{program_id}/audit-preview",
            headers=_headers("methodologist@local.test"),
        )
        assert bounded.status_code == 200
        assert bounded.json()["findings_truncated"] is True
        assert bounded.json()["counts"]["total"] == 2
        monkeypatch.setattr(program_intelligence, "PROGRAM_AUDIT_COMPETENCY_LIMIT", 2)
        truncated = client.get(
            f"/programs/{program_id}/audit-preview",
            headers=_headers("methodologist@local.test"),
        )
        assert truncated.status_code == 200
        assert truncated.json()["analysis_truncated"] is True
        assert truncated.json()["analyzed_competencies"] == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_program_administration_overview_is_aggregate_bounded_and_admin_only(
    monkeypatch,
):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        demo = client.post(
            f"/organizations/{organization_id}/programs/demo",
            headers=_headers("designer@local.test"),
        )
        assert demo.status_code == 201

        with Session() as db:
            admin = db.query(User).filter(User.email == "admin@local.test").one()
            datasets = [
                Dataset(name="overview-assessment"),
                Dataset(name="overview-complete"),
                Dataset(name="overview-other-org"),
            ]
            db.add_all(datasets)
            db.flush()
            empty_org = Organization(
                slug="overview-empty",
                name="Overview empty organization",
                is_active=True,
            )
            hidden_org = Organization(
                slug="overview-hidden",
                name="Overview hidden organization",
                is_active=True,
            )
            db.add_all([empty_org, hidden_org])
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=empty_org.id,
                    user_id=admin.id,
                    role="administrator",
                    is_active=True,
                )
            )
            assessment_course = Course(
                organization_id=organization_id,
                dataset_id=datasets[0].id,
                title="Assessment route course",
                description="Local overview course",
                source_type="manual",
            )
            complete_course = Course(
                organization_id=organization_id,
                dataset_id=datasets[1].id,
                title="Complete route course",
                description="Local overview course",
                source_type="manual",
            )
            other_course = Course(
                organization_id=hidden_org.id,
                dataset_id=datasets[2].id,
                title="Cross organization course",
                description="Must not count in the local overview",
                source_type="manual",
            )
            db.add_all([assessment_course, complete_course, other_course])
            db.flush()
            assessment_program = Program(
                organization_id=organization_id,
                code="ASSESS",
                title="A Assessment declaration",
                description="Mapped without assessment",
                version=1,
                is_active=True,
            )
            complete_program = Program(
                organization_id=organization_id,
                code="COMPLETE",
                title="B Declared complete",
                description="All competencies have an assessment declaration",
                version=1,
                is_active=True,
            )
            invalid_program = Program(
                organization_id=organization_id,
                code="INVALID",
                title="C Cross organization only",
                description="Invalid direct database fixture",
                version=1,
                is_active=True,
            )
            hidden_program = Program(
                organization_id=hidden_org.id,
                code="HIDDEN",
                title="Hidden program title",
                description="Must never be disclosed",
                version=1,
                is_active=True,
            )
            db.add_all(
                [
                    assessment_program,
                    complete_program,
                    invalid_program,
                    hidden_program,
                ]
            )
            db.flush()
            db.add_all(
                [
                    ProgramCourse(
                        program_id=assessment_program.id,
                        course_id=assessment_course.id,
                        position=1,
                    ),
                    ProgramCourse(
                        program_id=complete_program.id,
                        course_id=complete_course.id,
                        position=1,
                    ),
                    ProgramCourse(
                        program_id=invalid_program.id,
                        course_id=other_course.id,
                        position=1,
                    ),
                ]
            )
            assessment_competency = Competency(
                program_id=assessment_program.id,
                code="ASSESS-01",
                title="Mapped but not assessed",
                position=1,
            )
            complete_competency = Competency(
                program_id=complete_program.id,
                code="COMPLETE-01",
                title="Mapped and assessed",
                position=1,
            )
            invalid_competency = Competency(
                program_id=invalid_program.id,
                code="INVALID-01",
                title="Cross organization declaration",
                position=1,
            )
            db.add_all(
                [
                    assessment_competency,
                    complete_competency,
                    invalid_competency,
                ]
            )
            db.flush()
            db.add_all(
                [
                    CourseContribution(
                        program_id=assessment_program.id,
                        competency_id=assessment_competency.id,
                        course_id=assessment_course.id,
                        stage="introduced",
                        rationale="The course introduces this competency.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=complete_program.id,
                        competency_id=complete_competency.id,
                        course_id=complete_course.id,
                        stage="assessed",
                        rationale="The course declares an assessment.",
                        evidence_type="manual_note",
                    ),
                    CourseContribution(
                        program_id=invalid_program.id,
                        competency_id=invalid_competency.id,
                        course_id=other_course.id,
                        stage="assessed",
                        rationale="This cross-organization relation must not count.",
                        evidence_type="manual_note",
                    ),
                ]
            )
            db.commit()
            empty_org_id = empty_org.id
            hidden_org_id = hidden_org.id
            change_event_count = db.query(ProgramChangeEvent).count()

        endpoint = f"/organizations/{organization_id}/program-administration-overview"
        response = client.get(endpoint, headers=_headers("admin@local.test"))
        assert response.status_code == 200
        payload = response.json()
        assert payload["analysis_truncated"] is False
        assert [item["program_title"] for item in payload["programs"]] == sorted(
            item["program_title"] for item in payload["programs"]
        )
        assert payload["totals"] == {
            "programs": 4,
            "courses": 4,
            "competencies": 6,
            "mapped_competencies": 4,
            "assessed_competencies": 2,
            "programs_requiring_review": 3,
            "programs_not_started": 1,
        }
        states = {item["program_code"]: item for item in payload["programs"]}
        assert states["ASSESS"]["route_state"] == "assessment_gap"
        assert states["COMPLETE"]["route_state"] == ("declared_assessment_complete")
        assert states["INVALID"]["route_state"] == "not_started"
        assert states["INVALID"]["course_count"] == 0
        assert states["INVALID"]["mapped_competency_count"] == 0
        assert states["CS-FOUND"]["route_state"] == "mapping_gap"
        assert all(
            item["confidence_label"] == "Факт по сохранённой карте"
            and item["review_status"] == "not_reviewed"
            for item in payload["programs"]
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "Hidden program title" not in serialized
        assert "development seed answer" not in serialized
        assert "expected_answer" not in serialized
        assert "student" not in serialized
        assert "teacher" not in serialized

        for email in (
            "designer@local.test",
            "methodologist@local.test",
            "instructor@local.test",
            "student@local.test",
        ):
            denied = client.get(endpoint, headers=_headers(email))
            assert denied.status_code == 404
        hidden = client.get(
            f"/organizations/{hidden_org_id}/program-administration-overview",
            headers=_headers("admin@local.test"),
        )
        assert hidden.status_code == 404
        empty = client.get(
            f"/organizations/{empty_org_id}/program-administration-overview",
            headers=_headers("admin@local.test"),
        )
        assert empty.status_code == 200
        assert empty.json()["programs"] == []
        assert empty.json()["totals"]["programs"] == 0

        with Session() as db:
            assert db.query(ProgramChangeEvent).count() == change_event_count

        monkeypatch.setattr(program_intelligence, "PROGRAM_ADMIN_OVERVIEW_LIMIT", 2)
        truncated = client.get(endpoint, headers=_headers("admin@local.test"))
        assert truncated.status_code == 200
        assert truncated.json()["analysis_truncated"] is True
        assert len(truncated.json()["programs"]) == 2
        assert truncated.json()["totals"]["programs"] == 2
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_explicit_prerequisites_are_scoped_acyclic_versioned_and_evidence_backed(
    monkeypatch,
):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        created = client.post(
            f"/organizations/{organization_id}/programs/demo",
            headers=_headers("designer@local.test"),
        )
        assert created.status_code == 201
        program_id = created.json()["program_id"]

        with Session() as db:
            program = db.get(Program, program_id)
            competencies = (
                db.query(Competency)
                .filter(Competency.program_id == program_id)
                .order_by(Competency.position)
                .all()
            )
            courses = (
                db.query(ProgramCourse, Course)
                .join(Course, Course.id == ProgramCourse.course_id)
                .filter(ProgramCourse.program_id == program_id)
                .order_by(ProgramCourse.position)
                .all()
            )
            third_dataset = Dataset(name="prerequisite-third-course")
            db.add(third_dataset)
            db.flush()
            third_course = Course(
                organization_id=organization_id,
                dataset_id=third_dataset.id,
                title="Capstone after prerequisite",
                description="Target competency starts after prerequisite assessment.",
                source_type="manual",
            )
            db.add(third_course)
            db.flush()
            db.add(
                ProgramCourse(
                    program_id=program_id,
                    course_id=third_course.id,
                    position=3,
                )
            )
            db.add(
                CourseContribution(
                    program_id=program_id,
                    competency_id=competencies[2].id,
                    course_id=third_course.id,
                    stage="introduced",
                    rationale="The capstone explicitly starts the target competency.",
                    evidence_type="manual_note",
                )
            )
            other_program = Program(
                organization_id=organization_id,
                code="OTHER-PREREQ",
                title="Other prerequisite program",
                version=1,
                is_active=True,
            )
            db.add(other_program)
            db.flush()
            other_competency = Competency(
                program_id=other_program.id,
                code="OTHER-01",
                title="Other program competency",
                position=1,
            )
            db.add(other_competency)
            db.commit()
            prerequisite_id = competencies[0].id
            target_same_course_id = competencies[1].id
            target_later_id = competencies[2].id
            other_competency_id = other_competency.id
            original_course_ids = [course.id for _, course in courses]
            third_course_id = third_course.id
            assert program.version == 1

        endpoint = f"/programs/{program_id}/prerequisites"
        self_link = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": prerequisite_id,
                "rationale": "A competency should never depend on itself.",
            },
        )
        assert self_link.status_code == 409
        assert self_link.json()["detail"]["code"] == "prerequisite_self_link"

        declared = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 1,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": target_later_id,
                "rationale": "The assessed foundation should precede the capstone work.",
            },
        )
        assert declared.status_code == 200
        assert declared.json()["program_version"] == 2
        declared_relation_id = declared.json()["relation_id"]

        no_op = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 2,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": target_later_id,
                "rationale": "The assessed foundation should precede the capstone work.",
            },
        )
        assert no_op.status_code == 200
        assert no_op.json() == {
            "relation_id": declared_relation_id,
            "program_version": 2,
            "changed": False,
        }

        updated = client.put(
            endpoint,
            headers=_headers("admin@local.test"),
            json={
                "expected_version": 2,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": target_later_id,
                "rationale": "The assessed foundation is required before capstone design.",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["program_version"] == 3

        order_check = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 3,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": target_same_course_id,
                "rationale": "The foundation should be complete before structure selection.",
            },
        )
        assert order_check.status_code == 200
        assert order_check.json()["program_version"] == 4

        needs_evidence = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 4,
                "prerequisite_competency_id": target_later_id,
                "target_competency_id": target_same_course_id,
                "rationale": "Capstone documentation should precede structure selection.",
            },
        )
        assert needs_evidence.status_code == 200
        assert needs_evidence.json()["program_version"] == 5
        needs_evidence_relation_id = needs_evidence.json()["relation_id"]

        cycle = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 5,
                "prerequisite_competency_id": target_same_course_id,
                "target_competency_id": prerequisite_id,
                "rationale": "This reverse relation would close a transitive cycle.",
            },
        )
        assert cycle.status_code == 409
        assert cycle.json()["detail"]["code"] == "prerequisite_cycle"

        cross_program = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 5,
                "prerequisite_competency_id": prerequisite_id,
                "target_competency_id": other_competency_id,
                "rationale": "A cross-program dependency must remain undisclosed.",
            },
        )
        assert cross_program.status_code == 404
        stale = client.put(
            endpoint,
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 4,
                "prerequisite_competency_id": target_same_course_id,
                "target_competency_id": target_later_id,
                "rationale": "This write uses a stale optimistic version.",
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "program_version_conflict"
        for email in (
            "methodologist@local.test",
            "instructor@local.test",
            "student@local.test",
        ):
            denied = client.put(
                endpoint,
                headers=_headers(email),
                json={
                    "expected_version": 5,
                    "prerequisite_competency_id": target_same_course_id,
                    "target_competency_id": target_later_id,
                    "rationale": "This role cannot author prerequisite relations.",
                },
            )
            assert denied.status_code == 404

        program_map = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        assert program_map.status_code == 200
        payload = program_map.json()
        assert payload["prerequisites_truncated"] is False
        assert len(payload["prerequisites"]) == 3
        relations = {
            (
                item["prerequisite_competency_id"],
                item["target_competency_id"],
            ): item
            for item in payload["prerequisites"]
        }
        assert (
            relations[(prerequisite_id, target_later_id)]["structural_state"]
            == "declared_order"
        )
        assert (
            relations[(prerequisite_id, target_same_course_id)]["structural_state"]
            == "order_check"
        )
        assert (
            relations[(target_later_id, target_same_course_id)]["structural_state"]
            == "needs_evidence"
        )
        declared_item = relations[(prerequisite_id, target_later_id)]
        assert declared_item["prerequisite_assessment"]["course_position"] == 2
        assert declared_item["target_start"]["course_position"] == 3
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "development seed answer must never leave the backend" not in serialized
        assert "expected_answer" not in serialized
        assert "model_info" not in serialized

        monkeypatch.setattr(program_intelligence, "PROGRAM_PREREQUISITE_LIMIT", 2)
        bounded = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        assert bounded.status_code == 200
        assert bounded.json()["prerequisites_truncated"] is True
        assert len(bounded.json()["prerequisites"]) == 2
        monkeypatch.setattr(program_intelligence, "PROGRAM_PREREQUISITE_LIMIT", 500)

        reordered = client.put(
            f"/programs/{program_id}/courses",
            headers=_headers("designer@local.test"),
            json={
                "expected_version": 5,
                "course_ids": [third_course_id, *original_course_ids],
            },
        )
        assert reordered.status_code == 200
        assert reordered.json()["program_version"] == 6
        recomputed = client.get(
            f"/programs/{program_id}/map",
            headers=_headers("methodologist@local.test"),
        )
        recomputed_relation = next(
            item
            for item in recomputed.json()["prerequisites"]
            if item["id"] == declared_relation_id
        )
        assert recomputed_relation["structural_state"] == "order_check"

        denied_delete = client.request(
            "DELETE",
            f"{endpoint}/{needs_evidence_relation_id}",
            headers=_headers("methodologist@local.test"),
            json={"expected_version": 6},
        )
        assert denied_delete.status_code == 404
        deleted = client.request(
            "DELETE",
            f"{endpoint}/{needs_evidence_relation_id}",
            headers=_headers("admin@local.test"),
            json={"expected_version": 6},
        )
        assert deleted.status_code == 200
        assert deleted.json()["program_version"] == 7

        with Session() as db:
            assert db.get(Program, program_id).version == 7
            assert (
                db.query(ProgramPrerequisiteRelation)
                .filter(ProgramPrerequisiteRelation.program_id == program_id)
                .count()
                == 2
            )
            events = (
                db.query(ProgramChangeEvent)
                .filter(
                    ProgramChangeEvent.program_id == program_id,
                    ProgramChangeEvent.event_type.like("program_prerequisite_%"),
                )
                .order_by(ProgramChangeEvent.id)
                .all()
            )
            assert [event.event_type for event in events] == [
                "program_prerequisite_created",
                "program_prerequisite_updated",
                "program_prerequisite_created",
                "program_prerequisite_created",
                "program_prerequisite_deleted",
            ]
            assert all("rationale" not in event.event_metadata for event in events)
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_demo_seed_is_disabled_by_production_policy(monkeypatch):
    client, engine, Session = _client(monkeypatch)
    try:
        organization_id = _bootstrap(client)
        with Session() as db:
            designer = db.query(User).filter(User.email == "designer@local.test").one()
            monkeypatch.setenv("APP_ENV", "production")
            monkeypatch.setenv("ENABLE_DEMO_SEED", "1")
            with pytest.raises(ProgramScopeDenied):
                create_demo_program(
                    db,
                    organization_id=organization_id,
                    actor_user_id=designer.id,
                )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
