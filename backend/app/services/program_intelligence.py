from __future__ import annotations

import os

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from ..models.models import (
    AssessmentItem,
    Competency,
    Course,
    CourseContribution,
    Dataset,
    LearningObjective,
    Organization,
    OrganizationMembership,
    Program,
    ProgramChangeEvent,
    ProgramCourse,
    ProgramPrerequisiteRelation,
)
from ..schemas.program_intelligence import (
    CompetencyCreateIn,
    CompetencyMapOut,
    CompetencyOut,
    ContributionEvidenceOut,
    CourseContributionOut,
    CourseContributionUpsertIn,
    PrerequisiteEvidenceOut,
    PrerequisiteRelationDeleteIn,
    PrerequisiteRelationMutationOut,
    PrerequisiteRelationOut,
    PrerequisiteRelationUpsertIn,
    ProgramAdministrationItemOut,
    ProgramAdministrationOverviewOut,
    ProgramAdministrationTotalsOut,
    ProgramAuditCountsOut,
    ProgramAuditEvidenceOut,
    ProgramAuditFindingOut,
    ProgramAuditPreviewOut,
    ProgramAuthoringContextOut,
    ProgramAuthoringCourseOut,
    ProgramCourseOrderIn,
    ProgramCourseOrderOut,
    ProgramCourseOut,
    ProgramCreateIn,
    ProgramDemoOut,
    ProgramEvidenceOptionOut,
    ProgramEvidenceOptionsOut,
    ProgramMapCountsOut,
    ProgramMapOut,
    ProgramSummaryOut,
)

PROGRAM_READ_ROLES = frozenset({"methodologist", "program_designer", "administrator"})
PROGRAM_WRITE_ROLES = frozenset({"program_designer", "administrator"})
PROGRAM_ADMIN_ROLES = frozenset({"administrator"})
DEMO_PROGRAM_CODE = "CS-FOUND"
AUTHORING_COURSE_LIMIT = 500
AUTHORING_EVIDENCE_LIMIT = 100
PROGRAM_AUDIT_COMPETENCY_LIMIT = 500
PROGRAM_AUDIT_CONTRIBUTION_LIMIT = 5000
PROGRAM_AUDIT_FINDING_LIMIT = 500
PROGRAM_AUDIT_EVIDENCE_LIMIT = 8
PROGRAM_ADMIN_OVERVIEW_LIMIT = 200
PROGRAM_PREREQUISITE_LIMIT = 500


class ProgramScopeDenied(Exception):
    pass


class ProgramVersionConflict(Exception):
    pass


class ProgramDuplicate(Exception):
    pass


class ProgramCourseOrderConflict(Exception):
    pass


class ProgramCourseRemovalDenied(Exception):
    pass


class ProgramPrerequisiteConflict(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def _require_program_role(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
    write: bool,
) -> None:
    allowed = PROGRAM_WRITE_ROLES if write else PROGRAM_READ_ROLES
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.role.in_(allowed),
            OrganizationMembership.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise ProgramScopeDenied


def _require_program_administrator(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
) -> None:
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.role.in_(PROGRAM_ADMIN_ROLES),
            OrganizationMembership.is_active.is_(True),
        )
        .first()
    )
    if membership is None:
        raise ProgramScopeDenied


def _organization(
    db: Session,
    organization_id: int,
    *,
    lock: bool = False,
) -> Organization:
    query = db.query(Organization).filter(
        Organization.id == organization_id,
        Organization.is_active.is_(True),
    )
    if lock:
        query = query.with_for_update()
    organization = query.first()
    if organization is None:
        raise ProgramScopeDenied
    return organization


def _program(
    db: Session,
    program_id: int,
    *,
    organization_id: int | None = None,
    lock: bool = False,
) -> Program:
    query = db.query(Program).filter(
        Program.id == program_id,
        Program.is_active.is_(True),
    )
    if organization_id is not None:
        query = query.filter(Program.organization_id == organization_id)
    if lock:
        query = query.with_for_update()
    program = query.first()
    if program is None:
        raise ProgramScopeDenied
    return program


def _event(
    db: Session,
    *,
    program: Program,
    actor_user_id: int | None,
    event_type: str,
    entity_type: str,
    entity_id: int | None,
    metadata: dict,
) -> None:
    db.add(
        ProgramChangeEvent(
            program_id=program.id,
            organization_id=program.organization_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            version=program.version,
            event_metadata=metadata,
        )
    )


def _summary(db: Session, program: Program) -> ProgramSummaryOut:
    competency_ids = [
        item_id
        for (item_id,) in db.query(Competency.id)
        .filter(Competency.program_id == program.id)
        .all()
    ]
    course_count = (
        db.query(ProgramCourse.id)
        .join(Course, Course.id == ProgramCourse.course_id)
        .filter(
            ProgramCourse.program_id == program.id,
            Course.organization_id == program.organization_id,
        )
        .count()
    )
    assessed_count = 0
    if competency_ids:
        assessed_count = (
            db.query(CourseContribution.competency_id)
            .join(
                ProgramCourse,
                (ProgramCourse.program_id == CourseContribution.program_id)
                & (ProgramCourse.course_id == CourseContribution.course_id),
            )
            .join(Course, Course.id == CourseContribution.course_id)
            .join(Competency, Competency.id == CourseContribution.competency_id)
            .filter(
                CourseContribution.program_id == program.id,
                CourseContribution.stage == "assessed",
                Course.organization_id == program.organization_id,
                Competency.program_id == program.id,
            )
            .distinct()
            .count()
        )
    return ProgramSummaryOut(
        id=program.id,
        organization_id=program.organization_id,
        code=program.code,
        title=program.title,
        description=program.description,
        version=program.version,
        is_active=program.is_active,
        competency_count=len(competency_ids),
        course_count=course_count,
        assessed_competency_count=assessed_count,
        updated_at=program.updated_at,
    )


def list_programs(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
) -> list[ProgramSummaryOut]:
    _organization(db, organization_id)
    _require_program_role(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        write=False,
    )
    programs = (
        db.query(Program)
        .filter(
            Program.organization_id == organization_id,
            Program.is_active.is_(True),
        )
        .order_by(Program.title, Program.id)
        .all()
    )
    return [_summary(db, item) for item in programs]


