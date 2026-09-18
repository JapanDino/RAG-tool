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
from backend.app.models.models import AuditRun, Course, CourseFinding, Dataset


def test_course_audit_comparison_reports_delta_and_finding_churn():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    db = Session()
    dataset = Dataset(name="audit-comparison")
    db.add(dataset)
    db.flush()
    course = Course(
        dataset_id=dataset.id, title="Improving course", source_type="manual"
    )
    db.add(course)
    db.flush()

    def run(summary):
        item = AuditRun(
            course_id=course.id,
            status="done",
            pipeline_version="test",
            extractor_version="test",
            classifier_version="test",
            embedding_model="hash",
            relation_model="test",
            config={},
            metrics={"summary": summary},
        )
        db.add(item)
        db.flush()
        return item

    before = run(
        {
            "objective_material_coverage": 0.5,
            "objective_assessment_coverage": 0.5,
            "findings_total": 2,
            "high_severity_findings": 1,
        }
    )
    after = run(
        {
            "objective_material_coverage": 1.0,
            "objective_assessment_coverage": 0.75,
            "findings_total": 2,
            "high_severity_findings": 0,
        }
    )

    def finding(run_id, kind, fingerprint):
        db.add(
            CourseFinding(
                course_id=course.id,
                audit_run_id=run_id,
                finding_type=kind,
                severity="medium",
                title=kind,
                description=kind,
                evidence=[],
                recommendation="fix",
                confidence=0.8,
                uncertainty_reasons=[],
                status="new",
                model_info={"fingerprint": fingerprint},
            )
        )

    finding(before.id, "objective_without_material", "removed")
    finding(before.id, "objective_without_assessment", "persisted")
    finding(after.id, "objective_without_assessment", "persisted")
    finding(after.id, "bloom_mismatch", "new")
    db.commit()

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    response = TestClient(app).get(f"/courses/{course.id}/audits/compare")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["before"]["audit_run_id"] == before.id
    assert payload["after"]["audit_run_id"] == after.id
    assert payload["delta"]["objective_material_coverage"] == 0.5
    assert payload["delta"]["high_severity_findings"] == -1.0
    assert payload["new_findings"] == 1
    assert payload["removed_findings"] == 1
    assert payload["persisted_findings"] == 1
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
