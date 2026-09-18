from __future__ import annotations

import hashlib
import hmac
import json
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from ..models.models import (
    AgentRun,
    AssessmentItem,
    Competency,
    CourseContribution,
    LearningObjective,
    Program,
    ProgramChangeEvent,
    ProgramCourse,
    ProgramReviewNote,
)
from ..schemas.agent_api import (
    AgentProgramEvidenceAnchorOut,
    AgentProgramEvidenceCandidateOut,
    AgentProgramEvidenceRouteOut,
    AgentProgramOptionOut,
    AgentProgramPriorityOut,
    AgentProgramReviewDraftOut,
    AgentProgramRouteBriefOut,
    AgentProgramRouteCountsOut,
    AgentProgramSavedNoteOut,
)
from ..schemas.program_intelligence import (
    PrerequisiteEvidenceOut,
    PrerequisiteRelationOut,
    ProgramAuditPreviewOut,
    ProgramReviewNoteOut,
    ProgramReviewNoteSaveIn,
)
from .agent_policy import TOOL_REGISTRY
from .agent_run import (
    AgentTrustedContext,
    agent_reference_secret,
    resolve_agent_context,
)
from .authorization import Principal
from .learner_agent import _configure_statement_timeout, _run_validated_tool
from .program_intelligence import get_program_audit_preview, get_program_map

EXECUTABLE_PROGRAM_WORKFLOWS = frozenset(
    {
        "program.inspect_map.v1",
        "program.inspect_gap.v1",
        "program.inspect_prerequisite.v1",
        "program.draft_review_note.v1",
    }
)
PROGRAM_OPTION_LIMIT = 100


class ProgramRouteToolIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_ref: str = Field(min_length=44, max_length=160)


class ProgramRouteToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    counts: AgentProgramRouteCountsOut
    priorities: list[AgentProgramPriorityOut] = Field(max_length=3)
    analysis_truncated: bool
    findings_truncated: bool
    limitations: list[str] = Field(max_length=4)


class ProgramEvidenceToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route_kind: Literal["gap", "prerequisite"]
    state: Literal["candidate", "clear", "empty", "partial"]
    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    headline: str = Field(min_length=1, max_length=300)
    candidate: AgentProgramEvidenceCandidateOut | None
    analysis_truncated: bool
    action_target: Literal["audit", "prerequisites"]
    action_label: str = Field(min_length=1, max_length=120)
    limitations: list[str] = Field(min_length=1, max_length=4)


class ProgramReviewToolOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: Literal["draft", "clear", "partial"]
    program_title: str = Field(min_length=1, max_length=500)
    program_version: int = Field(ge=1)
    headline: str = Field(min_length=1, max_length=300)
    draft_ref: str | None = Field(default=None, min_length=40, max_length=200)
    candidate: AgentProgramEvidenceCandidateOut | None
    content: str | None = Field(default=None, min_length=40, max_length=2000)
    source_fingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{16}$")
    current_note: AgentProgramSavedNoteOut | None
    limitations: list[str] = Field(min_length=2, max_length=4)
    program_changed: Literal[False]
    canvas_changed: Literal[False]


