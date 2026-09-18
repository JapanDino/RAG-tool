import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    AlignmentEdge,
    AssessmentItem,
    AuditRun,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseQuestionAnswer,
    Document,
    FindingReviewEvent,
    Job,
    JobStatus,
    JobType,
    LearningMaterial,
    LearningObjective,
)
from ..schemas.course_audit import (
    AlignmentEdgeOut,
    AssessmentItemOut,
    AuditComparisonOut,
    AuditComparisonSnapshot,
    AuditReportOut,
    AuditRunCreate,
    AuditRunOut,
    AuditStartOut,
    CanvasAlignmentCalibrationOut,
    CanvasAlignmentEvaluationOut,
    CourseFindingOut,
    FindingReviewEventOut,
    FindingReviewIn,
    LearningMaterialOut,
    LearningObjectiveOut,
)
from ..services.authorization import (
    Principal,
    get_current_principal,
    require_course_route_access,
)
from ..services.canvas_alignment_calibration import calibrate_canvas_alignment
from ..services.canvas_alignment_evaluation import evaluate_canvas_alignment
from ..services.embedding_provider import current_embedding_model
from ..tasks.queue import enqueue_or_mark

router = APIRouter(
    tags=["course-audits"],
    dependencies=[Depends(require_course_route_access)],
)


def _audit_or_404(db: Session, audit_run_id: int) -> AuditRun:
    run = db.get(AuditRun, audit_run_id)
    if run is None:
        raise HTTPException(404, "audit run not found")
    return run


@router.post(
    "/courses/{course_id}/audits", response_model=AuditStartOut, status_code=202
)
def start_audit(course_id: int, payload: AuditRunCreate, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    documents = (
        db.query(Document).filter(Document.dataset_id == course.dataset_id).all()
    )
    if not documents:
        raise HTTPException(409, "course has no documents")
    pending = [document.id for document in documents if document.status != "ready"]
    if pending:
        raise HTTPException(409, f"course documents are not ready: {pending}")
    calibration_source_id = payload.config.get("calibration_source_audit_id")
    if calibration_source_id is not None:
        calibration_source = db.get(AuditRun, calibration_source_id)
        if calibration_source is None or calibration_source.course_id != course_id:
            raise HTTPException(
                422, "calibration source audit does not belong to this course"
            )
        if calibration_source.status != "done":
            raise HTTPException(409, "calibration source audit must be completed")

    run = AuditRun(
        course_id=course_id,
        status="queued",
        pipeline_version="course-audit-v1",
        extractor_version="objective-assessment-baseline-v1",
        classifier_version="bloom-hybrid-v1",
        embedding_model=current_embedding_model(),
        relation_model="lexical-module-baseline-v1",
        config=payload.config,
        metrics={"stage": "queued", "progress": 0},
    )
    db.add(run)
    db.flush()
    job = Job(
        type=JobType.audit,
        status=JobStatus.queued,
        payload={"course_id": course_id, "audit_run_id": run.id},
    )
    db.add(job)
    db.commit()
    db.refresh(run)
    db.refresh(job)
    enqueue_or_mark(db, job)
    return AuditStartOut(audit_run_id=run.id, job_id=job.id, status=run.status)


@router.get("/courses/{course_id}/audits", response_model=list[AuditRunOut])
def list_audits(course_id: int, db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "course not found")
    return (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course_id)
        .order_by(AuditRun.id.desc())
        .all()
    )


