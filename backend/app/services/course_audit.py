from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.models import (
    AlignmentCandidate,
    AlignmentEdge,
    AssessmentItem,
    AuditRun,
    Course,
    CourseFinding,
    Document,
    LearningMaterial,
    LearningObjective,
)
from .course_alignment import build_alignment_edges, detect_findings
from .course_extraction import extract_course_entities


class CourseAuditService:
    """Application service for one idempotent, versioned course audit run."""

    def __init__(self, db: Session):
        self.db = db

    def run(self, course_id: int, audit_run_id: int) -> dict:
        course = self.db.get(Course, course_id)
        run = self.db.get(AuditRun, audit_run_id)
        if course is None or run is None or run.course_id != course_id:
            raise ValueError("course or audit run not found")

        run.status = "running"
        run.error = None
        run.finished_at = None
        self._clear_generated_outputs(run.id)
        self.db.commit()

        try:
            documents = (
                self.db.query(Document)
                .filter(Document.dataset_id == course.dataset_id)
                .all()
            )
            if not documents:
                raise ValueError("course has no documents")
            pending = [
                document.id for document in documents if document.status != "ready"
            ]
            if pending:
                raise ValueError(f"course documents are not ready: {pending}")

            extraction = extract_course_entities(self.db, course, run)
            self._set_progress(run, "extraction", 40, extraction)

            alignment = build_alignment_edges(
                self.db,
                course,
                run,
                min_score=float((run.config or {}).get("min_relation_score", 0.22)),
                top_k=int((run.config or {}).get("top_k", 5)),
            )
            self._set_progress(run, "alignment", 70, {**extraction, **alignment})

            findings = detect_findings(self.db, course, run)
            summary = self._summary(run.id)
            run.metrics = {
                "stage": "complete",
                "progress": 100,
                "extraction": extraction,
                "alignment": alignment,
                "findings": findings,
                "summary": summary,
            }
            run.status = "done"
            run.finished_at = datetime.now(timezone.utc)
            self.db.commit()
            return run.metrics
        except Exception as exc:
            self.db.rollback()
            run = self.db.get(AuditRun, audit_run_id)
            if run is not None:
                run.status = "failed"
                run.error = str(exc)[:4000]
                run.finished_at = datetime.now(timezone.utc)
                run.metrics = {**(run.metrics or {}), "stage": "failed"}
                self.db.commit()
            raise

    def _clear_generated_outputs(self, audit_run_id: int) -> None:
        for model in (
            CourseFinding,
            AlignmentEdge,
            AlignmentCandidate,
            AssessmentItem,
            LearningMaterial,
            LearningObjective,
        ):
            self.db.query(model).filter(model.audit_run_id == audit_run_id).delete(
                synchronize_session="fetch"
            )

    def _set_progress(
        self, run: AuditRun, stage: str, progress: int, values: dict
    ) -> None:
        run.metrics = {
            **(run.metrics or {}),
            "stage": stage,
            "progress": progress,
            **values,
        }
        self.db.commit()

    def _summary(self, audit_run_id: int) -> dict:
        objectives_total = (
            self.db.query(LearningObjective)
            .filter(LearningObjective.audit_run_id == audit_run_id)
            .count()
        )
        materials_total = (
            self.db.query(LearningMaterial)
            .filter(LearningMaterial.audit_run_id == audit_run_id)
            .count()
        )
        assessments_total = (
            self.db.query(AssessmentItem)
            .filter(AssessmentItem.audit_run_id == audit_run_id)
            .count()
        )
        teaches = {
            row[0]
            for row in self.db.query(AlignmentEdge.source_id)
            .filter(
                AlignmentEdge.audit_run_id == audit_run_id,
                AlignmentEdge.relation_type == "teaches",
            )
            .all()
        }
        assesses = {
            row[0]
            for row in self.db.query(AlignmentEdge.source_id)
            .filter(
                AlignmentEdge.audit_run_id == audit_run_id,
                AlignmentEdge.relation_type == "assesses",
            )
            .all()
        }
        findings_total = (
            self.db.query(CourseFinding)
            .filter(CourseFinding.audit_run_id == audit_run_id)
            .count()
        )
        high_severity = (
            self.db.query(CourseFinding)
            .filter(
                CourseFinding.audit_run_id == audit_run_id,
                CourseFinding.severity == "high",
            )
            .count()
        )
        return {
            "objectives_total": objectives_total,
            "materials_total": materials_total,
            "assessments_total": assessments_total,
            "objectives_with_material": len(teaches),
            "objectives_with_assessment": len(assesses),
            "objective_material_coverage": (
                round(len(teaches) / objectives_total, 4) if objectives_total else 0.0
            ),
            "objective_assessment_coverage": (
                round(len(assesses) / objectives_total, 4) if objectives_total else 0.0
            ),
            "findings_total": findings_total,
            "high_severity_findings": high_severity,
        }