def get_program_administration_overview(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
) -> ProgramAdministrationOverviewOut:
    _organization(db, organization_id)
    _require_program_administrator(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
    )
    program_rows = (
        db.query(Program)
        .filter(
            Program.organization_id == organization_id,
            Program.is_active.is_(True),
        )
        .order_by(Program.title, Program.id)
        .limit(PROGRAM_ADMIN_OVERVIEW_LIMIT + 1)
        .all()
    )
    analysis_truncated = len(program_rows) > PROGRAM_ADMIN_OVERVIEW_LIMIT
    programs = program_rows[:PROGRAM_ADMIN_OVERVIEW_LIMIT]
    program_ids = [program.id for program in programs]

    course_counts: dict[int, int] = {}
    competency_counts: dict[int, int] = {}
    mapped_counts: dict[int, int] = {}
    assessed_counts: dict[int, int] = {}
    if program_ids:
        course_counts = {
            program_id: count
            for program_id, count in db.query(
                ProgramCourse.program_id,
                func.count(ProgramCourse.id),
            )
            .join(Course, Course.id == ProgramCourse.course_id)
            .filter(
                ProgramCourse.program_id.in_(program_ids),
                Course.organization_id == organization_id,
            )
            .group_by(ProgramCourse.program_id)
            .all()
        }
        competency_counts = {
            program_id: count
            for program_id, count in db.query(
                Competency.program_id,
                func.count(Competency.id),
            )
            .filter(Competency.program_id.in_(program_ids))
            .group_by(Competency.program_id)
            .all()
        }
        valid_contributions = (
            db.query(
                CourseContribution.program_id,
                func.count(func.distinct(CourseContribution.competency_id)),
            )
            .join(
                ProgramCourse,
                (ProgramCourse.program_id == CourseContribution.program_id)
                & (ProgramCourse.course_id == CourseContribution.course_id),
            )
            .join(Course, Course.id == CourseContribution.course_id)
            .join(
                Competency,
                (Competency.id == CourseContribution.competency_id)
                & (Competency.program_id == CourseContribution.program_id),
            )
            .filter(
                CourseContribution.program_id.in_(program_ids),
                Course.organization_id == organization_id,
            )
        )
        mapped_counts = {
            program_id: count
            for program_id, count in valid_contributions.group_by(
                CourseContribution.program_id
            ).all()
        }
        assessed_counts = {
            program_id: count
            for program_id, count in valid_contributions.filter(
                CourseContribution.stage == "assessed"
            )
            .group_by(CourseContribution.program_id)
            .all()
        }

    items: list[ProgramAdministrationItemOut] = []
    for program in programs:
        course_count = course_counts.get(program.id, 0)
        competency_count = competency_counts.get(program.id, 0)
        mapped_count = min(mapped_counts.get(program.id, 0), competency_count)
        assessed_count = min(assessed_counts.get(program.id, 0), competency_count)
        unmapped_count = max(competency_count - mapped_count, 0)
        without_assessment_count = max(competency_count - assessed_count, 0)
        if not course_count or not competency_count:
            route_state = "not_started"
            route_state_label = "Маршрут ещё не собран"
        elif unmapped_count:
            route_state = "mapping_gap"
            route_state_label = "Есть компетенции без курса"
        elif without_assessment_count:
            route_state = "assessment_gap"
            route_state_label = "Нужно сверить заявленные проверки"
        else:
            route_state = "declared_assessment_complete"
            route_state_label = "Для всех компетенций заявлена проверка"
        items.append(
            ProgramAdministrationItemOut(
                program_id=program.id,
                program_code=program.code,
                program_title=program.title,
                program_version=program.version,
                updated_at=program.updated_at,
                course_count=course_count,
                competency_count=competency_count,
                mapped_competency_count=mapped_count,
                assessed_competency_count=assessed_count,
                unmapped_competency_count=unmapped_count,
                without_assessment_count=without_assessment_count,
                route_state=route_state,
                route_state_label=route_state_label,
            )
        )

    return ProgramAdministrationOverviewOut(
        organization_id=organization_id,
        analysis_truncated=analysis_truncated,
        totals=ProgramAdministrationTotalsOut(
            programs=len(items),
            courses=sum(item.course_count for item in items),
            competencies=sum(item.competency_count for item in items),
            mapped_competencies=sum(item.mapped_competency_count for item in items),
            assessed_competencies=sum(item.assessed_competency_count for item in items),
            programs_requiring_review=sum(
                item.route_state != "declared_assessment_complete" for item in items
            ),
            programs_not_started=sum(
                item.route_state == "not_started" for item in items
            ),
        ),
        programs=items,
    )


def create_program(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
    payload: ProgramCreateIn,
) -> ProgramSummaryOut:
    _organization(db, organization_id, lock=True)
    _require_program_role(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    code = payload.code.strip().upper()
    if (
        db.query(Program)
        .filter(Program.organization_id == organization_id, Program.code == code)
        .first()
        is not None
    ):
        raise ProgramDuplicate
    program = Program(
        organization_id=organization_id,
        code=code,
        title=payload.title.strip(),
        description=payload.description.strip(),
        version=1,
        is_active=True,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(program)
    db.flush()
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type="program_created",
        entity_type="program",
        entity_id=program.id,
        metadata={"code": program.code},
    )
    db.flush()
    return _summary(db, program)


def get_program_authoring_context(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
) -> ProgramAuthoringContextOut:
    program = _program(db, program_id)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    rows = (
        db.query(Course)
        .filter(Course.organization_id == program.organization_id)
        .order_by(Course.title, Course.id)
        .limit(AUTHORING_COURSE_LIMIT + 1)
        .all()
    )
    program_positions = {
        row.course_id: row.position
        for row in db.query(ProgramCourse)
        .filter(ProgramCourse.program_id == program.id)
        .all()
    }
    return ProgramAuthoringContextOut(
        program_id=program.id,
        program_version=program.version,
        courses=[
            ProgramAuthoringCourseOut(
                id=course.id,
                title=course.title,
                description=course.description[:500],
                in_program=course.id in program_positions,
                position=program_positions.get(course.id),
            )
            for course in rows[:AUTHORING_COURSE_LIMIT]
        ],
        courses_truncated=len(rows) > AUTHORING_COURSE_LIMIT,
    )


def get_program_evidence_options(
    db: Session,
    *,
    program_id: int,
    course_id: int,
    actor_user_id: int | None,
) -> ProgramEvidenceOptionsOut:
    program = _program(db, program_id)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.organization_id == program.organization_id,
        )
        .first()
    )
    if course is None:
        raise ProgramScopeDenied
    objectives = (
        db.query(LearningObjective)
        .filter(LearningObjective.course_id == course.id)
        .order_by(LearningObjective.id.desc())
        .limit(AUTHORING_EVIDENCE_LIMIT + 1)
        .all()
    )
    assessments = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.course_id == course.id)
        .order_by(AssessmentItem.id.desc())
        .limit(AUTHORING_EVIDENCE_LIMIT + 1)
        .all()
    )
    options = [
        ProgramEvidenceOptionOut(
            evidence_type="learning_objective",
            evidence_id=objective.id,
            label=objective.text[:160] or "Цель курса",
            excerpt=objective.text[:500],
            confidence=objective.confidence,
            review_status=objective.review_status,
        )
        for objective in objectives[:AUTHORING_EVIDENCE_LIMIT]
    ]
    options.extend(
        ProgramEvidenceOptionOut(
            evidence_type="assessment_item",
            evidence_id=assessment.id,
            label=assessment.title or assessment.text[:160] or "Задание курса",
            excerpt=assessment.text[:500],
            confidence=assessment.confidence,
            review_status=assessment.review_status,
        )
        for assessment in assessments[:AUTHORING_EVIDENCE_LIMIT]
    )
    return ProgramEvidenceOptionsOut(
        course_id=course.id,
        options=options,
        options_truncated=(
            len(objectives) > AUTHORING_EVIDENCE_LIMIT
            or len(assessments) > AUTHORING_EVIDENCE_LIMIT
        ),
    )


