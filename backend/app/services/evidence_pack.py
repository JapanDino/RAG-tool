from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.models import (
    AuditRun,
    Course,
    CourseCopilotSuggestion,
    CourseEvaluationProtocol,
    CourseFinding,
    CourseModule,
    CourseQuestionAnswer,
    Document,
)
from ..schemas.copilot import CopilotSuggestionOut, CourseAnswerOut
from ..schemas.course_audit import (
    AuditRunOut,
    CourseDocumentOut,
    CourseFindingOut,
    CourseModuleOut,
    CourseOut,
)
from ..schemas.evaluation_protocol import CourseEvaluationProtocolOut
from ..schemas.evidence_pack import EvidenceArtifactOut, EvidencePackPreviewOut
from .canvas_change_set import build_canvas_change_set, canvas_change_set_markdown
from .evaluation_protocol import evaluation_protocol_markdown
from .ml_feedback_export import build_ml_feedback_rows


def _latest_done_audit(db: Session, course_id: int) -> AuditRun | None:
    return (
        db.query(AuditRun)
        .filter(AuditRun.course_id == course_id, AuditRun.status == "done")
        .order_by(AuditRun.id.desc())
        .first()
    )


def _latest_protocol(db: Session, course_id: int) -> CourseEvaluationProtocol | None:
    return (
        db.query(CourseEvaluationProtocol)
        .filter(CourseEvaluationProtocol.course_id == course_id)
        .order_by(CourseEvaluationProtocol.id.desc())
        .first()
    )


def _protocol_check_passed(
    protocol: CourseEvaluationProtocol | None, check_id: str
) -> bool:
    if protocol is None:
        return False
    return any(
        item.get("check_id") == check_id and item.get("passed") is True
        for item in protocol.checks or []
    )


def build_evidence_pack_preview(db: Session, course: Course) -> EvidencePackPreviewOut:
    audit = _latest_done_audit(db, course.id)
    protocol = _latest_protocol(db, course.id)
    suggestions = (
        db.query(CourseCopilotSuggestion)
        .filter(CourseCopilotSuggestion.course_id == course.id)
        .all()
    )
    questions = (
        db.query(CourseQuestionAnswer)
        .filter(CourseQuestionAnswer.course_id == course.id)
        .all()
    )
    reviewed_findings = (
        db.query(CourseFinding)
        .filter(CourseFinding.course_id == course.id, CourseFinding.status != "new")
        .count()
    )
    grounded_artifacts = sum(bool(item.citations) for item in suggestions) + sum(
        bool(item.citations) for item in questions
    )
    reviewed_ai = (
        sum(item.status in {"accepted", "rejected"} for item in suggestions)
        + sum(item.feedback_status != "unreviewed" for item in questions)
        + reviewed_findings
    )
    feedback_rows, feedback_warnings = build_ml_feedback_rows(db, course)
    accepted = sum(item.status == "accepted" for item in suggestions)
    citation_integrity = _protocol_check_passed(protocol, "citation_integrity")

    score = 0
    missing: list[str] = []
    warnings = list(feedback_warnings)
    if audit:
        score += 25
    else:
        missing.append("Нет завершённого аудита курса")
    if protocol and protocol.status == "passed":
        score += 25
    else:
        missing.append("Нет успешно пройденного Evaluation Protocol")
    if grounded_artifacts:
        score += 15
    else:
        missing.append("Нет сохранённых RAG-ответов с проверяемыми цитатами")
    if reviewed_ai:
        score += 10
    else:
        missing.append("Нет преподавательской оценки findings, Copilot или Q&A")
    if course.source_type == "canvas" and course.external_id:
        score += 10
    else:
        missing.append(
            "Курс не подключён к Canvas; пакет останется переносимым preview"
        )
    if citation_integrity:
        score += 15
    else:
        missing.append("Citation integrity ещё не подтверждена успешным протоколом")

    if (
        protocol
        and protocol.status == "passed"
        and grounded_artifacts
        and not citation_integrity
    ):
        warnings.append("После появления новых RAG-цитат повторите Evaluation Protocol")
    artifacts = [
        EvidenceArtifactOut(
            name="course-summary.json",
            included=True,
            description="Курс, модули и документы без исходного содержимого",
        ),
        EvidenceArtifactOut(
            name="audit-report.json",
            included=audit is not None,
            description="Последний завершённый аудит и findings",
        ),
        EvidenceArtifactOut(
            name="evaluation-protocol.md/json",
            included=protocol is not None,
            description="Последняя программа и результаты испытаний",
        ),
        EvidenceArtifactOut(
            name="canvas-change-set.md/json",
            included=accepted > 0,
            description="Принятые Copilot-исправления",
        ),
        EvidenceArtifactOut(
            name="qa-history.json",
            included=bool(questions),
            description="Последние вопросы с grounded citations и feedback",
        ),
        EvidenceArtifactOut(
            name="ml-feedback.jsonl",
            included=bool(feedback_rows),
            description="Обезличенные teacher labels",
        ),
        EvidenceArtifactOut(
            name="manifest.json",
            included=True,
            description="SHA-256 и размер каждого файла",
        ),
    ]
    return EvidencePackPreviewOut(
        course_id=course.id,
        completeness_score=score,
        ready_for_submission=bool(
            audit and protocol and protocol.status == "passed" and score >= 75
        ),
        latest_audit_id=audit.id if audit else None,
        latest_protocol_id=protocol.id if protocol else None,
        artifacts=artifacts,
        missing=missing,
        warnings=sorted(set(warnings)),
    )


