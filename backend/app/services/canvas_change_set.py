from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.models import (
    AssessmentItem,
    Course,
    CourseCopilotSuggestion,
    CourseFinding,
    CourseModule,
    Document,
)
from ..schemas.canvas_changes import CanvasChangeItemOut, CanvasChangeSetOut


def _assessment_id(finding: CourseFinding) -> int | None:
    for item in finding.evidence or []:
        if (
            item.get("object_type") == "assessment_item"
            and item.get("object_id") is not None
        ):
            try:
                return int(item["object_id"])
            except (TypeError, ValueError):
                return None
    return None


def build_canvas_change_set(db: Session, course: Course) -> CanvasChangeSetOut:
    now = datetime.now(timezone.utc)
    connected = course.source_type == "canvas" and bool(course.external_id)
    canvas_course_id = course.external_id if connected else None
    course_path_id = canvas_course_id or ":course_id"

    suggestions = (
        db.query(CourseCopilotSuggestion)
        .filter(
            CourseCopilotSuggestion.course_id == course.id,
            CourseCopilotSuggestion.status == "accepted",
        )
        .order_by(CourseCopilotSuggestion.id)
        .all()
    )
    finding_ids = {item.finding_id for item in suggestions}
    findings = (
        db.query(CourseFinding).filter(CourseFinding.id.in_(finding_ids)).all()
        if finding_ids
        else []
    )
    finding_by_id = {item.id: item for item in findings if item.course_id == course.id}
    items: list[CanvasChangeItemOut] = []
    warnings: list[str] = (
        []
        if connected
        else [
            "Course is not connected to Canvas; choose a Canvas course before applying this package"
        ]
    )

    for suggestion in suggestions:
        finding = finding_by_id.get(suggestion.finding_id)
        if finding is None:
            warnings.append(f"Suggestion {suggestion.id}: finding is unavailable")
            continue
        module = db.get(CourseModule, finding.module_id) if finding.module_id else None
        module_external_id = (
            module.external_id if module and module.course_id == course.id else None
        )
        module_title = (
            module.title if module and module.course_id == course.id else None
        )
        operation = "create_assignment"
        method = "POST"
        api_path = f"/api/v1/courses/{course_path_id}/assignments"
        target_external_id = None
        target_url = None
        ready = connected
        warning = (
            None
            if connected
            else "Canvas course ID is required before this change can be applied"
        )

        if suggestion.action_type == "create_material":
            operation = "create_page"
            api_path = f"/api/v1/courses/{course_path_id}/pages"
        elif suggestion.action_type == "revise_assessment":
            operation = "update_assignment"
            method = "PUT"
            assessment = (
                db.get(AssessmentItem, _assessment_id(finding))
                if _assessment_id(finding)
                else None
            )
            if (
                assessment is not None
                and assessment.course_id == course.id
                and assessment.document_id
            ):
                document = db.get(Document, assessment.document_id)
                if document is not None:
                    target_external_id = (
                        str(
                            (document.source_metadata or {}).get("canvas_assignment_id")
                            or ""
                        )
                        or None
                    )
                    target_url = document.source or None
            if target_external_id:
                api_path = (
                    f"/api/v1/courses/{course_path_id}/assignments/{target_external_id}"
                )
            else:
                ready = False
                warning = "Canvas assignment ID could not be mapped; manual target selection is required"
                warnings.append(f"Suggestion {suggestion.id}: {warning}")

        items.append(
            CanvasChangeItemOut(
                suggestion_id=suggestion.id,
                finding_id=finding.id,
                audit_run_id=suggestion.audit_run_id,
                action_type=suggestion.action_type,
                operation=operation,
                api_method=method,
                api_path=api_path,
                ready_for_canvas=ready,
                module_external_id=module_external_id,
                module_title=module_title,
                target_external_id=target_external_id,
                target_url=target_url,
                title=suggestion.title,
                body=suggestion.draft,
                target_bloom_level=suggestion.target_bloom_level,
                rationale=suggestion.rationale,
                citations=suggestion.citations or [],
                confidence=suggestion.confidence,
                warning=warning,
            )
        )

    return CanvasChangeSetOut(
        available=True,
        course_id=course.id,
        canvas_course_id=canvas_course_id,
        course_title=course.title,
        source_url=course.source_url,
        generated_at=now,
        accepted_suggestions=len(suggestions),
        ready_items=sum(item.ready_for_canvas for item in items),
        items=items,
        warnings=warnings,
    )


def canvas_change_set_markdown(change_set: CanvasChangeSetOut) -> str:
    lines = [
        f"# Canvas Change Set: {change_set.course_title}",
        "",
        "> READ-ONLY PREVIEW. Review every item before making changes in Canvas.",
        "",
        f"- Canvas course ID: `{change_set.canvas_course_id or 'unknown'}`",
        f"- Accepted suggestions: {change_set.accepted_suggestions}",
        f"- Ready for Canvas: {change_set.ready_items}",
    ]
    for index, item in enumerate(change_set.items, start=1):
        lines.extend(
            [
                "",
                f"## {index}. {item.title}",
                "",
                f"- Operation: `{item.api_method} {item.api_path}`",
                f"- Status: {'ready' if item.ready_for_canvas else 'manual target required'}",
                f"- Module: {item.module_title or 'not specified'}",
                f"- Target Bloom level: `{item.target_bloom_level}`",
                f"- Confidence: {item.confidence:.0%}",
            ]
        )
        if item.warning:
            lines.append(f"- Warning: {item.warning}")
        lines.extend(
            ["", item.body, "", f"**Rationale:** {item.rationale}", "", "### Sources"]
        )
        if item.citations:
            for citation in item.citations:
                suffix = f" — {citation.source_url}" if citation.source_url else ""
                lines.append(
                    f"- [{citation.source_id}] {citation.document_title}{suffix}"
                )
        else:
            lines.append("- No citations")
    if change_set.warnings:
        lines.extend(
            ["", "## Warnings", *[f"- {warning}" for warning in change_set.warnings]]
        )
    return "\n".join(lines).strip() + "\n"
