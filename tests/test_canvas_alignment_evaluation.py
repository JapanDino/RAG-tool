import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.models import (
    AlignmentCandidate,
    AlignmentEdge,
    AssessmentItem,
    AuditRun,
    CanvasOutcomeAlignment,
    Course,
    Dataset,
    Document,
    LearningObjective,
)
from backend.app.services.canvas_alignment_calibration import calibrate_canvas_alignment
from backend.app.services.canvas_alignment_evaluation import evaluate_canvas_alignment


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session()


def test_canvas_alignment_evaluation_reports_tp_fp_fn_and_mapping_coverage():
    engine, db = _db()
    dataset = Dataset(name="canvas-eval")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Algorithms", source_type="canvas")
    db.add(course)
    db.flush()
    run = AuditRun(course_id=course.id, status="done")
    db.add(run)
    db.flush()

    outcome_docs = []
    for outcome_id in ("o1", "o2", "o3"):
        document = Document(
            dataset_id=dataset.id,
            title=f"Outcome {outcome_id}",
            source="canvas",
            external_id=f"canvas:outcome:{outcome_id}",
            source_metadata={"canvas_outcome_id": outcome_id},
        )
        db.add(document)
        db.flush()
        outcome_docs.append(document)
    assignment_docs = []
    for assignment_id in ("a1", "a2"):
        document = Document(
            dataset_id=dataset.id,
            title=f"Assignment {assignment_id}",
            source="canvas",
            external_id=f"canvas:assignment:{assignment_id}",
            source_metadata={"canvas_assignment_id": assignment_id},
        )
        db.add(document)
        db.flush()
        assignment_docs.append(document)

    objectives = [
        LearningObjective(
            course_id=course.id, audit_run_id=run.id, document_id=doc.id, text=doc.title
        )
        for doc in outcome_docs[:2]
    ]
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
    db.add_all([*objectives, *assessments])
    db.flush()
    db.add_all(
        [
            CanvasOutcomeAlignment(
                course_id=course.id,
                outcome_external_id="o1",
                assignment_external_id="a1",
            ),
            CanvasOutcomeAlignment(
                course_id=course.id,
                outcome_external_id="o2",
                assignment_external_id="a2",
            ),
            CanvasOutcomeAlignment(
                course_id=course.id,
                outcome_external_id="o3",
                assignment_external_id="a2",
            ),
            AlignmentEdge(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objectives[0].id,
                target_type="assessment_item",
                target_id=assessments[0].id,
                relation_type="assesses",
            ),
            AlignmentEdge(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objectives[0].id,
                target_type="assessment_item",
                target_id=assessments[1].id,
                relation_type="assesses",
            ),
        ]
    )
    db.commit()

    result = evaluate_canvas_alignment(db, run.id)

    assert result["available"] is True
    assert result["explicit_pairs"] == 3
    assert result["inferred_pairs"] == 2
    assert result["true_positives"] == 1
    assert result["false_positives"] == 1
    assert result["false_negatives"] == 1
    assert result["precision"] == 0.5
    assert result["recall"] == 0.5
    assert result["f1"] == 0.5
    assert result["mapping_coverage"] == pytest.approx(2 / 3, abs=0.0001)
    assert len(result["unmapped_explicit"]) == 1

    db.add_all(
        [
            AlignmentCandidate(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objectives[0].id,
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
                source_id=objectives[0].id,
                target_type="assessment_item",
                target_id=assessments[1].id,
                relation_type="assesses",
                score=0.7,
                selected=True,
            ),
            AlignmentCandidate(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objectives[1].id,
                target_type="assessment_item",
                target_id=assessments[0].id,
                relation_type="assesses",
                score=0.6,
                selected=True,
            ),
            AlignmentCandidate(
                course_id=course.id,
                audit_run_id=run.id,
                source_type="learning_objective",
                source_id=objectives[1].id,
                target_type="assessment_item",
                target_id=assessments[1].id,
                relation_type="assesses",
                score=0.4,
                selected=True,
            ),
        ]
    )
    db.commit()
    calibration = calibrate_canvas_alignment(db, run.id)
    assert calibration["available"] is True
    assert calibration["current_threshold"] == 0.22
    assert calibration["current"]["true_positives"] == 2
    assert calibration["current"]["false_positives"] == 2
    assert calibration["recommended_threshold"] == 0.8
    assert calibration["recommended"]["precision"] == 1.0
    assert calibration["recommended"]["recall"] == 0.5
    assert calibration["reliable"] is False
    assert len(calibration["curve"]) >= 21
    db.close()
    engine.dispose()


def test_canvas_alignment_evaluation_is_unavailable_without_canvas_reference():
    engine, db = _db()
    dataset = Dataset(name="manual-eval")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Manual")
    db.add(course)
    db.flush()
    run = AuditRun(course_id=course.id, status="done")
    db.add(run)
    db.commit()

    assert evaluate_canvas_alignment(db, run.id) == {"available": False}
    db.close()
    engine.dispose()