def _program_course_order_out(
    db: Session,
    *,
    program: Program,
    changed: bool,
) -> ProgramCourseOrderOut:
    rows = (
        db.query(ProgramCourse, Course)
        .join(Course, Course.id == ProgramCourse.course_id)
        .filter(
            ProgramCourse.program_id == program.id,
            Course.organization_id == program.organization_id,
        )
        .order_by(ProgramCourse.position, ProgramCourse.id)
        .all()
    )
    return ProgramCourseOrderOut(
        courses=[
            ProgramCourseOut(id=course.id, title=course.title, position=row.position)
            for row, course in rows
        ],
        program_version=program.version,
        changed=changed,
    )


def set_program_course_order(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
    payload: ProgramCourseOrderIn,
) -> ProgramCourseOrderOut:
    program = _program(db, program_id, lock=True)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    if program.version != payload.expected_version:
        raise ProgramVersionConflict
    existing_rows = (
        db.query(ProgramCourse)
        .filter(ProgramCourse.program_id == program.id)
        .order_by(ProgramCourse.position, ProgramCourse.id)
        .all()
    )
    existing_ids = [row.course_id for row in existing_rows]
    if not set(existing_ids).issubset(payload.course_ids):
        raise ProgramCourseRemovalDenied
    courses = (
        db.query(Course)
        .filter(
            Course.id.in_(payload.course_ids),
            Course.organization_id == program.organization_id,
        )
        .all()
    )
    if len(courses) != len(payload.course_ids):
        raise ProgramScopeDenied
    if existing_ids == payload.course_ids:
        return _program_course_order_out(db, program=program, changed=False)

    rows_by_course = {row.course_id: row for row in existing_rows}
    temporary_start = (
        max(
            [len(payload.course_ids), *(row.position for row in existing_rows)],
            default=0,
        )
        + len(payload.course_ids)
        + 1
    )
    for offset, row in enumerate(existing_rows):
        row.position = temporary_start + offset
    if existing_rows:
        db.flush()
    added_course_ids = []
    for position, course_id in enumerate(payload.course_ids, start=1):
        row = rows_by_course.get(course_id)
        if row is None:
            row = ProgramCourse(
                program_id=program.id,
                course_id=course_id,
                position=position,
                added_by_user_id=actor_user_id,
            )
            rows_by_course[course_id] = row
            added_course_ids.append(course_id)
            db.add(row)
        else:
            row.position = position
    db.flush()
    program.version += 1
    program.updated_by_user_id = actor_user_id
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type="program_course_order_changed",
        entity_type="program",
        entity_id=program.id,
        metadata={
            "course_ids": payload.course_ids,
            "course_count": len(payload.course_ids),
            "added_course_ids": added_course_ids,
        },
    )
    db.flush()
    return _program_course_order_out(db, program=program, changed=True)


def add_competency(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
    payload: CompetencyCreateIn,
) -> CompetencyOut:
    program = _program(db, program_id, lock=True)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    if program.version != payload.expected_version:
        raise ProgramVersionConflict
    code = payload.code.strip().upper()
    if (
        db.query(Competency)
        .filter(Competency.program_id == program.id, Competency.code == code)
        .first()
        is not None
    ):
        raise ProgramDuplicate
    competency = Competency(
        program_id=program.id,
        code=code,
        title=payload.title.strip(),
        description=payload.description.strip(),
        position=payload.position,
    )
    db.add(competency)
    db.flush()
    program.version += 1
    program.updated_by_user_id = actor_user_id
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type="competency_created",
        entity_type="competency",
        entity_id=competency.id,
        metadata={"code": competency.code, "position": competency.position},
    )
    db.flush()
    return CompetencyOut(
        id=competency.id,
        program_id=competency.program_id,
        code=competency.code,
        title=competency.title,
        description=competency.description,
        position=competency.position,
        created_at=competency.created_at,
        updated_at=competency.updated_at,
        program_version=program.version,
    )


def _validate_evidence(
    db: Session,
    *,
    course: Course,
    evidence_type: str,
    evidence_id: int | None,
) -> None:
    if evidence_type == "manual_note":
        if evidence_id is not None:
            raise ProgramScopeDenied
        return
    model = (
        LearningObjective if evidence_type == "learning_objective" else AssessmentItem
    )
    evidence = (
        db.query(model)
        .filter(model.id == evidence_id, model.course_id == course.id)
        .first()
    )
    if evidence is None:
        raise ProgramScopeDenied


def upsert_course_contribution(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
    payload: CourseContributionUpsertIn,
) -> CourseContributionOut:
    program = _program(db, program_id, lock=True)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    if program.version != payload.expected_version:
        raise ProgramVersionConflict
    competency = (
        db.query(Competency)
        .filter(
            Competency.id == payload.competency_id,
            Competency.program_id == program.id,
        )
        .first()
    )
    course = (
        db.query(Course)
        .filter(
            Course.id == payload.course_id,
            Course.organization_id == program.organization_id,
        )
        .first()
    )
    if competency is None or course is None:
        raise ProgramScopeDenied
    _validate_evidence(
        db,
        course=course,
        evidence_type=payload.evidence_type,
        evidence_id=payload.evidence_id,
    )
    program_course = (
        db.query(ProgramCourse)
        .filter(
            ProgramCourse.program_id == program.id,
            ProgramCourse.course_id == course.id,
        )
        .first()
    )
    if program_course is None:
        course_count = (
            db.query(ProgramCourse)
            .filter(ProgramCourse.program_id == program.id)
            .count()
        )
        if course_count >= AUTHORING_COURSE_LIMIT:
            raise ProgramCourseOrderConflict
        position_taken = (
            db.query(ProgramCourse)
            .filter(
                ProgramCourse.program_id == program.id,
                ProgramCourse.position == payload.course_position,
            )
            .first()
        )
        if position_taken is not None:
            raise ProgramCourseOrderConflict
        program_course = ProgramCourse(
            program_id=program.id,
            course_id=course.id,
            position=payload.course_position,
            added_by_user_id=actor_user_id,
        )
        db.add(program_course)
        db.flush()
    elif program_course.position != payload.course_position:
        raise ProgramCourseOrderConflict
    contribution = (
        db.query(CourseContribution)
        .filter(
            CourseContribution.competency_id == competency.id,
            CourseContribution.course_id == course.id,
        )
        .first()
    )
    event_type = "course_contribution_updated"
    if contribution is None:
        event_type = "course_contribution_created"
        contribution = CourseContribution(
            program_id=program.id,
            competency_id=competency.id,
            course_id=course.id,
            created_by_user_id=actor_user_id,
        )
        db.add(contribution)
    contribution.stage = payload.stage
    contribution.rationale = payload.rationale.strip()
    contribution.evidence_type = payload.evidence_type
    contribution.evidence_id = payload.evidence_id
    contribution.updated_by_user_id = actor_user_id
    db.flush()
    program.version += 1
    program.updated_by_user_id = actor_user_id
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type="course_contribution",
        entity_id=contribution.id,
        metadata={
            "competency_id": competency.id,
            "course_id": course.id,
            "course_position": program_course.position,
            "stage": contribution.stage,
            "evidence_type": contribution.evidence_type,
        },
    )
    db.flush()
    return _contribution_out(db, contribution, program.version)


