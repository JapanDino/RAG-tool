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
    AlignmentCandidate,
    AssessmentItem,
    AuditRun,
    CanvasOutcomeAlignment,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseQuestionAnswer,
    Dataset,
    Document,
    LearningObjective,
)
from backend.app.services.ml_feedback_export import (
    build_ml_feedback_rows,
    ml_feedback_summary,
)


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session, Session()


def _seed(db):
    dataset = Dataset(name="feedback-export")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id,
        external_id="42",
        title="Algorithms",
        source_type="canvas",
    )
    db.add(course)
    db.flush()
    outcome_doc = Document(
        dataset_id=dataset.id,
        title="Outcome",
        source="canvas",
        source_metadata={
            "document_type": "learning_objectives",
            "canvas_outcome_id": "o1",
        },
    )
    assignment_docs = [
        Document(
            dataset_id=dataset.id,
            title=f"Assignment {index}",
            source="canvas",
            source_metadata={
                "document_type": "assignment",
                "canvas_assignment_id": f"a{index}",
            },
        )
        for index in (1, 2)
    ]
    db.add_all([outcome_doc, *assignment_docs])
    db.flush()
    run = AuditRun(course_id=course.id, status="done")
    db.add(run)
    db.flush()
    objective = LearningObjective(
        course_id=course.id,
        audit_run_id=run.id,
        document_id=outcome_doc.id,
        text="Analyze algorithms",
    )
    assessments = [
        AssessmentItem(
            course_id=course.id,
            audit_run_id=run.id,
            document_id=doc.id,
            title=doc.title,
            text=doc.title,
        )
        for doc in assignment_docs
    ]
    db.add_all([objective, *assessments])
    db.flush()
    finding = CourseFinding(
        course_id=course.id,
        audit_run_id=run.id,
        finding_type="bloom_mismatch",
        severity="high",
        title="Mismatch",
        description="Mismatch",
        evidence=[],
        recommendation="Revise",
        confidence=0.7,
        uncertainty_reasons=[],
        status="confirmed",
        reviewed_by="teacher@example.org",
        model_info={},
    )
    db.add(finding)
    db.flush()
    suggestion = CourseCopilotSuggestion(
        finding_id=finding.id,
        course_id=course.id,
        audit_run_id=run.id,
        action_type="revise_assessment",
        title="Revision",
        draft="Revised task",
        target_bloom_level="analyze",
        rationale="Aligns levels",
        citations=[],
        confidence=0.7,
        retrieval_method="hybrid",
        generation_provider="litellm",
        generation_model="model",
        status="accepted",
        reviewed_by="teacher@example.org",
    )
    superseded = CourseCopilotSuggestion(
        finding_id=finding.id,
        course_id=course.id,
        audit_run_id=run.id,
        action_type="revise_assessment",
        title="Old revision",
        draft="Old task",
        target_bloom_level="analyze",
        rationale="Old rationale",
        citations=[],
        confidence=0.6,
        retrieval_method="hybrid",
        generation_provider="litellm",
        generation_model="model",
        status="rejected",
        review_reason="superseded",
        reviewed_by="teacher@example.org",
    )
    answer = CourseQuestionAnswer(
        course_id=course.id,
        question="What is quicksort?",
        answer="A sorting algorithm.",
        citations=[],
        confidence=0.8,
        retrieval_method="hybrid",
        generation_provider="litellm",
        feedback_status="helpful",
        feedback_comment="Correct",
        reviewed_by="teacher@example.org",
    )
    db.add_all(
        [
            suggestion,
            superseded,
            answer,
            CanvasOutcomeAlignment(
                course_id=course.id,
                outcome_external_id="o1",
                assignment_external_id="a1",
            ),
            AlignmentCandidate(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objective.id,
                target_type="assessment_item",
                target_id=assessments[0].id,
                relation_type="assesses",
                score=0.8,
                selected=True,
            ),
            AlignmentCandidate(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objective.id,
                target_type="assessment_item",
                target_id=assessments[1].id,
                relation_type="assesses",
                score=0.4,
                selected=False,
            ),
        ]
    )
    db.commit()
    return course


def test_ml_feedback_export_combines_teacher_and_canvas_labels_without_reviewer_pii():
    engine, _, db = _db()
    course = _seed(db)
    rows, warnings = build_ml_feedback_rows(db, course)
    assert {item["example_type"] for item in rows} == {
        "course_qa",
        "course_finding",
        "copilot_remediation",
        "canvas_alignment",
    }
    assert len(rows) == 5
    assert all(item.get("review", {}) == {} for item in rows)
    assert not any("teacher@example.org" in json.dumps(item) for item in rows)
    negative = next(
        item
        for item in rows
        if item["example_type"] == "canvas_alignment" and item["label"] == "not_aligned"
    )
    assert negative["weak_negative"] is True
    assert any("weak negatives" in warning for warning in warnings)
    summary = ml_feedback_summary(course, rows, warnings)
    assert summary.total_examples == 5
    assert summary.positive_examples == 4
    assert summary.negative_examples == 1

    private_rows, _ = build_ml_feedback_rows(db, course, include_review_metadata=True)
    assert any(
        item.get("review", {}).get("reviewed_by") == "teacher@example.org"
        for item in private_rows
    )
    db.close()
    engine.dispose()


def test_ml_feedback_jsonl_api_is_course_scoped_and_downloadable():
    engine, Session, db = _db()
    course = _seed(db)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    summary = client.get(f"/courses/{course.id}/ml-feedback")
    assert summary.status_code == 200
    assert summary.json()["total_examples"] == 5
    download = client.get(f"/courses/{course.id}/ml-feedback/download")
    assert download.status_code == 200
    assert (
        download.headers["content-disposition"]
        == f'attachment; filename="course-ml-feedback-{course.id}.jsonl"'
    )
    rows = [json.loads(line) for line in download.text.splitlines()]
    assert len(rows) == 5
    assert not any("teacher@example.org" in line for line in download.text.splitlines())
    private = client.get(
        f"/courses/{course.id}/ml-feedback/download?include_review_metadata=true"
    )
    assert "teacher@example.org" in private.text
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