@router.get("/courses/{course_id}/quality-metrics")
def course_quality_metrics(course_id: int, db: Session = Depends(get_db)):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "course not found")
    runs = (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course_id)
        .order_by(AuditRun.id.desc())
        .all()
    )
    findings = (
        db.query(CourseFinding).filter(CourseFinding.course_id == course_id).all()
    )
    questions = (
        db.query(CourseQuestionAnswer)
        .filter(CourseQuestionAnswer.course_id == course_id)
        .all()
    )
    reviewed_questions = [
        item for item in questions if item.feedback_status != "unreviewed"
    ]
    helpful_questions = [
        item for item in reviewed_questions if item.feedback_status == "helpful"
    ]
    reviewed = [item for item in findings if item.status != "new"]
    accepted = [item for item in reviewed if item.status in {"confirmed", "resolved"}]
    durations = [
        (run.finished_at - run.created_at).total_seconds()
        for run in runs
        if run.created_at is not None and run.finished_at is not None
    ]
    return {
        "audits_total": len(runs),
        "audits_done": sum(run.status == "done" for run in runs),
        "audits_failed": sum(run.status == "failed" for run in runs),
        "audit_success_rate": (
            round(sum(run.status == "done" for run in runs) / len(runs), 4)
            if runs
            else 0.0
        ),
        "average_audit_duration_seconds": (
            round(sum(durations) / len(durations), 2) if durations else None
        ),
        "findings_total": len(findings),
        "findings_reviewed": len(reviewed),
        "finding_review_rate": (
            round(len(reviewed) / len(findings), 4) if findings else 0.0
        ),
        "finding_acceptance_rate": (
            round(len(accepted) / len(reviewed), 4) if reviewed else None
        ),
        "findings_resolved": sum(item.status == "resolved" for item in findings),
        "qa_questions_total": len(questions),
        "qa_grounded_answers": sum(not item.insufficient_context for item in questions),
        "qa_grounded_rate": (
            round(
                sum(not item.insufficient_context for item in questions)
                / len(questions),
                4,
            )
            if questions
            else None
        ),
        "qa_average_confidence": (
            round(sum(item.confidence for item in questions) / len(questions), 4)
            if questions
            else None
        ),
        "qa_reviewed_answers": len(reviewed_questions),
        "qa_helpful_answers": len(helpful_questions),
        "qa_helpful_rate": (
            round(len(helpful_questions) / len(reviewed_questions), 4)
            if reviewed_questions
            else None
        ),
        "latest_summary": (runs[0].metrics or {}).get("summary", {}) if runs else {},
    }


@router.get("/courses/{course_id}/audits/compare", response_model=AuditComparisonOut)
def compare_course_audits(
    course_id: int,
    before_id: int | None = Query(default=None, ge=1),
    after_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "course not found")
    completed = (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course_id, AuditRun.status == "done")
        .order_by(AuditRun.id.desc())
        .all()
    )
    if before_id is None and after_id is None:
        if len(completed) < 2:
            return AuditComparisonOut(available=False)
        after, before = completed[0], completed[1]
    elif before_id is not None and after_id is not None:
        before = db.get(AuditRun, before_id)
        after = db.get(AuditRun, after_id)
        if (
            before is None
            or after is None
            or before.course_id != course_id
            or after.course_id != course_id
        ):
            raise HTTPException(404, "audit run not found for this course")
        if before.status != "done" or after.status != "done":
            raise HTTPException(409, "both audit runs must be completed")
    else:
        raise HTTPException(422, "before_id and after_id must be provided together")

    before_findings = (
        db.query(CourseFinding).filter(CourseFinding.audit_run_id == before.id).all()
    )
    after_findings = (
        db.query(CourseFinding).filter(CourseFinding.audit_run_id == after.id).all()
    )

    def fingerprint(item: CourseFinding) -> str:
        return str((item.model_info or {}).get("fingerprint") or f"id:{item.id}")

    def type_counts(items: list[CourseFinding]) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in items:
            result[item.finding_type] = result.get(item.finding_type, 0) + 1
        return result

    before_fingerprints = {fingerprint(item) for item in before_findings}
    after_fingerprints = {fingerprint(item) for item in after_findings}
    before_summary = (before.metrics or {}).get("summary", {})
    after_summary = (after.metrics or {}).get("summary", {})
    tracked_metrics = (
        "objective_material_coverage",
        "objective_assessment_coverage",
        "findings_total",
        "high_severity_findings",
    )
    delta = {
        key: round(
            float(after_summary.get(key, 0)) - float(before_summary.get(key, 0)), 4
        )
        for key in tracked_metrics
    }
    return AuditComparisonOut(
        available=True,
        before=AuditComparisonSnapshot(
            audit_run_id=before.id,
            summary=before_summary,
            finding_types=type_counts(before_findings),
        ),
        after=AuditComparisonSnapshot(
            audit_run_id=after.id,
            summary=after_summary,
            finding_types=type_counts(after_findings),
        ),
        delta=delta,
        new_findings=len(after_fingerprints - before_fingerprints),
        removed_findings=len(before_fingerprints - after_fingerprints),
        persisted_findings=len(before_fingerprints & after_fingerprints),
    )


@router.get("/audits/{audit_run_id}", response_model=AuditRunOut)
def get_audit(audit_run_id: int, db: Session = Depends(get_db)):
    return _audit_or_404(db, audit_run_id)