def _evidence_out(
    db: Session,
    contribution: CourseContribution,
) -> ContributionEvidenceOut:
    if contribution.evidence_type == "manual_note":
        return ContributionEvidenceOut(
            state="manual",
            evidence_type="manual_note",
            label="Комментарий автора карты",
            excerpt=contribution.rationale,
            review_status="human_declared",
        )
    if contribution.evidence_type == "learning_objective":
        evidence = db.get(LearningObjective, contribution.evidence_id)
        if evidence is not None and evidence.course_id == contribution.course_id:
            return ContributionEvidenceOut(
                state="live",
                evidence_type="learning_objective",
                evidence_id=evidence.id,
                label="Цель курса",
                excerpt=evidence.text[:1200],
                confidence=evidence.confidence,
                review_status=evidence.review_status,
            )
    else:
        evidence = db.get(AssessmentItem, contribution.evidence_id)
        if evidence is not None and evidence.course_id == contribution.course_id:
            return ContributionEvidenceOut(
                state="live",
                evidence_type="assessment_item",
                evidence_id=evidence.id,
                label=evidence.title or "Задание курса",
                excerpt=evidence.text[:1200],
                confidence=evidence.confidence,
                review_status=evidence.review_status,
            )
    return ContributionEvidenceOut(
        state="missing",
        evidence_type=contribution.evidence_type,
        evidence_id=contribution.evidence_id,
        label="Источник требует повторной привязки",
        excerpt="Связанное доказательство больше недоступно в текущей версии курса.",
        review_status="missing",
    )


def _contribution_out(
    db: Session,
    contribution: CourseContribution,
    program_version: int,
) -> CourseContributionOut:
    return CourseContributionOut(
        id=contribution.id,
        program_id=contribution.program_id,
        competency_id=contribution.competency_id,
        course_id=contribution.course_id,
        stage=contribution.stage,
        rationale=contribution.rationale,
        evidence=_evidence_out(db, contribution),
        updated_at=contribution.updated_at,
        program_version=program_version,
    )


def _program_audit_evidence_out(
    *,
    contribution: CourseContribution,
    course: Course,
    course_position: int,
    evidence_lookup: dict[tuple[str, int], LearningObjective | AssessmentItem],
) -> ProgramAuditEvidenceOut:
    if contribution.evidence_type == "manual_note":
        evidence = ContributionEvidenceOut(
            state="manual",
            evidence_type="manual_note",
            label="Комментарий автора карты",
            excerpt=contribution.rationale,
            review_status="human_declared",
        )
    else:
        source = (
            evidence_lookup.get((contribution.evidence_type, contribution.evidence_id))
            if contribution.evidence_id is not None
            else None
        )
        if (
            contribution.evidence_type == "learning_objective"
            and isinstance(source, LearningObjective)
            and source.course_id == contribution.course_id
        ):
            evidence = ContributionEvidenceOut(
                state="live",
                evidence_type="learning_objective",
                evidence_id=source.id,
                label="Цель курса",
                excerpt=source.text,
                confidence=source.confidence,
                review_status=source.review_status,
            )
        elif (
            contribution.evidence_type == "assessment_item"
            and isinstance(source, AssessmentItem)
            and source.course_id == contribution.course_id
        ):
            evidence = ContributionEvidenceOut(
                state="live",
                evidence_type="assessment_item",
                evidence_id=source.id,
                label=source.title or "Задание курса",
                excerpt=source.text,
                confidence=source.confidence,
                review_status=source.review_status,
            )
        else:
            evidence = ContributionEvidenceOut(
                state="missing",
                evidence_type=contribution.evidence_type,
                evidence_id=contribution.evidence_id,
                label="Источник требует повторной привязки",
                excerpt=(
                    "Связанное доказательство больше недоступно в текущей "
                    "версии курса."
                ),
                review_status="missing",
            )
    return ProgramAuditEvidenceOut(
        contribution_id=contribution.id,
        course_id=course.id,
        course_title=course.title[:160],
        course_position=course_position,
        stage=contribution.stage,
        rationale=contribution.rationale[:500],
        evidence_state=evidence.state,
        evidence_type=evidence.evidence_type,
        evidence_label=evidence.label[:160],
        evidence_excerpt=evidence.excerpt[:500],
        evidence_confidence=evidence.confidence,
        evidence_review_status=evidence.review_status,
    )