class ProgramReviewNoteConflict(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _deny() -> None:
    raise HTTPException(status_code=404, detail="resource not found")


def _exact_context(row: AgentRun, context: AgentTrustedContext) -> bool:
    return (
        row.organization_id == context.organization_id
        and row.course_id is None
        and context.course_id is None
        and row.user_id == context.user_id
        and row.role == context.role
        and row.product_session_id is None
        and context.product_session_id is None
    )


def _program_signature(
    context: AgentTrustedContext, program_id: int, version: int
) -> str:
    raw = ":".join(
        (
            "program-ref:v1",
            str(context.organization_id),
            str(context.user_id),
            context.role,
            str(program_id),
            str(version),
        )
    )
    return hmac.new(
        agent_reference_secret(), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]


def program_ref(context: AgentTrustedContext, program_id: int, version: int) -> str:
    return f"program_{program_id}_{version}_{_program_signature(context, program_id, version)}"


def list_program_options(
    db: Session,
    *,
    context: AgentTrustedContext,
    selected_program_id: int | None = None,
) -> tuple[list[AgentProgramOptionOut], bool]:
    if context.role not in {"methodologist", "program_designer", "administrator"}:
        _deny()
    query = db.query(Program).filter(
        Program.organization_id == context.organization_id,
        Program.is_active.is_(True),
    )
    rows = (
        query.order_by(Program.code, Program.title, Program.id)
        .limit(PROGRAM_OPTION_LIMIT + 1)
        .all()
    )
    truncated = len(rows) > PROGRAM_OPTION_LIMIT
    rows = rows[:PROGRAM_OPTION_LIMIT]
    if selected_program_id is not None and all(
        row.id != selected_program_id for row in rows
    ):
        selected = query.filter(Program.id == selected_program_id).first()
        if selected is None:
            _deny()
        rows = [*rows[: PROGRAM_OPTION_LIMIT - 1], selected]
        truncated = True
    return (
        [
            AgentProgramOptionOut(
                program_ref=program_ref(context, item.id, item.version),
                program_id=item.id,
                code=item.code,
                title=item.title,
                version=item.version,
            )
            for item in rows
        ],
        truncated,
    )


def resolve_program_ref(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> Program:
    if context.role not in {"methodologist", "program_designer", "administrator"}:
        _deny()
    parts = signed_ref.split("_")
    if len(parts) != 4 or parts[0] != "program":
        _deny()
    try:
        program_id = int(parts[1])
        version = int(parts[2])
    except ValueError:
        _deny()
    if program_id <= 0 or version <= 0:
        _deny()
    expected = _program_signature(context, program_id, version)
    if not hmac.compare_digest(expected, parts[3]):
        _deny()
    program = db.get(Program, program_id)
    if (
        program is None
        or not program.is_active
        or program.organization_id != context.organization_id
        or program.version != version
    ):
        _deny()
    return program


def _program_counts(db: Session, program: Program) -> AgentProgramRouteCountsOut:
    courses = (
        db.query(func.count(ProgramCourse.id))
        .filter(ProgramCourse.program_id == program.id)
        .scalar()
        or 0
    )
    competencies = (
        db.query(func.count(Competency.id))
        .filter(Competency.program_id == program.id)
        .scalar()
        or 0
    )
    mapped = (
        db.query(func.count(func.distinct(CourseContribution.competency_id)))
        .filter(CourseContribution.program_id == program.id)
        .scalar()
        or 0
    )
    assessed = (
        db.query(func.count(func.distinct(CourseContribution.competency_id)))
        .filter(
            CourseContribution.program_id == program.id,
            CourseContribution.stage == "assessed",
        )
        .scalar()
        or 0
    )
    live_evidence = or_(
        CourseContribution.evidence_type == "manual_note",
        and_(
            CourseContribution.evidence_type == "learning_objective",
            LearningObjective.id.is_not(None),
            LearningObjective.course_id == CourseContribution.course_id,
        ),
        and_(
            CourseContribution.evidence_type == "assessment_item",
            AssessmentItem.id.is_not(None),
            AssessmentItem.course_id == CourseContribution.course_id,
        ),
    )
    missing = (
        db.query(func.coalesce(func.sum(case((live_evidence, 0), else_=1)), 0))
        .select_from(CourseContribution)
        .outerjoin(
            LearningObjective,
            and_(
                CourseContribution.evidence_type == "learning_objective",
                LearningObjective.id == CourseContribution.evidence_id,
            ),
        )
        .outerjoin(
            AssessmentItem,
            and_(
                CourseContribution.evidence_type == "assessment_item",
                AssessmentItem.id == CourseContribution.evidence_id,
            ),
        )
        .filter(CourseContribution.program_id == program.id)
        .scalar()
        or 0
    )
    return AgentProgramRouteCountsOut(
        courses=int(courses),
        competencies=int(competencies),
        assessed_competencies=int(assessed),
        learning_only_competencies=max(0, int(mapped) - int(assessed)),
        unmapped_competencies=max(0, int(competencies) - int(mapped)),
        missing_evidence_cells=int(missing),
    )


def build_program_route_brief(
    *,
    program: Program,
    counts: AgentProgramRouteCountsOut,
    audit: ProgramAuditPreviewOut,
) -> AgentProgramRouteBriefOut:
    priorities = [
        AgentProgramPriorityOut(
            kind=finding.kind,
            attention=finding.attention,
            title=f"{finding.title}: {finding.competency_title}",
            detail=finding.detail,
            confidence=finding.confidence,
            confidence_label=finding.confidence_label,
            review_status=finding.review_status,
            evidence_status=finding.evidence_status,
            evidence_count=min(8, len(finding.evidence)),
            evidence_truncated=finding.evidence_truncated,
        )
        for finding in audit.findings[:3]
    ]
    if audit.analysis_truncated or audit.findings_truncated:
        headline = (
            "Карта проверена не полностью — начните с ручной проверки доказательств"
        )
    elif not counts.competencies:
        headline = "Сначала добавьте первую компетенцию и свяжите её с курсом"
    elif priorities:
        headline = "Начните с первого разрыва в сохранённом маршруте"
    else:
        headline = "Явных разрывов базовой карты сейчас не видно"
    limitations = [
        "Сводка относится только к текущей сохранённой версии карты программы.",
        "Это маршрут методической проверки, а не оценка качества программы или работы людей.",
        "Помощник не использует данные учеников, оценки, переписки и индивидуальные рейтинги.",
    ]
    if audit.analysis_truncated or audit.findings_truncated:
        limitations.append(
            "Карта превысила безопасный предел анализа; сводка неполная и требует ручной проверки."
        )
    return AgentProgramRouteBriefOut(
        mode="program_route_brief",
        program_title=program.title,
        program_version=program.version,
        headline=headline,
        counts=counts,
        priorities=priorities,
        analysis_truncated=audit.analysis_truncated,
        findings_truncated=audit.findings_truncated,
        limitations=limitations,
        read_only=True,
    )


def current_program_route_brief(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> AgentProgramRouteBriefOut:
    program = resolve_program_ref(db, context=context, signed_ref=signed_ref)
    audit = get_program_audit_preview(
        db,
        program_id=program.id,
        actor_user_id=context.user_id,
    )
    return build_program_route_brief(
        program=program,
        counts=_program_counts(db, program),
        audit=audit,
    )


def _evidence_review_label(value: str) -> str:
    return {
        "confirmed": "Источник подтверждён",
        "accepted": "Источник подтверждён",
        "unreviewed": "Источник ещё не проверен",
        "human_declared": "Основание заявлено автором карты",
        "missing": "Источник недоступен",
    }.get(value, "Статус источника требует проверки")


def _gap_evidence_anchor(item) -> AgentProgramEvidenceAnchorOut:
    stage_label = {
        "introduced": "Вводится",
        "developed": "Развивается",
        "assessed": "Проверяется",
    }[item.stage]
    return AgentProgramEvidenceAnchorOut(
        title=f"{item.course_position}. {item.course_title}"[:500],
        context=f"{stage_label} · {item.evidence_label}"[:500],
        excerpt=item.evidence_excerpt[:500],
        evidence_state=item.evidence_state,
        review_label=_evidence_review_label(item.evidence_review_status),
    )


def build_program_gap_route(
    *,
    program: Program,
    audit: ProgramAuditPreviewOut,
) -> AgentProgramEvidenceRouteOut:
    allowed_kinds = {
        "coverage_gap",
        "assessment_gap",
        "evidence_gap",
        "duplication_check",
    }
    finding = next(
        (item for item in audit.findings if item.kind in allowed_kinds),
        None,
    )
    truncated = audit.analysis_truncated or audit.findings_truncated
    candidate = None
    if finding is not None:
        candidate = AgentProgramEvidenceCandidateOut(
            focus_key=finding.key,
            candidate_type=finding.kind,
            subject=f"{finding.competency_code} · {finding.competency_title}",
            title=finding.title,
            detail=finding.detail,
            declared_rationale=None,
            confidence_label=finding.confidence_label,
            review_label="Автоматический сигнал · ещё не проверен",
            evidence_status=finding.evidence_status,
            evidence=[_gap_evidence_anchor(item) for item in finding.evidence[:4]],
            evidence_truncated=(
                finding.evidence_truncated or len(finding.evidence) > 4
            ),
        )
        headline = "Начните с первого доказательного пробела"
        state = "candidate"
    elif audit.analyzed_competencies == 0:
        headline = "Карта пока не содержит компетенций для этой проверки"
        state = "empty"
    elif truncated:
        headline = "Проверена только часть карты — нужен ручной просмотр"
        state = "partial"
    else:
        headline = "Явного пробела по этим правилам сейчас не найдено"
        state = "clear"
    limitations = [
        "Маршрут читает только текущую сохранённую карту и её доступные основания.",
        "Отсутствие сигнала не доказывает качество или полноту образовательной программы.",
        "Повтор этапа может быть намеренной спиралью обучения и требует человеческой сверки.",
    ]
    if truncated:
        limitations.append(
            "Карта превысила безопасный предел анализа; результат неполный."
        )
    return AgentProgramEvidenceRouteOut(
        mode="program_evidence_route",
        route_kind="gap",
        state=state,
        program_title=program.title,
        program_version=program.version,
        headline=headline,
        candidate=candidate,
        analysis_truncated=truncated,
        action_target="audit",
        action_label="Открыть доказательства пробела",
        limitations=limitations,
        read_only=True,
    )


def _prerequisite_evidence_anchor(
    item: PrerequisiteEvidenceOut,
) -> AgentProgramEvidenceAnchorOut:
    stage_label = {
        "introduced": "Вводится",
        "developed": "Развивается",
        "assessed": "Проверяется",
    }[item.stage]
    return AgentProgramEvidenceAnchorOut(
        title=f"{item.course_position}. {item.course_title}"[:500],
        context=f"{stage_label} · {item.evidence_label}"[:500],
        excerpt=item.evidence_excerpt[:500],
        evidence_state=item.evidence_state,
        review_label=_evidence_review_label(item.evidence_review_status),
    )


def build_program_prerequisite_route(
    *,
    program: Program,
    relations: list[PrerequisiteRelationOut],
    relations_truncated: bool,
) -> AgentProgramEvidenceRouteOut:
    state_order = {"needs_evidence": 0, "order_check": 1, "declared_order": 2}
    relation = min(
        enumerate(relations),
        key=lambda row: (state_order[row[1].structural_state], row[0]),
        default=(0, None),
    )[1]
    candidate = None
    if relation is None:
        headline = "Явных линий предпосылок в карте пока нет"
        state = "empty"
    else:
        evidence_items = [
            item
            for item in (relation.prerequisite_assessment, relation.target_start)
            if item is not None
        ]
        missing = len(evidence_items) < 2 or any(
            item.evidence_state == "missing" for item in evidence_items
        )
        review_labels = {
            "needs_evidence": "Основания неполны · нужна ручная проверка",
            "order_check": "Порядок требует методической сверки",
            "declared_order": "Явная связь · не вывод о готовности ученика",
        }
        candidate = AgentProgramEvidenceCandidateOut(
            focus_key=f"prerequisite:{relation.id}",
            candidate_type=relation.structural_state,
            subject=(
                f"{relation.prerequisite_competency_code} → "
                f"{relation.target_competency_code}"
            ),
            title=(
                f"{relation.prerequisite_competency_title} → "
                f"{relation.target_competency_title}"
            )[:500],
            detail=relation.structural_state_label,
            declared_rationale=relation.rationale[:1000],
            confidence_label=relation.confidence_label,
            review_label=review_labels[relation.structural_state],
            evidence_status=(
                "missing" if missing else "declared" if evidence_items else "none"
            ),
            evidence=[
                _prerequisite_evidence_anchor(item) for item in evidence_items[:2]
            ],
            evidence_truncated=False,
        )
        headlines = {
            "needs_evidence": "Сначала восстановите основания объявленной связи",
            "order_check": "Сначала сверьте порядок объявленной связи",
            "declared_order": "Откройте основания первой объявленной связи",
        }
        headline = headlines[relation.structural_state]
        state = "candidate"
    limitations = [
        "Показаны только явно сохранённые автором карты отношения предпосылки.",
        "Структурный порядок не подтверждает готовность, прогресс или результат ученика.",
        "Помощник не создаёт недостающие связи и не изменяет карту программы.",
    ]
    if relations_truncated:
        limitations.append(
            "Список линий превысил безопасный предел; показанный маршрут неполный."
        )
    return AgentProgramEvidenceRouteOut(
        mode="program_evidence_route",
        route_kind="prerequisite",
        state=state,
        program_title=program.title,
        program_version=program.version,
        headline=headline,
        candidate=candidate,
        analysis_truncated=relations_truncated,
        action_target="prerequisites",
        action_label="Открыть линии предпосылок",
        limitations=limitations,
        read_only=True,
    )


def current_program_evidence_route(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
    workflow: Literal["program.inspect_gap.v1", "program.inspect_prerequisite.v1"],
) -> AgentProgramEvidenceRouteOut:
    route, _ = current_program_evidence_material(
        db,
        context=context,
        signed_ref=signed_ref,
        workflow=workflow,
    )
    return route


def _program_gap_material(
    db: Session,
    *,
    context: AgentTrustedContext,
    program: Program,
) -> tuple[AgentProgramEvidenceRouteOut, str]:
    audit = get_program_audit_preview(
        db,
        program_id=program.id,
        actor_user_id=context.user_id,
    )
    route = build_program_gap_route(program=program, audit=audit)
    contribution_ids = {
        evidence.contribution_id
        for finding in audit.findings
        for evidence in finding.evidence
    }
    source = {
        "kind": "gap",
        "program": {
            "id": program.id,
            "version": program.version,
            "title": program.title,
            "updated_at": program.updated_at,
        },
        "audit": audit.model_dump(mode="json"),
        "raw_evidence": _raw_evidence_manifest(
            db,
            program_id=program.id,
            contribution_ids=contribution_ids,
        ),
        "route": route.model_dump(mode="json"),
    }
    return route, _source_digest(source)


def current_program_evidence_material(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
    workflow: Literal["program.inspect_gap.v1", "program.inspect_prerequisite.v1"],
) -> tuple[AgentProgramEvidenceRouteOut, str]:
    program = resolve_program_ref(db, context=context, signed_ref=signed_ref)
    if workflow == "program.inspect_gap.v1":
        return _program_gap_material(db, context=context, program=program)
    program_map = get_program_map(
        db,
        program_id=program.id,
        actor_user_id=context.user_id,
    )
    route = build_program_prerequisite_route(
        program=program,
        relations=program_map.prerequisites,
        relations_truncated=program_map.prerequisites_truncated,
    )
    contribution_ids = {
        evidence.contribution_id
        for relation in program_map.prerequisites
        for evidence in (relation.prerequisite_assessment, relation.target_start)
        if evidence is not None
    }
    source = {
        "kind": "prerequisite",
        "program": {
            "id": program.id,
            "version": program.version,
            "title": program.title,
            "updated_at": program.updated_at,
        },
        "relations_truncated": program_map.prerequisites_truncated,
        "relations": [
            relation.model_dump(mode="json") for relation in program_map.prerequisites
        ],
        "raw_evidence": _raw_evidence_manifest(
            db,
            program_id=program.id,
            contribution_ids=contribution_ids,
        ),
        "route": route.model_dump(mode="json"),
    }
    return route, _source_digest(source)


def _program_review_draft_content(
    candidate: AgentProgramEvidenceCandidateOut,
) -> str:
    subject = candidate.subject[:300].rstrip(" .")
    title = candidate.title[:300].rstrip(" .")
    detail = candidate.detail[:600].rstrip()
    return (
        f"Наблюдение для решения: {subject}. {title}. "
        f"Текущее основание: {detail} "
        "Перед изменением карты сверьте перечисленные источники и зафиксируйте "
        "следующий методический шаг либо причину, по которой действие не требуется."
    )[:2000]


def _program_review_draft_ref(
    *,
    context: AgentTrustedContext,
    program: Program,
    focus_key: str,
    source_digest: str,
) -> str:
    focus_digest = hashlib.sha256(focus_key.encode("utf-8")).hexdigest()[:16]
    raw = ":".join(
        (
            "program-review-draft:v1",
            str(context.organization_id),
            str(context.user_id),
            context.role,
            str(program.id),
            str(program.version),
            focus_key,
            source_digest,
        )
    )
    signature = hmac.new(
        agent_reference_secret(), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()[:32]
    return (
        f"review_{program.id}_{program.version}_{focus_digest}_"
        f"{source_digest[:16]}_{signature}"
    )


def _source_fingerprint(source_digest: str) -> str:
    return f"sha256:{source_digest[:16]}"


def _saved_note_for_agent(note: ProgramReviewNote) -> AgentProgramSavedNoteOut:
    return AgentProgramSavedNoteOut(
        note_ref=f"program_review_note_{note.id}",
        decision=note.decision,
        content=note.content,
        version=note.version,
        source_fingerprint=_source_fingerprint(note.source_digest),
    )


def build_program_review_draft(
    db: Session,
    *,
    context: AgentTrustedContext,
    program: Program,
    route: AgentProgramEvidenceRouteOut,
    source_digest: str,
) -> AgentProgramReviewDraftOut:
    candidate = route.candidate
    current_note = (
        db.query(ProgramReviewNote)
        .filter(
            ProgramReviewNote.organization_id == context.organization_id,
            ProgramReviewNote.program_id == program.id,
            ProgramReviewNote.finding_key == candidate.focus_key,
            ProgramReviewNote.source_digest == source_digest,
        )
        .one_or_none()
        if candidate is not None
        else None
    )
    limitations = [
        "Черновик собран по текущей сохранённой карте и не является методическим решением.",
        "Сохранение заметки не изменяет программу, курсы или Canvas.",
        "Помощник не использует данные учеников, оценки, переписки или индивидуальные рейтинги.",
    ]
    if route.analysis_truncated:
        return AgentProgramReviewDraftOut(
            mode="program_review_draft",
            state="partial",
            program_title=program.title,
            program_version=program.version,
            headline="Карта проверена не полностью — заметку нельзя привязать надёжно",
            draft_ref=None,
            candidate=candidate,
            content=None,
            source_fingerprint=_source_fingerprint(source_digest),
            current_note=(
                _saved_note_for_agent(current_note)
                if current_note is not None
                else None
            ),
            limitations=[
                *limitations,
                "Сначала откройте полную карту и восстановите недостающие основания.",
            ],
            program_changed=False,
            canvas_changed=False,
        )
    if candidate is None:
        return AgentProgramReviewDraftOut(
            mode="program_review_draft",
            state="clear",
            program_title=program.title,
            program_version=program.version,
            headline="Текущего доказательного кандидата для заметки нет",
            draft_ref=None,
            candidate=None,
            content=None,
            source_fingerprint=_source_fingerprint(source_digest),
            current_note=None,
            limitations=limitations,
            program_changed=False,
            canvas_changed=False,
        )
    content = _program_review_draft_content(candidate)
    return AgentProgramReviewDraftOut(
        mode="program_review_draft",
        state="draft",
        program_title=program.title,
        program_version=program.version,
        headline=(
            "Сохранённое решение можно пересмотреть по текущим основаниям"
            if current_note is not None
            else "Черновик готов к человеческому решению"
        ),
        draft_ref=_program_review_draft_ref(
            context=context,
            program=program,
            focus_key=candidate.focus_key,
            source_digest=source_digest,
        ),
        candidate=candidate,
        content=content,
        source_fingerprint=_source_fingerprint(source_digest),
        current_note=(
            _saved_note_for_agent(current_note) if current_note is not None else None
        ),
        limitations=limitations,
        program_changed=False,
        canvas_changed=False,
    )


def current_program_review_draft(
    db: Session,
    *,
    context: AgentTrustedContext,
    signed_ref: str,
) -> tuple[AgentProgramReviewDraftOut, str]:
    if context.role not in {"program_designer", "administrator"}:
        _deny()
    program = resolve_program_ref(db, context=context, signed_ref=signed_ref)
    route, source_digest = _program_gap_material(
        db,
        context=context,
        program=program,
    )
    result = build_program_review_draft(
        db,
        context=context,
        program=program,
        route=route,
        source_digest=source_digest,
    )
    return result, _source_digest(
        {
            "evidence_source_digest": source_digest,
            "result": result.model_dump(mode="json"),
        }
    )


def _program_review_note_out(note: ProgramReviewNote) -> ProgramReviewNoteOut:
    return ProgramReviewNoteOut(
        note_ref=f"program_review_note_{note.id}",
        program_id=note.program_id,
        finding_key=note.finding_key,
        finding_kind=note.finding_kind,
        decision=note.decision,
        content=note.content,
        version=note.version,
        source_fingerprint=_source_fingerprint(note.source_digest),
        created_at=note.created_at,
        updated_at=note.updated_at,
        program_changed=False,
        canvas_changed=False,
    )


def save_program_review_note(
    db: Session,
    *,
    context: AgentTrustedContext,
    program_id: int,
    payload: ProgramReviewNoteSaveIn,
) -> ProgramReviewNoteOut:
    if context.role not in {"program_designer", "administrator"}:
        _deny()
    program = (
        db.query(Program)
        .filter(
            Program.id == program_id,
            Program.organization_id == context.organization_id,
            Program.is_active.is_(True),
        )
        .with_for_update()
        .one_or_none()
    )
    if program is None:
        _deny()
    route, source_digest = _program_gap_material(
        db,
        context=context,
        program=program,
    )
    candidate = route.candidate
    if route.analysis_truncated or candidate is None:
        raise ProgramReviewNoteConflict("source_changed")
    expected_ref = _program_review_draft_ref(
        context=context,
        program=program,
        focus_key=candidate.focus_key,
        source_digest=source_digest,
    )
    if not hmac.compare_digest(expected_ref, payload.draft_ref):
        raise ProgramReviewNoteConflict("source_changed")

    note = (
        db.query(ProgramReviewNote)
        .filter(
            ProgramReviewNote.organization_id == context.organization_id,
            ProgramReviewNote.program_id == program.id,
            ProgramReviewNote.finding_key == candidate.focus_key,
        )
        .with_for_update()
        .one_or_none()
    )
    current_version = note.version if note is not None else 0
    draft_content = _program_review_draft_content(candidate)
    draft_digest = hashlib.sha256(draft_content.encode("utf-8")).hexdigest()
    if (
        note is not None
        and note.decision == payload.decision
        and note.content == payload.content
        and note.source_digest == source_digest
        and note.initial_draft_digest == draft_digest
    ):
        return _program_review_note_out(note)
    if payload.expected_version != current_version:
        raise ProgramReviewNoteConflict("version")

    created = note is None
    if note is None:
        note = ProgramReviewNote(
            organization_id=context.organization_id,
            program_id=program.id,
            finding_key=candidate.focus_key,
            finding_kind=candidate.candidate_type,
            source_digest=source_digest,
            initial_draft_digest=draft_digest,
            content=payload.content,
            decision=payload.decision,
            version=1,
            created_by_user_id=context.user_id,
            updated_by_user_id=context.user_id,
        )
        db.add(note)
    else:
        note.finding_kind = candidate.candidate_type
        note.source_digest = source_digest
        note.initial_draft_digest = draft_digest
        note.content = payload.content
        note.decision = payload.decision
        note.version += 1
        note.updated_by_user_id = context.user_id
    db.flush()
    db.add(
        ProgramChangeEvent(
            program_id=program.id,
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            event_type=(
                "program_review_note_created"
                if created
                else "program_review_note_updated"
            ),
            entity_type="program_review_note",
            entity_id=note.id,
            version=note.version,
            event_metadata={
                "decision": note.decision,
                "note_version": note.version,
                "source_digest": note.source_digest,
                "finding_key_digest": hashlib.sha256(
                    note.finding_key.encode("utf-8")
                ).hexdigest(),
            },
        )
    )
    db.flush()
    return _program_review_note_out(note)


def _result_digest(
    result: (
        AgentProgramRouteBriefOut
        | AgentProgramEvidenceRouteOut
        | AgentProgramReviewDraftOut
    ),
) -> str:
    return hashlib.sha256(result.model_dump_json().encode("utf-8")).hexdigest()


def _source_digest(value: dict) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _raw_evidence_manifest(
    db: Session,
    *,
    program_id: int,
    contribution_ids: set[int],
) -> dict:
    if not contribution_ids:
        return {"contributions": [], "learning_objectives": [], "assessment_items": []}
    contributions = (
        db.query(CourseContribution)
        .filter(
            CourseContribution.program_id == program_id,
            CourseContribution.id.in_(sorted(contribution_ids)),
        )
        .order_by(CourseContribution.id)
        .all()
    )
    learning_ids = sorted(
        {
            row.evidence_id
            for row in contributions
            if row.evidence_type == "learning_objective" and row.evidence_id is not None
        }
    )
    assessment_ids = sorted(
        {
            row.evidence_id
            for row in contributions
            if row.evidence_type == "assessment_item" and row.evidence_id is not None
        }
    )
    learning_rows = (
        db.query(LearningObjective)
        .filter(LearningObjective.id.in_(learning_ids))
        .order_by(LearningObjective.id)
        .all()
        if learning_ids
        else []
    )
    assessment_rows = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.id.in_(assessment_ids))
        .order_by(AssessmentItem.id)
        .all()
        if assessment_ids
        else []
    )
    return {
        "contributions": [
            {
                "id": row.id,
                "competency_id": row.competency_id,
                "course_id": row.course_id,
                "stage": row.stage,
                "rationale": row.rationale,
                "evidence_type": row.evidence_type,
                "evidence_id": row.evidence_id,
                "updated_at": row.updated_at,
            }
            for row in contributions
        ],
        "learning_objectives": [
            {
                "id": row.id,
                "course_id": row.course_id,
                "text": row.text,
                "confidence": row.confidence,
                "review_status": row.review_status,
            }
            for row in learning_rows
        ],
        "assessment_items": [
            {
                "id": row.id,
                "course_id": row.course_id,
                "title": row.title,
                "text": row.text,
                "confidence": row.confidence,
                "review_status": row.review_status,
            }
            for row in assessment_rows
        ],
    }


def execute_program_run(
    db: Session,
    *,
    principal: Principal,
    run_id: int,
) -> AgentRun:
    row = db.query(AgentRun).filter(AgentRun.id == run_id).one_or_none()
    if row is None:
        _deny()
    context = resolve_agent_context(db, principal, organization_id=row.organization_id)
    tool_name = {
        "program.inspect_map.v1": "get_program_competency_map",
        "program.inspect_gap.v1": "inspect_program_gap",
        "program.inspect_prerequisite.v1": "inspect_prerequisite_path",
        "program.draft_review_note.v1": "draft_program_review_note",
    }.get(row.workflow)
    if tool_name is None:
        _deny()
    definition = TOOL_REGISTRY[tool_name]
    _configure_statement_timeout(db, definition.timeout_seconds)
    row = (
        db.query(AgentRun).filter(AgentRun.id == run_id).with_for_update().one_or_none()
    )
    if (
        row is None
        or not _exact_context(row, context)
        or row.workflow not in EXECUTABLE_PROGRAM_WORKFLOWS
    ):
        _deny()
    if row.status in {"completed", "abstained", "failed"}:
        return row
    if row.status != "tool_running" or not row.selection_ref:
        raise HTTPException(status_code=409, detail="run is not ready to execute")

    evidence_source_digest: str | None = None
    if row.workflow == "program.inspect_map.v1":
        result: (
            AgentProgramRouteBriefOut
            | AgentProgramEvidenceRouteOut
            | AgentProgramReviewDraftOut
        ) = _run_validated_tool(
            db,
            row,
            principal,
            tool_name=tool_name,
            tool_input=ProgramRouteToolIn(program_ref=row.selection_ref),
            call=lambda _deadline: current_program_route_brief(
                db, context=context, signed_ref=row.selection_ref or ""
            ),
            output_projection=lambda value: ProgramRouteToolOut(
                program_title=value.program_title,
                program_version=value.program_version,
                counts=value.counts,
                priorities=value.priorities,
                analysis_truncated=value.analysis_truncated,
                findings_truncated=value.findings_truncated,
                limitations=value.limitations,
            ),
            organization_id=row.organization_id,
        )
        if not isinstance(result, AgentProgramRouteBriefOut):
            raise ValueError("program route result is invalid")
    elif row.workflow == "program.draft_review_note.v1":

        def load_review_draft(_deadline: float) -> AgentProgramReviewDraftOut:
            nonlocal evidence_source_digest
            value, evidence_source_digest = current_program_review_draft(
                db,
                context=context,
                signed_ref=row.selection_ref or "",
            )
            return value

        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name=tool_name,
            tool_input=ProgramRouteToolIn(program_ref=row.selection_ref),
            call=load_review_draft,
            output_projection=lambda value: ProgramReviewToolOut(
                state=value.state,
                program_title=value.program_title,
                program_version=value.program_version,
                headline=value.headline,
                draft_ref=value.draft_ref,
                candidate=value.candidate,
                content=value.content,
                source_fingerprint=value.source_fingerprint,
                current_note=value.current_note,
                limitations=value.limitations,
                program_changed=value.program_changed,
                canvas_changed=value.canvas_changed,
            ),
            organization_id=row.organization_id,
        )
        if not isinstance(result, AgentProgramReviewDraftOut):
            raise ValueError("program review draft result is invalid")
    else:
        workflow = row.workflow
        if workflow not in {
            "program.inspect_gap.v1",
            "program.inspect_prerequisite.v1",
        }:
            _deny()

        def load_evidence_route(_deadline: float) -> AgentProgramEvidenceRouteOut:
            nonlocal evidence_source_digest
            value, evidence_source_digest = current_program_evidence_material(
                db,
                context=context,
                signed_ref=row.selection_ref or "",
                workflow=workflow,
            )
            return value

        result = _run_validated_tool(
            db,
            row,
            principal,
            tool_name=tool_name,
            tool_input=ProgramRouteToolIn(program_ref=row.selection_ref),
            call=load_evidence_route,
            output_projection=lambda value: ProgramEvidenceToolOut(
                route_kind=value.route_kind,
                state=value.state,
                program_title=value.program_title,
                program_version=value.program_version,
                headline=value.headline,
                candidate=value.candidate,
                analysis_truncated=value.analysis_truncated,
                action_target=value.action_target,
                action_label=value.action_label,
                limitations=value.limitations,
            ),
            organization_id=row.organization_id,
        )
        if not isinstance(result, AgentProgramEvidenceRouteOut):
            raise ValueError("program evidence route result is invalid")
    current = resolve_agent_context(db, principal, organization_id=row.organization_id)
    if not _exact_context(row, current):
        _deny()
    resolve_program_ref(db, context=current, signed_ref=row.selection_ref)
    if evidence_source_digest is not None:
        if row.workflow == "program.draft_review_note.v1":
            _, latest_source_digest = current_program_review_draft(
                db,
                context=current,
                signed_ref=row.selection_ref,
            )
        else:
            _, latest_source_digest = current_program_evidence_material(
                db,
                context=current,
                signed_ref=row.selection_ref,
                workflow=row.workflow,
            )
        if not hmac.compare_digest(evidence_source_digest, latest_source_digest):
            _deny()
        row.result_digest = evidence_source_digest
    else:
        row.result_digest = _result_digest(result)
    row.status = "completed"
    row.label = (
        "Маршрут проверки программы готов"
        if row.workflow == "program.inspect_map.v1"
        else (
            "Черновик заметки по программе готов"
            if row.workflow == "program.draft_review_note.v1"
            else "Доказательный маршрут программы готов"
        )
    )
    row.recovery_action = None
    db.commit()
    db.refresh(row)
    return row


def project_program_route_brief(
    db: Session,
    *,
    row: AgentRun,
) -> AgentProgramRouteBriefOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow != "program.inspect_map.v1"
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    result = current_program_route_brief(
        db, context=context, signed_ref=row.selection_ref
    )
    if not hmac.compare_digest(row.result_digest, _result_digest(result)):
        _deny()
    return result


def project_program_evidence_route(
    db: Session,
    *,
    row: AgentRun,
) -> AgentProgramEvidenceRouteOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow
        not in {"program.inspect_gap.v1", "program.inspect_prerequisite.v1"}
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    result, source_digest = current_program_evidence_material(
        db,
        context=context,
        signed_ref=row.selection_ref,
        workflow=row.workflow,
    )
    if not hmac.compare_digest(row.result_digest, source_digest):
        _deny()
    return result


def project_program_review_draft(
    db: Session,
    *,
    row: AgentRun,
) -> AgentProgramReviewDraftOut:
    context = AgentTrustedContext(
        organization_id=row.organization_id,
        course_id=row.course_id,
        user_id=row.user_id,
        role=row.role,
        product_session_id=row.product_session_id,
    )
    if (
        row.workflow != "program.draft_review_note.v1"
        or not row.selection_ref
        or not row.result_digest
    ):
        _deny()
    result, material_digest = current_program_review_draft(
        db,
        context=context,
        signed_ref=row.selection_ref,
    )
    if not hmac.compare_digest(row.result_digest, material_digest):
        _deny()
    return result


__all__ = [
    "EXECUTABLE_PROGRAM_WORKFLOWS",
    "build_program_route_brief",
    "build_program_gap_route",
    "build_program_prerequisite_route",
    "build_program_review_draft",
    "current_program_evidence_route",
    "current_program_evidence_material",
    "current_program_review_draft",
    "current_program_route_brief",
    "execute_program_run",
    "list_program_options",
    "program_ref",
    "project_program_evidence_route",
    "project_program_review_draft",
    "project_program_route_brief",
    "resolve_program_ref",
    "save_program_review_note",
    "ProgramReviewNoteConflict",
]