def _privacy_safe(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = str(key).lower()
            if (
                normalized
                in {
                    "reviewed_by",
                    "feedback_comment",
                    "access_token",
                    "api_key",
                    "password",
                    "secret",
                }
                or normalized.endswith("_token")
                or normalized.endswith("_secret")
            ):
                continue
            result[key] = _privacy_safe(item)
        return result
    if isinstance(value, list):
        return [_privacy_safe(item) for item in value]
    return value


def _json_bytes(value) -> bytes:
    return (
        json.dumps(_privacy_safe(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _zip_write(archive: zipfile.ZipFile, name: str, content: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, content)


def build_evidence_pack(
    db: Session, course: Course
) -> tuple[bytes, EvidencePackPreviewOut]:
    preview = build_evidence_pack_preview(db, course)
    audit = (
        db.get(AuditRun, preview.latest_audit_id) if preview.latest_audit_id else None
    )
    protocol = (
        db.get(CourseEvaluationProtocol, preview.latest_protocol_id)
        if preview.latest_protocol_id
        else None
    )
    modules = (
        db.query(CourseModule)
        .filter(CourseModule.course_id == course.id)
        .order_by(CourseModule.position, CourseModule.id)
        .all()
    )
    documents = (
        db.query(Document)
        .filter(Document.dataset_id == course.dataset_id)
        .order_by(Document.id)
        .all()
    )
    questions = (
        db.query(CourseQuestionAnswer)
        .filter(CourseQuestionAnswer.course_id == course.id)
        .order_by(CourseQuestionAnswer.id.desc())
        .limit(50)
        .all()
    )
    files: dict[str, bytes] = {
        "course-summary.json": _json_bytes(
            {
                "course": CourseOut.model_validate(course).model_dump(mode="json"),
                "modules": [
                    CourseModuleOut.model_validate(item).model_dump(mode="json")
                    for item in modules
                ],
                "documents": [
                    CourseDocumentOut.model_validate(item).model_dump(mode="json")
                    for item in documents
                ],
                "evidence_readiness": preview.model_dump(mode="json"),
            }
        ),
    }
    if audit is not None:
        findings = (
            db.query(CourseFinding)
            .filter(CourseFinding.audit_run_id == audit.id)
            .order_by(CourseFinding.id)
            .all()
        )
        suggestions = (
            db.query(CourseCopilotSuggestion)
            .filter(CourseCopilotSuggestion.audit_run_id == audit.id)
            .order_by(CourseCopilotSuggestion.id)
            .all()
        )
        files["audit-report.json"] = _json_bytes(
            {
                "audit": AuditRunOut.model_validate(audit).model_dump(mode="json"),
                "findings": [
                    CourseFindingOut.model_validate(item).model_dump(mode="json")
                    for item in findings
                ],
                "copilot_suggestions": [
                    CopilotSuggestionOut.model_validate(item).model_dump(mode="json")
                    for item in suggestions
                ],
            }
        )
    if protocol is not None:
        protocol_payload = CourseEvaluationProtocolOut.model_validate(protocol)
        files["evaluation-protocol.json"] = _json_bytes(
            protocol_payload.model_dump(mode="json")
        )
        files["evaluation-protocol.md"] = evaluation_protocol_markdown(
            protocol, course
        ).encode("utf-8")
    change_set = build_canvas_change_set(db, course)
    if change_set.accepted_suggestions:
        files["canvas-change-set.json"] = _json_bytes(
            change_set.model_dump(mode="json")
        )
        files["canvas-change-set.md"] = canvas_change_set_markdown(change_set).encode(
            "utf-8"
        )
    if questions:
        files["qa-history.json"] = _json_bytes(
            [
                CourseAnswerOut.model_validate(item).model_dump(mode="json")
                for item in questions
            ]
        )
    feedback_rows, feedback_warnings = build_ml_feedback_rows(db, course)
    max_feedback_examples = int(
        os.getenv("EVIDENCE_PACK_MAX_FEEDBACK_EXAMPLES", "2000")
    )
    if feedback_rows:
        selected_rows = feedback_rows[:max_feedback_examples]
        files["ml-feedback.jsonl"] = (
            "\n".join(
                json.dumps(item, ensure_ascii=False, separators=(",", ":"))
                for item in selected_rows
            )
            + "\n"
        ).encode("utf-8")
        if len(feedback_rows) > len(selected_rows):
            preview.warnings.append(
                f"ML feedback truncated to {max_feedback_examples} examples"
            )
    preview.warnings = sorted(set([*preview.warnings, *feedback_warnings]))

    max_bytes = int(os.getenv("EVIDENCE_PACK_MAX_BYTES", str(25 * 1024 * 1024)))
    unpacked_size = sum(len(content) for content in files.values())
    if unpacked_size > max_bytes:
        raise ValueError(f"evidence pack exceeds {max_bytes} uncompressed bytes")
    manifest = {
        "schema_version": "course-evidence-pack-v1",
        "privacy_mode": "reviewer-and-secret-metadata-removed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "course_id": course.id,
        "completeness": preview.model_dump(mode="json"),
        "files": [
            {
                "name": name,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
            for name, content in sorted(files.items())
        ],
    }
    files["manifest.json"] = _json_bytes(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for name, content in sorted(files.items()):
            _zip_write(archive, name, content)
    return buffer.getvalue(), preview