def get_program_audit_preview(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
) -> ProgramAuditPreviewOut:
    program = _program(db, program_id)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=False,
    )
    competency_rows = (
        db.query(Competency)
        .filter(Competency.program_id == program.id)
        .order_by(Competency.position, Competency.code, Competency.id)
        .limit(PROGRAM_AUDIT_COMPETENCY_LIMIT + 1)
        .all()
    )
    competencies = competency_rows[:PROGRAM_AUDIT_COMPETENCY_LIMIT]
    program_course_rows = (
        db.query(ProgramCourse, Course)
        .join(Course, Course.id == ProgramCourse.course_id)
        .filter(
            ProgramCourse.program_id == program.id,
            Course.organization_id == program.organization_id,
        )
        .order_by(ProgramCourse.position, ProgramCourse.id)
        .limit(AUTHORING_COURSE_LIMIT + 1)
        .all()
    )
    courses_over_limit = len(program_course_rows) > AUTHORING_COURSE_LIMIT
    program_course_rows = program_course_rows[:AUTHORING_COURSE_LIMIT]
    courses_by_id = {course.id: course for _, course in program_course_rows}
    course_positions = {row.course_id: row.position for row, _ in program_course_rows}
    competency_ids = [competency.id for competency in competencies]
    course_ids = list(courses_by_id)

    contribution_totals: dict[int, int] = {}
    contributions: list[CourseContribution] = []
    contributions_over_limit = False
    if competency_ids and course_ids:
        contribution_totals = {
            competency_id: count
            for competency_id, count in (
                db.query(
                    CourseContribution.competency_id,
                    func.count(CourseContribution.id),
                )
                .filter(
                    CourseContribution.program_id == program.id,
                    CourseContribution.competency_id.in_(competency_ids),
                )
                .group_by(CourseContribution.competency_id)
                .all()
            )
        }
        contribution_rows = (
            db.query(CourseContribution)
            .filter(
                CourseContribution.program_id == program.id,
                CourseContribution.competency_id.in_(competency_ids),
                CourseContribution.course_id.in_(course_ids),
            )
            .order_by(
                CourseContribution.competency_id,
                CourseContribution.course_id,
                CourseContribution.id,
            )
            .limit(PROGRAM_AUDIT_CONTRIBUTION_LIMIT + 1)
            .all()
        )
        contributions_over_limit = (
            len(contribution_rows) > PROGRAM_AUDIT_CONTRIBUTION_LIMIT
        )
        contributions = contribution_rows[:PROGRAM_AUDIT_CONTRIBUTION_LIMIT]

    by_competency: dict[int, list[CourseContribution]] = {
        competency.id: [] for competency in competencies
    }
    for contribution in contributions:
        by_competency[contribution.competency_id].append(contribution)
    for items in by_competency.values():
        items.sort(
            key=lambda contribution: (
                course_positions[contribution.course_id],
                contribution.id,
            )
        )

    objective_ids = {
        item.evidence_id
        for item in contributions
        if item.evidence_type == "learning_objective" and item.evidence_id is not None
    }
    assessment_ids = {
        item.evidence_id
        for item in contributions
        if item.evidence_type == "assessment_item" and item.evidence_id is not None
    }
    evidence_lookup: dict[tuple[str, int], LearningObjective | AssessmentItem] = {}
    if objective_ids:
        evidence_lookup.update(
            {
                ("learning_objective", objective.id): objective
                for objective in db.query(LearningObjective)
                .filter(
                    LearningObjective.id.in_(objective_ids),
                    LearningObjective.course_id.in_(course_ids),
                )
                .all()
            }
        )
    if assessment_ids:
        evidence_lookup.update(
            {
                ("assessment_item", assessment.id): assessment
                for assessment in db.query(AssessmentItem)
                .filter(
                    AssessmentItem.id.in_(assessment_ids),
                    AssessmentItem.course_id.in_(course_ids),
                )
                .all()
            }
        )

    findings: list[tuple[int, int, str, ProgramAuditFindingOut]] = []
    kind_order = {
        "coverage_gap": 0,
        "assessment_gap": 1,
        "evidence_gap": 2,
        "duplication_check": 3,
        "sequence_check": 4,
    }
    for competency in competencies:
        items = by_competency.get(competency.id, [])
        total_items = contribution_totals.get(competency.id, 0)
        complete = len(items) == total_items
        evidence_by_id = {
            item.id: _program_audit_evidence_out(
                contribution=item,
                course=courses_by_id[item.course_id],
                course_position=course_positions[item.course_id],
                evidence_lookup=evidence_lookup,
            )
            for item in items
        }

        def append_finding(
            *,
            kind: str,
            attention: str,
            title: str,
            detail: str,
            confidence: str,
            confidence_label: str,
            evidence_items: list[CourseContribution],
            evidence_status: str,
        ) -> None:
            finding = ProgramAuditFindingOut(
                key=f"{kind}:{competency.id}",
                kind=kind,
                attention=attention,
                competency_id=competency.id,
                competency_code=competency.code,
                competency_title=competency.title,
                title=title,
                detail=detail,
                confidence=confidence,
                confidence_label=confidence_label,
                review_status="not_reviewed",
                evidence_status=evidence_status,
                evidence_truncated=(len(evidence_items) > PROGRAM_AUDIT_EVIDENCE_LIMIT),
                evidence=[
                    evidence_by_id[item.id]
                    for item in evidence_items[:PROGRAM_AUDIT_EVIDENCE_LIMIT]
                ],
            )
            findings.append(
                (
                    0 if attention == "review" else 1,
                    competency.position,
                    kind_order[kind],
                    finding,
                )
            )

        if total_items == 0:
            append_finding(
                kind="coverage_gap",
                attention="review",
                title="Компетенция не связана с курсом",
                detail=("В текущей карте нет ни одного явно заявленного вклада курса."),
                confidence="high",
                confidence_label="Факт по сохранённой карте",
                evidence_items=[],
                evidence_status="none",
            )
            continue

        missing_items = [
            item
            for item in items
            if evidence_by_id[item.id].evidence_state == "missing"
        ]
        if missing_items:
            append_finding(
                kind="evidence_gap",
                attention="review",
                title="Источник связи недоступен",
                detail=(
                    "Связь сохранена, но выбранное основание больше нельзя проверить "
                    "в текущей версии курса."
                ),
                confidence="high",
                confidence_label="Факт по состоянию источника",
                evidence_items=missing_items,
                evidence_status="missing",
            )

        if not complete:
            continue
        assessed_items = [item for item in items if item.stage == "assessed"]
        learning_items = [
            item for item in items if item.stage in {"introduced", "developed"}
        ]
        repeated_learning_stages = {
            stage
            for stage in ("introduced", "developed")
            if len({item.course_id for item in items if item.stage == stage}) >= 2
        }
        if repeated_learning_stages:
            duplicated_items = [
                item for item in items if item.stage in repeated_learning_stages
            ]
            duplicated_items.sort(
                key=lambda item: (course_positions[item.course_id], item.id)
            )
            repeated_stage_counts = [
                (label, len({item.course_id for item in items if item.stage == stage}))
                for stage, label in (
                    ("introduced", "«вводится»"),
                    ("developed", "«развивается»"),
                )
                if stage in repeated_learning_stages
            ]
            if len(repeated_stage_counts) == 1:
                label, course_count = repeated_stage_counts[0]
                repeated_stage_detail = (
                    f"Этап {label} явно заявлен в {course_count} курсах. "
                )
            else:
                repeated_stage_detail = (
                    "Повторяются этапы: "
                    + "; ".join(
                        f"{label} — в {course_count} курсах"
                        for label, course_count in repeated_stage_counts
                    )
                    + ". "
                )
            duplicated_missing = any(
                evidence_by_id[item.id].evidence_state == "missing"
                for item in duplicated_items
            )
            append_finding(
                kind="duplication_check",
                attention="watch",
                title="Один этап компетенции повторяется в нескольких курсах",
                detail=(
                    repeated_stage_detail
                    + "Это может быть осознанной спиралью обучения, а не лишним "
                    "повтором — основания нужно сопоставить методически."
                ),
                confidence="medium",
                confidence_label="Явный повтор — нужна методическая сверка",
                evidence_items=duplicated_items,
                evidence_status=("missing" if duplicated_missing else "declared"),
            )
        if not assessed_items:
            append_finding(
                kind="assessment_gap",
                attention="review",
                title="В маршруте нет заявленной проверки",
                detail=(
                    "Компетенция вводится или развивается, но ни один курс не "
                    "помечен как проверяющий её."
                ),
                confidence="high",
                confidence_label="Факт по заявленным этапам",
                evidence_items=items,
                evidence_status=("missing" if missing_items else "declared"),
            )
        if assessed_items and learning_items:
            earliest_assessed = min(
                assessed_items,
                key=lambda item: course_positions[item.course_id],
            )
            earliest_learning = min(
                learning_items,
                key=lambda item: course_positions[item.course_id],
            )
            if (
                course_positions[earliest_assessed.course_id]
                < course_positions[earliest_learning.course_id]
            ):
                append_finding(
                    kind="sequence_check",
                    attention="watch",
                    title="Проверка стоит раньше обучения",
                    detail=(
                        "По заявленной карте проверяющий курс идёт раньше первого "
                        "курса, который вводит или развивает компетенцию. Порядок "
                        "может быть намеренным — его нужно сверить."
                    ),
                    confidence="medium",
                    confidence_label="Структурный сигнал — нужна сверка",
                    evidence_items=[earliest_assessed, earliest_learning],
                    evidence_status=("missing" if missing_items else "declared"),
                )

    findings.sort(key=lambda item: item[:3])
    finding_rows = [item[3] for item in findings]
    findings_truncated = len(finding_rows) > PROGRAM_AUDIT_FINDING_LIMIT
    finding_rows = finding_rows[:PROGRAM_AUDIT_FINDING_LIMIT]
    counts_by_kind = {
        kind: sum(finding.kind == kind for finding in finding_rows)
        for kind in kind_order
    }
    counts = ProgramAuditCountsOut(
        total=len(finding_rows),
        review=sum(finding.attention == "review" for finding in finding_rows),
        watch=sum(finding.attention == "watch" for finding in finding_rows),
        **counts_by_kind,
    )
    return ProgramAuditPreviewOut(
        program_id=program.id,
        program_version=program.version,
        analyzed_competencies=len(competencies),
        analyzed_contributions=len(contributions),
        analysis_truncated=(
            len(competency_rows) > PROGRAM_AUDIT_COMPETENCY_LIMIT
            or courses_over_limit
            or contributions_over_limit
        ),
        findings_truncated=findings_truncated,
        counts=counts,
        findings=finding_rows,
    )


