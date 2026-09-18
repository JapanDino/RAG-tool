import hashlib
import io
import json
import zipfile

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
    AuditRun,
    Chunk,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseModule,
    CourseQuestionAnswer,
    Dataset,
    Document,
)
from backend.app.services.evaluation_protocol import run_evaluation_protocol
from backend.app.services.evidence_pack import (
    build_evidence_pack,
    build_evidence_pack_preview,
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


def _seed_complete(db):
    dataset = Dataset(name="evidence-pack")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id,
        title="Algorithms",
        source_type="manual",
        source_metadata={"api_key": "must-not-leak"},
    )
    db.add(course)
    db.flush()
    module = CourseModule(course_id=course.id, external_id="m1", title="Sorting")
    db.add(module)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        course_module_id=module.id,
        title="Sorting lecture",
        source="test://sorting",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "access_token": "must-not-leak",
        },
    )
    db.add(document)
    db.flush()
    chunk_text = "Quicksort has average time complexity O(n log n)."
    chunk = Chunk(document_id=document.id, idx=0, text=chunk_text, meta={})
    db.add(chunk)
    db.flush()
    run = AuditRun(
        course_id=course.id, status="done", metrics={"summary": {"objectives_total": 1}}
    )
    db.add(run)
    db.flush()
    finding = CourseFinding(
        course_id=course.id,
        module_id=module.id,
        audit_run_id=run.id,
        finding_type="objective_without_material",
        severity="medium",
        title="Missing material",
        description="Missing",
        evidence=[],
        recommendation="Add material",
        confidence=0.8,
        uncertainty_reasons=[],
        status="confirmed",
        reviewed_by="teacher@example.org",
        model_info={},
    )
    db.add(finding)
    db.flush()
    citation = {
        "source_id": "S1",
        "chunk_id": chunk.id,
        "document_id": document.id,
        "document_title": document.title,
        "module_id": module.id,
        "module_title": module.title,
        "quote": chunk_text,
        "source_url": document.source,
        "score": 0.9,
    }
    db.add(
        CourseCopilotSuggestion(
            finding_id=finding.id,
            course_id=course.id,
            audit_run_id=run.id,
            action_type="create_material",
            title="New material",
            draft="Grounded material draft",
            target_bloom_level="analyze",
            rationale="Closes the gap",
            citations=[citation],
            confidence=0.8,
            retrieval_method="hybrid:test",
            generation_provider="litellm",
            generation_model="test-model",
            status="accepted",
            review_reason="teacher_accepted",
            reviewed_by="teacher@example.org",
        )
    )
    db.add(
        CourseQuestionAnswer(
            course_id=course.id,
            question="What is quicksort complexity?",
            answer="O(n log n).",
            citations=[citation],
            confidence=0.8,
            retrieval_method="hybrid:test",
            generation_provider="litellm",
            generation_model="test-model",
            feedback_status="helpful",
            feedback_comment="Correct",
            reviewed_by="teacher@example.org",
        )
    )
    db.commit()
    protocol = run_evaluation_protocol(db, course)
    assert protocol.status == "passed"
    return course


def test_evidence_pack_has_readiness_hash_manifest_and_privacy_defaults():
    engine, _, db = _db()
    course = _seed_complete(db)
    preview = build_evidence_pack_preview(db, course)
    assert preview.completeness_score == 90
    assert preview.ready_for_submission is True
    assert preview.latest_audit_id
    assert preview.latest_protocol_id
    assert any("Canvas" in item for item in preview.missing)

    content, generated_preview = build_evidence_pack(db, course)
    assert generated_preview.ready_for_submission is True
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = set(archive.namelist())
        assert {
            "course-summary.json",
            "audit-report.json",
            "evaluation-protocol.json",
            "evaluation-protocol.md",
            "canvas-change-set.json",
            "canvas-change-set.md",
            "qa-history.json",
            "ml-feedback.jsonl",
            "manifest.json",
        } <= names
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["privacy_mode"] == "reviewer-and-secret-metadata-removed"
        for item in manifest["files"]:
            payload = archive.read(item["name"])
            assert len(payload) == item["bytes"]
            assert hashlib.sha256(payload).hexdigest() == item["sha256"]
        combined = b"\n".join(archive.read(name) for name in names)
        assert b"teacher@example.org" not in combined
        assert b"must-not-leak" not in combined
    db.close()
    engine.dispose()


def test_evidence_pack_api_handles_incomplete_course_and_size_limit(monkeypatch):
    engine, Session, db = _db()
    dataset = Dataset(name="incomplete-evidence")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Incomplete")
    db.add(course)
    db.commit()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    preview = client.get(f"/courses/{course.id}/evidence-pack")
    assert preview.status_code == 200
    assert preview.json()["completeness_score"] == 0
    assert preview.json()["ready_for_submission"] is False
    download = client.get(f"/courses/{course.id}/evidence-pack/download")
    assert download.status_code == 200
    assert (
        download.headers["content-disposition"]
        == f'attachment; filename="course-evidence-pack-{course.id}.zip"'
    )
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        assert set(archive.namelist()) == {"course-summary.json", "manifest.json"}

    monkeypatch.setenv("EVIDENCE_PACK_MAX_BYTES", "1")
    too_large = client.get(f"/courses/{course.id}/evidence-pack/download")
    assert too_large.status_code == 413
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