@router.get(
    "/audits/{audit_run_id}/objectives", response_model=list[LearningObjectiveOut]
)
def list_objectives(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return (
        db.query(LearningObjective)
        .filter(LearningObjective.audit_run_id == audit_run_id)
        .order_by(LearningObjective.id)
        .all()
    )


@router.get(
    "/audits/{audit_run_id}/materials", response_model=list[LearningMaterialOut]
)
def list_materials(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return (
        db.query(LearningMaterial)
        .filter(LearningMaterial.audit_run_id == audit_run_id)
        .order_by(LearningMaterial.id)
        .all()
    )


@router.get(
    "/audits/{audit_run_id}/assessments", response_model=list[AssessmentItemOut]
)
def list_assessments(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return (
        db.query(AssessmentItem)
        .filter(AssessmentItem.audit_run_id == audit_run_id)
        .order_by(AssessmentItem.id)
        .all()
    )


@router.get("/audits/{audit_run_id}/alignment", response_model=list[AlignmentEdgeOut])
def list_alignment(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return (
        db.query(AlignmentEdge)
        .filter(AlignmentEdge.audit_run_id == audit_run_id)
        .order_by(AlignmentEdge.id)
        .all()
    )


@router.get(
    "/audits/{audit_run_id}/canvas-alignment",
    response_model=CanvasAlignmentEvaluationOut,
)
def canvas_alignment_evaluation(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return evaluate_canvas_alignment(db, audit_run_id)


@router.get(
    "/audits/{audit_run_id}/canvas-alignment/calibration",
    response_model=CanvasAlignmentCalibrationOut,
)
def canvas_alignment_calibration(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return calibrate_canvas_alignment(db, audit_run_id)


@router.get("/audits/{audit_run_id}/findings", response_model=list[CourseFindingOut])
def list_findings(audit_run_id: int, db: Session = Depends(get_db)):
    _audit_or_404(db, audit_run_id)
    return (
        db.query(CourseFinding)
        .filter(CourseFinding.audit_run_id == audit_run_id)
        .order_by(CourseFinding.id)
        .all()
    )


@router.get("/audits/{audit_run_id}/report", response_model=AuditReportOut)
def audit_report(audit_run_id: int, db: Session = Depends(get_db)):
    run = _audit_or_404(db, audit_run_id)
    findings = (
        db.query(CourseFinding)
        .filter(CourseFinding.audit_run_id == audit_run_id)
        .order_by(CourseFinding.id)
        .all()
    )
    suggestions = (
        db.query(CourseCopilotSuggestion)
        .filter(CourseCopilotSuggestion.audit_run_id == audit_run_id)
        .order_by(CourseCopilotSuggestion.id)
        .all()
    )
    return AuditReportOut(
        audit=AuditRunOut.model_validate(run),
        summary=(run.metrics or {}).get("summary", {}),
        findings=[CourseFindingOut.model_validate(item) for item in findings],
        copilot_suggestions=suggestions,
    )


@router.get("/audits/{audit_run_id}/report/download")
def download_audit_report(audit_run_id: int, db: Session = Depends(get_db)):
    report = audit_report(audit_run_id, db)
    content = json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="course-audit-{audit_run_id}.json"'
        },
    )


@router.patch("/findings/{finding_id}", response_model=CourseFindingOut)
def review_finding(
    finding_id: int,
    payload: FindingReviewIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    finding = db.get(CourseFinding, finding_id)
    if finding is None:
        raise HTTPException(404, "finding not found")
    allowed = {
        "new": {"confirmed", "rejected", "ignored"},
        "confirmed": {"resolved", "rejected", "ignored"},
        "rejected": {"confirmed", "ignored"},
        "resolved": {"confirmed", "ignored"},
        "ignored": {"confirmed", "rejected"},
    }
    if payload.status not in allowed.get(finding.status, set()):
        raise HTTPException(
            409, f"invalid finding transition: {finding.status} -> {payload.status}"
        )
    reviewed_by = principal.email if not principal.bypass else payload.reviewed_by
    if not reviewed_by:
        raise HTTPException(422, "reviewed_by is required in compatibility mode")
    previous_status = finding.status
    finding.status = payload.status
    finding.reviewed_by = reviewed_by
    finding.reviewed_at = datetime.now(timezone.utc)
    db.add(
        FindingReviewEvent(
            finding_id=finding.id,
            course_id=finding.course_id,
            audit_run_id=finding.audit_run_id,
            from_status=previous_status,
            to_status=payload.status,
            reviewed_by=reviewed_by,
        )
    )
    db.commit()
    db.refresh(finding)
    return finding


@router.get(
    "/findings/{finding_id}/history", response_model=list[FindingReviewEventOut]
)
def finding_history(finding_id: int, db: Session = Depends(get_db)):
    if db.get(CourseFinding, finding_id) is None:
        raise HTTPException(404, "finding not found")
    return (
        db.query(FindingReviewEvent)
        .filter(FindingReviewEvent.finding_id == finding_id)
        .order_by(FindingReviewEvent.id)
        .all()
    )