def _prerequisite_would_cycle(
    relations: list[ProgramPrerequisiteRelation],
    *,
    prerequisite_competency_id: int,
    target_competency_id: int,
) -> bool:
    adjacency: dict[int, set[int]] = {}
    for relation in relations:
        adjacency.setdefault(relation.prerequisite_competency_id, set()).add(
            relation.target_competency_id
        )
    stack = [target_competency_id]
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        if current == prerequisite_competency_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(adjacency.get(current, ()))
    return False


def upsert_prerequisite_relation(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
    payload: PrerequisiteRelationUpsertIn,
) -> PrerequisiteRelationMutationOut:
    program = _program(db, program_id, lock=True)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    if program.version != payload.expected_version:
        raise ProgramVersionConflict
    if payload.prerequisite_competency_id == payload.target_competency_id:
        raise ProgramPrerequisiteConflict("self_link")
    competencies = (
        db.query(Competency)
        .filter(
            Competency.program_id == program.id,
            Competency.id.in_(
                [
                    payload.prerequisite_competency_id,
                    payload.target_competency_id,
                ]
            ),
        )
        .all()
    )
    if len(competencies) != 2:
        raise ProgramScopeDenied
    relations = (
        db.query(ProgramPrerequisiteRelation)
        .filter(ProgramPrerequisiteRelation.program_id == program.id)
        .order_by(ProgramPrerequisiteRelation.id)
        .all()
    )
    relation = next(
        (
            item
            for item in relations
            if item.prerequisite_competency_id == payload.prerequisite_competency_id
            and item.target_competency_id == payload.target_competency_id
        ),
        None,
    )
    rationale = payload.rationale.strip()
    if relation is not None and relation.rationale == rationale:
        return PrerequisiteRelationMutationOut(
            relation_id=relation.id,
            program_version=program.version,
            changed=False,
        )
    if relation is None:
        if len(relations) >= PROGRAM_PREREQUISITE_LIMIT:
            raise ProgramPrerequisiteConflict("limit")
        if _prerequisite_would_cycle(
            relations,
            prerequisite_competency_id=payload.prerequisite_competency_id,
            target_competency_id=payload.target_competency_id,
        ):
            raise ProgramPrerequisiteConflict("cycle")
        relation = ProgramPrerequisiteRelation(
            program_id=program.id,
            prerequisite_competency_id=payload.prerequisite_competency_id,
            target_competency_id=payload.target_competency_id,
            rationale=rationale,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        )
        db.add(relation)
        event_type = "program_prerequisite_created"
    else:
        relation.rationale = rationale
        relation.updated_by_user_id = actor_user_id
        event_type = "program_prerequisite_updated"
    db.flush()
    program.version += 1
    program.updated_by_user_id = actor_user_id
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type=event_type,
        entity_type="program_prerequisite",
        entity_id=relation.id,
        metadata={
            "prerequisite_competency_id": relation.prerequisite_competency_id,
            "target_competency_id": relation.target_competency_id,
        },
    )
    db.flush()
    return PrerequisiteRelationMutationOut(
        relation_id=relation.id,
        program_version=program.version,
        changed=True,
    )


def delete_prerequisite_relation(
    db: Session,
    *,
    program_id: int,
    relation_id: int,
    actor_user_id: int | None,
    payload: PrerequisiteRelationDeleteIn,
) -> PrerequisiteRelationMutationOut:
    program = _program(db, program_id, lock=True)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    if program.version != payload.expected_version:
        raise ProgramVersionConflict
    relation = (
        db.query(ProgramPrerequisiteRelation)
        .filter(
            ProgramPrerequisiteRelation.id == relation_id,
            ProgramPrerequisiteRelation.program_id == program.id,
        )
        .first()
    )
    if relation is None:
        raise ProgramScopeDenied
    prerequisite_competency_id = relation.prerequisite_competency_id
    target_competency_id = relation.target_competency_id
    db.delete(relation)
    db.flush()
    program.version += 1
    program.updated_by_user_id = actor_user_id
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type="program_prerequisite_deleted",
        entity_type="program_prerequisite",
        entity_id=relation_id,
        metadata={
            "prerequisite_competency_id": prerequisite_competency_id,
            "target_competency_id": target_competency_id,
        },
    )
    db.flush()
    return PrerequisiteRelationMutationOut(
        relation_id=relation_id,
        program_version=program.version,
        changed=True,
    )


