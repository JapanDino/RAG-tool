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
    AssessmentItem,
    AuditRun,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseModule,
    Dataset,
    Document,
)
from backend.app.services.canvas_change_set import (
    build_canvas_change_set,
    canvas_change_set_markdown,
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


def _suggestion(db, course, run, finding, action_type, status="accepted"):
    item = CourseCopilotSuggestion(
        finding_id=finding.id,
        course_id=course.id,
        audit_run_id=run.id,
        action_type=action_type,
        title=f"Draft {action_type}",
        draft="Grounded teacher-editable draft.",
        target_bloom_level="analyze",
        rationale="Closes the audited course gap.",
        citations=[
            {
                "source_id": "S1",
                "chunk_id": 1,
                "document_id": 1,
                "document_title": "Lecture",
                "module_id": finding.module_id,
                "module_title": "Sorting",
                "quote": "Course evidence.",
                "source_url": "https://canvas.example.edu/courses/42/pages/sorting",
                "score": 0.8,
            }
        ],
        confidence=0.8,
        retrieval_method="hybrid:test",
        generation_provider="litellm",
        generation_model="test-model",
        status=status,
    )
    db.add(item)
    db.flush()
    return item


def _seed(db):
    dataset = Dataset(name="canvas-change-set")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id,
        external_id="42",
        title="Algorithms",
        source_type="canvas",
        source_url="https://canvas.example.edu/courses/42",
    )
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, external_id="7", title="Sorting")
    db.add(module)
    db.flush()
    assignment_doc = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title="Compare algorithms",
        source="https://canvas.example.edu/courses/42/assignments/9",
        source_metadata={"document_type": "assignment", "canvas_assignment_id": "9"},
    )
    db.add(assignment_doc)
    db.flush()
    run = AuditRun(course_id=course.id, status="done")
    db.add(run)
    db.flush()
    assessment = AssessmentItem(
        course_id=course.id,
        audit_run_id=run.id,
        module_id=module.id,
        document_id=assignment_doc.id,
        title="Compare algorithms",
        text="Compare quicksort and mergesort.",
    )
    db.add(assessment)
    db.flush()
    create_finding = CourseFinding(
        course_id=course.id,
        module_id=module.id,
        audit_run_id=run.id,
        finding_type="objective_without_material",
        severity="medium",
        title="Missing material",
        description="Missing",
        evidence=[],
        recommendation="Add",
        confidence=0.8,
        uncertainty_reasons=[],
        model_info={},
    )
    revise_finding = CourseFinding(
        course_id=course.id,
        module_id=module.id,
        audit_run_id=run.id,
        finding_type="bloom_mismatch",
        severity="high",
        title="Mismatch",
        description="Mismatch",
        evidence=[{"object_type": "assessment_item", "object_id": assessment.id}],
        recommendation="Revise",
        confidence=0.8,
        uncertainty_reasons=[],
        model_info={},
    )
    db.add_all([create_finding, revise_finding])
    db.flush()
    create = _suggestion(db, course, run, create_finding, "create_material")
    revise = _suggestion(db, course, run, revise_finding, "revise_assessment")
    _suggestion(db, course, run, create_finding, "create_material", status="draft")
    db.commit()
    return course, create, revise


def test_canvas_change_set_maps_accepted_drafts_to_canvas_operations():
    engine, _, db = _db()
    course, create, revise = _seed(db)
    change_set = build_canvas_change_set(db, course)
    assert change_set.available is True
    assert change_set.accepted_suggestions == 2
    assert change_set.ready_items == 2
    assert [item.suggestion_id for item in change_set.items] == [create.id, revise.id]
    assert change_set.items[0].operation == "create_page"
    assert change_set.items[0].module_external_id == "7"
    assert change_set.items[1].operation == "update_assignment"
    assert change_set.items[1].target_external_id == "9"
    assert change_set.items[1].api_path.endswith("/assignments/9")
    markdown = canvas_change_set_markdown(change_set)
    assert "READ-ONLY PREVIEW" in markdown
    assert "PUT /api/v1/courses/42/assignments/9" in markdown
    assert "Grounded teacher-editable draft" in markdown
    assignment_doc = db.query(Document).filter(Document.external_id.is_(None)).first()
    assignment_doc.source_metadata = {"document_type": "assignment"}
    db.commit()
    unmapped = build_canvas_change_set(db, course)
    update_item = next(
        item for item in unmapped.items if item.operation == "update_assignment"
    )
    assert update_item.ready_for_canvas is False
    assert update_item.warning
    assert unmapped.ready_items == 1
    db.close()
    engine.dispose()


def test_canvas_change_set_download_and_non_canvas_guard():
    engine, Session, db = _db()
    course, _, _ = _seed(db)
    manual_dataset = Dataset(name="manual-change-set")
    db.add(manual_dataset)
    db.flush()
    manual = Course(dataset_id=manual_dataset.id, title="Manual")
    db.add(manual)
    db.commit()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    preview = client.get(f"/courses/{course.id}/canvas-change-set")
    assert preview.status_code == 200
    assert preview.json()["accepted_suggestions"] == 2
    markdown = client.get(
        f"/courses/{course.id}/canvas-change-set/download?format=markdown"
    )
    assert markdown.status_code == 200
    assert (
        markdown.headers["content-disposition"]
        == f'attachment; filename="canvas-change-set-{course.id}.md"'
    )
    payload = client.get(f"/courses/{course.id}/canvas-change-set/download?format=json")
    assert payload.status_code == 200
    assert payload.json()["ready_items"] == 2
    portable = client.get(f"/courses/{manual.id}/canvas-change-set")
    assert portable.status_code == 200
    assert portable.json()["available"] is True
    assert portable.json()["ready_items"] == 0
    portable_download = client.get(f"/courses/{manual.id}/canvas-change-set/download")
    assert portable_download.status_code == 200
    assert "not connected to Canvas" in portable_download.text
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
