import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.models.base import Base
from backend.app.models.models import (
    AlignmentCandidate,
    AlignmentEdge,
    AuditRun,
    Chunk,
    Course,
    CourseFinding,
    CourseModule,
    Dataset,
    Document,
    LearningObjective,
)
from backend.app.services.course_audit import CourseAuditService


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


def _seed_course(db):
    dataset = Dataset(name="course-audit")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Алгоритмы", source_type="manual")
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, title="Сложность", position=1)
    db.add(module)
    db.flush()

    rows = [
        (
            "Цели.txt",
            "learning_objectives",
            "После модуля студент сможет анализировать временную сложность алгоритмов. "
            "После модуля студент сможет оценивать надежность распределенных систем.",
        ),
        (
            "Лекция.txt",
            "lecture_material",
            "Временная сложность алгоритмов описывает рост числа операций и сравнение алгоритмов.",
        ),
        (
            "Задание.txt",
            "assignment",
            "Назовите определение временной сложности алгоритмов.",
        ),
    ]
    for title, kind, text in rows:
        document = Document(
            dataset_id=dataset.id,
            course_module_id=module.id,
            title=title,
            source=f"test://{title}",
            status="ready",
            source_metadata={"document_type": kind},
        )
        db.add(document)
        db.flush()
        db.add(
            Chunk(
                document_id=document.id,
                idx=0,
                text=text,
                meta={
                    "source_start": 0,
                    "source_end": len(text),
                    "sentence_start": 0,
                    "sentence_end": 1,
                },
            )
        )
    db.commit()
    return course


def _new_run(db, course):
    run = AuditRun(
        course_id=course.id,
        status="queued",
        pipeline_version="test",
        extractor_version="test",
        classifier_version="test",
        embedding_model="hash:test",
        relation_model="test",
        config={"min_relation_score": 0.2},
        metrics={},
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def test_audit_vertical_slice_is_idempotent_and_evidence_backed():
    engine, db = _db()
    course = _seed_course(db)
    run = _new_run(db, course)

    metrics = CourseAuditService(db).run(course.id, run.id)
    assert metrics["summary"]["objectives_total"] == 2
    assert metrics["summary"]["materials_total"] == 1
    assert metrics["summary"]["assessments_total"] == 1
    assert metrics["summary"]["objectives_with_material"] >= 1
    assert metrics["summary"]["objectives_with_assessment"] >= 1

    finding_types = {
        item.finding_type
        for item in db.query(CourseFinding).filter_by(audit_run_id=run.id)
    }
    assert "objective_without_material" in finding_types
    assert "objective_without_assessment" in finding_types
    assert "bloom_mismatch" in finding_types
    for finding in db.query(CourseFinding).filter_by(audit_run_id=run.id):
        assert finding.evidence
        assert finding.model_info["fingerprint"]

    counts_before = (
        db.query(LearningObjective).filter_by(audit_run_id=run.id).count(),
        db.query(AlignmentEdge).filter_by(audit_run_id=run.id).count(),
        db.query(AlignmentCandidate).filter_by(audit_run_id=run.id).count(),
        db.query(CourseFinding).filter_by(audit_run_id=run.id).count(),
    )
    CourseAuditService(db).run(course.id, run.id)
    counts_after = (
        db.query(LearningObjective).filter_by(audit_run_id=run.id).count(),
        db.query(AlignmentEdge).filter_by(audit_run_id=run.id).count(),
        db.query(AlignmentCandidate).filter_by(audit_run_id=run.id).count(),
        db.query(CourseFinding).filter_by(audit_run_id=run.id).count(),
    )
    assert counts_after == counts_before
    assert (
        counts_after[2]
        == metrics["summary"]["objectives_total"]
        * metrics["summary"]["assessments_total"]
    )
    db.close()
    engine.dispose()


def test_review_decision_survives_new_audit_run():
    engine, db = _db()
    course = _seed_course(db)
    first = _new_run(db, course)
    CourseAuditService(db).run(course.id, first.id)
    reviewed = db.query(CourseFinding).filter_by(audit_run_id=first.id).first()
    reviewed.status = "confirmed"
    reviewed.reviewed_by = "teacher"
    db.commit()

    second = _new_run(db, course)
    CourseAuditService(db).run(course.id, second.id)
    carried = [
        item
        for item in db.query(CourseFinding).filter_by(audit_run_id=second.id).all()
        if item.model_info.get("carried_review_from") == reviewed.id
    ]
    assert carried
    assert carried[0].status == "confirmed"
    assert carried[0].reviewed_by == "teacher"
    db.close()
    engine.dispose()