def _prerequisite_evidence_out(
    db: Session,
    *,
    contribution: CourseContribution,
    course: Course,
    course_position: int,
) -> PrerequisiteEvidenceOut:
    evidence = _evidence_out(db, contribution)
    return PrerequisiteEvidenceOut(
        contribution_id=contribution.id,
        competency_id=contribution.competency_id,
        course_id=course.id,
        course_title=course.title,
        course_position=course_position,
        stage=contribution.stage,
        evidence_state=evidence.state,
        evidence_label=evidence.label,
        evidence_excerpt=evidence.excerpt[:500],
        evidence_review_status=evidence.review_status,
    )


def get_program_map(
    db: Session,
    *,
    program_id: int,
    actor_user_id: int | None,
) -> ProgramMapOut:
    program = _program(db, program_id)
    _require_program_role(
        db,
        organization_id=program.organization_id,
        actor_user_id=actor_user_id,
        write=False,
    )
    competencies = (
        db.query(Competency)
        .filter(Competency.program_id == program.id)
        .order_by(Competency.position, Competency.code, Competency.id)
        .all()
    )
    program_course_rows = (
        db.query(ProgramCourse, Course)
        .join(Course, Course.id == ProgramCourse.course_id)
        .filter(
            ProgramCourse.program_id == program.id,
            Course.organization_id == program.organization_id,
        )
        .order_by(ProgramCourse.position, ProgramCourse.id)
        .all()
    )
    contributions = (
        db.query(CourseContribution)
        .filter(CourseContribution.program_id == program.id)
        .order_by(CourseContribution.course_id, CourseContribution.id)
        .all()
    )
    courses_by_id = {course.id: course for _, course in program_course_rows}
    program_courses = [
        ProgramCourseOut(id=course.id, title=course.title, position=row.position)
        for row, course in program_course_rows
    ]
    course_positions = {row.course_id: row.position for row, _ in program_course_rows}
    by_competency: dict[int, list[CourseContribution]] = {
        item.id: [] for item in competencies
    }
    competency_ids = set(by_competency)
    valid_contributions = [
        contribution
        for contribution in contributions
        if contribution.course_id in courses_by_id
        and contribution.competency_id in competency_ids
    ]
    for contribution in valid_contributions:
        by_competency[contribution.competency_id].append(contribution)
    for competency_contributions in by_competency.values():
        competency_contributions.sort(
            key=lambda contribution: (
                course_positions[contribution.course_id],
                contribution.id,
            )
        )

    prerequisite_competency = aliased(Competency)
    target_competency = aliased(Competency)
    prerequisite_relation_rows = (
        db.query(
            ProgramPrerequisiteRelation,
            prerequisite_competency,
            target_competency,
        )
        .join(
            prerequisite_competency,
            prerequisite_competency.id
            == ProgramPrerequisiteRelation.prerequisite_competency_id,
        )
        .join(
            target_competency,
            target_competency.id == ProgramPrerequisiteRelation.target_competency_id,
        )
        .filter(
            ProgramPrerequisiteRelation.program_id == program.id,
            prerequisite_competency.program_id == program.id,
            target_competency.program_id == program.id,
        )
        .order_by(
            target_competency.position,
            target_competency.code,
            prerequisite_competency.position,
            prerequisite_competency.code,
            ProgramPrerequisiteRelation.id,
        )
        .limit(PROGRAM_PREREQUISITE_LIMIT + 1)
        .all()
    )
    prerequisites_truncated = (
        len(prerequisite_relation_rows) > PROGRAM_PREREQUISITE_LIMIT
    )
    prerequisite_rows: list[PrerequisiteRelationOut] = []
    for relation, prerequisite, target in prerequisite_relation_rows[
        :PROGRAM_PREREQUISITE_LIMIT
    ]:
        prerequisite_assessment = next(
            (
                item
                for item in by_competency.get(prerequisite.id, [])
                if item.stage == "assessed"
            ),
            None,
        )
        target_start = next(iter(by_competency.get(target.id, [])), None)
        prerequisite_evidence = (
            _prerequisite_evidence_out(
                db,
                contribution=prerequisite_assessment,
                course=courses_by_id[prerequisite_assessment.course_id],
                course_position=course_positions[prerequisite_assessment.course_id],
            )
            if prerequisite_assessment is not None
            else None
        )
        target_evidence = (
            _prerequisite_evidence_out(
                db,
                contribution=target_start,
                course=courses_by_id[target_start.course_id],
                course_position=course_positions[target_start.course_id],
            )
            if target_start is not None
            else None
        )
        if (
            prerequisite_evidence is None
            or target_evidence is None
            or prerequisite_evidence.evidence_state == "missing"
            or target_evidence.evidence_state == "missing"
        ):
            structural_state = "needs_evidence"
            structural_state_label = "Недостаточно оснований для проверки порядка"
        elif prerequisite_evidence.course_position >= target_evidence.course_position:
            structural_state = "order_check"
            structural_state_label = "Порядок требует методической сверки"
        else:
            structural_state = "declared_order"
            structural_state_label = (
                "Сохранённая структура соответствует заявленному порядку"
            )
        prerequisite_rows.append(
            PrerequisiteRelationOut(
                id=relation.id,
                program_id=program.id,
                prerequisite_competency_id=prerequisite.id,
                prerequisite_competency_code=prerequisite.code,
                prerequisite_competency_title=prerequisite.title,
                target_competency_id=target.id,
                target_competency_code=target.code,
                target_competency_title=target.title,
                rationale=relation.rationale,
                structural_state=structural_state,
                structural_state_label=structural_state_label,
                prerequisite_assessment=prerequisite_evidence,
                target_start=target_evidence,
                updated_at=relation.updated_at,
            )
        )

    competency_rows = []
    missing_evidence_cells = 0
    for competency in competencies:
        items = [
            _contribution_out(db, contribution, program.version)
            for contribution in by_competency.get(competency.id, [])
        ]
        missing_evidence_cells += sum(
            item.evidence.state == "missing" for item in items
        )
        if any(item.stage == "assessed" for item in items):
            coverage_state = "assessed"
        elif items:
            coverage_state = "learning_only"
        else:
            coverage_state = "unmapped"
        competency_rows.append(
            CompetencyMapOut(
                id=competency.id,
                code=competency.code,
                title=competency.title,
                description=competency.description,
                position=competency.position,
                coverage_state=coverage_state,
                contributions=items,
            )
        )
    assessed = sum(item.coverage_state == "assessed" for item in competency_rows)
    learning_only = sum(
        item.coverage_state == "learning_only" for item in competency_rows
    )
    unmapped = sum(item.coverage_state == "unmapped" for item in competency_rows)
    counts = ProgramMapCountsOut(
        competencies=len(competency_rows),
        courses=len(program_courses),
        mapped_cells=len(valid_contributions),
        assessed_competencies=assessed,
        learning_only_competencies=learning_only,
        unmapped_competencies=unmapped,
        missing_evidence_cells=missing_evidence_cells,
    )
    summary = _summary(db, program).model_copy(
        update={
            "competency_count": counts.competencies,
            "course_count": counts.courses,
            "assessed_competency_count": counts.assessed_competencies,
        }
    )
    return ProgramMapOut(
        program=summary,
        courses=program_courses,
        competencies=competency_rows,
        prerequisites=prerequisite_rows,
        prerequisites_truncated=prerequisites_truncated,
        counts=counts,
    )


def _demo_course(
    db: Session,
    *,
    organization_id: int,
    external_id: str,
    title: str,
    description: str,
) -> tuple[Course, bool]:
    course = (
        db.query(Course)
        .filter(
            Course.organization_id == organization_id,
            Course.external_id == external_id,
        )
        .first()
    )
    if course is not None:
        return course, False
    dataset = Dataset(name=f"demo:program:{external_id}")
    db.add(dataset)
    db.flush()
    course = Course(
        organization_id=organization_id,
        dataset_id=dataset.id,
        external_id=external_id,
        title=title,
        description=description,
        source_type="manual",
        source_metadata={"demo": True, "program_intelligence": True},
    )
    db.add(course)
    db.flush()
    return course, True


def create_demo_program(
    db: Session,
    *,
    organization_id: int,
    actor_user_id: int | None,
) -> ProgramDemoOut:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env == "production" or os.getenv("ENABLE_DEMO_SEED", "1") in {
        "0",
        "false",
        "False",
    }:
        raise ProgramScopeDenied
    _organization(db, organization_id, lock=True)
    _require_program_role(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        write=True,
    )
    existing = (
        db.query(Program)
        .filter(
            Program.organization_id == organization_id,
            Program.code == DEMO_PROGRAM_CODE,
        )
        .first()
    )
    if existing is not None:
        return ProgramDemoOut(
            program_id=existing.id,
            created=False,
            courses_created=0,
            competencies_created=0,
            contributions_created=0,
        )

    algorithms, algorithms_created = _demo_course(
        db,
        organization_id=organization_id,
        external_id="builtin:program-algorithms-v1",
        title="Алгоритмы и оценка сложности",
        description="Базовый курс о выборе и сравнении алгоритмов.",
    )
    structures, structures_created = _demo_course(
        db,
        organization_id=organization_id,
        external_id="builtin:program-structures-v1",
        title="Структуры данных: практикум",
        description="Практика выбора структур данных и обоснования решений.",
    )
    objective_algorithms = LearningObjective(
        course_id=algorithms.id,
        text="Сравнивать временную и пространственную сложность алгоритмов и объяснять выбор.",
        normalized_text="compare algorithm time space complexity",
        bloom_vector=[],
        top_bloom_levels=["analyze"],
        extraction_method="development_seed",
        confidence=1.0,
        review_status="confirmed",
    )
    objective_structures = LearningObjective(
        course_id=structures.id,
        text="Выбирать структуру данных под ограничения задачи и аргументировать компромиссы.",
        normalized_text="select data structure and justify tradeoffs",
        bloom_vector=[],
        top_bloom_levels=["evaluate"],
        extraction_method="development_seed",
        confidence=1.0,
        review_status="confirmed",
    )
    assessment = AssessmentItem(
        course_id=structures.id,
        assessment_type="project",
        title="Разбор архитектурного решения",
        text="Сравните два решения задачи и обоснуйте выбор алгоритма по времени и памяти.",
        expected_answer="development seed answer must never leave the backend",
        bloom_vector=[],
        top_bloom_levels=["evaluate"],
        extraction_method="development_seed",
        confidence=1.0,
        review_status="confirmed",
    )
    db.add_all([objective_algorithms, objective_structures, assessment])
    db.flush()
    program = Program(
        organization_id=organization_id,
        code=DEMO_PROGRAM_CODE,
        title="Основы компьютерных наук",
        description="Демонстрационная траектория из базовых алгоритмов к обоснованному проектированию.",
        version=1,
        is_active=True,
        created_by_user_id=actor_user_id,
        updated_by_user_id=actor_user_id,
    )
    db.add(program)
    db.flush()
    db.add_all(
        [
            ProgramCourse(
                program_id=program.id,
                course_id=algorithms.id,
                position=1,
                added_by_user_id=actor_user_id,
            ),
            ProgramCourse(
                program_id=program.id,
                course_id=structures.id,
                position=2,
                added_by_user_id=actor_user_id,
            ),
        ]
    )
    db.flush()
    competencies = [
        Competency(
            program_id=program.id,
            code="CS-01",
            title="Анализировать эффективность алгоритмов",
            description="Сравнивать решения по времени, памяти и ограничениям задачи.",
            position=1,
        ),
        Competency(
            program_id=program.id,
            code="CS-02",
            title="Выбирать подходящие структуры данных",
            description="Соотносить структуру данных с операциями и компромиссами.",
            position=2,
        ),
        Competency(
            program_id=program.id,
            code="CS-03",
            title="Документировать инженерные решения",
            description="Объяснять решение так, чтобы его можно было проверить и развить.",
            position=3,
        ),
    ]
    db.add_all(competencies)
    db.flush()
    contributions = [
        CourseContribution(
            program_id=program.id,
            competency_id=competencies[0].id,
            course_id=algorithms.id,
            stage="introduced",
            rationale="Курс вводит сравнение алгоритмов по времени и памяти.",
            evidence_type="learning_objective",
            evidence_id=objective_algorithms.id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ),
        CourseContribution(
            program_id=program.id,
            competency_id=competencies[0].id,
            course_id=structures.id,
            stage="assessed",
            rationale="Проект проверяет аргументированный выбор алгоритма под ограничения.",
            evidence_type="assessment_item",
            evidence_id=assessment.id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ),
        CourseContribution(
            program_id=program.id,
            competency_id=competencies[1].id,
            course_id=structures.id,
            stage="developed",
            rationale="Практикум развивает выбор структур данных и анализ компромиссов.",
            evidence_type="learning_objective",
            evidence_id=objective_structures.id,
            created_by_user_id=actor_user_id,
            updated_by_user_id=actor_user_id,
        ),
    ]
    db.add_all(contributions)
    _event(
        db,
        program=program,
        actor_user_id=actor_user_id,
        event_type="development_demo_created",
        entity_type="program",
        entity_id=program.id,
        metadata={"competencies": 3, "courses": 2, "contributions": 3},
    )
    db.flush()
    return ProgramDemoOut(
        program_id=program.id,
        created=True,
        courses_created=int(algorithms_created) + int(structures_created),
        competencies_created=3,
        contributions_created=3,
    )
