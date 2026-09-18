from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlencode, urlparse

from sqlalchemy.orm import Session

from ..models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseFinding,
    CourseMembership,
    CourseModule,
    CourseQuestionAnswer,
    Dataset,
    Document,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from .lti_development import LOCAL_CLIENT_ID, LOCAL_DEPLOYMENT_ID

SIMULATOR_ORGANIZATION_SLUG = "canvas-simulator-school"
SIMULATOR_LEARNER_EMAIL = "learner@canvas-simulator.test"
SIMULATOR_LEARNER_NAME = "Алина Соколова"
SIMULATOR_INSTRUCTOR_EMAIL = "instructor@canvas-simulator.test"
SIMULATOR_INSTRUCTOR_NAME = "Михаил Орлов"
SIMULATOR_SIGNAL_STUDENTS = (
    ("signal-learner-2@canvas-simulator.test", "Илья Ковалёв"),
    ("signal-learner-3@canvas-simulator.test", "Софья Волкова"),
    ("signal-learner-4@canvas-simulator.test", "Мария Лебедева"),
)
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "testserver"})


@dataclass(frozen=True)
class SimulatorItem:
    fixture_id: str
    title: str
    canvas_type: str
    content: str | None = None


@dataclass(frozen=True)
class SimulatorModule:
    fixture_id: str
    title: str
    items: tuple[SimulatorItem, ...]


@dataclass(frozen=True)
class SimulatorCourse:
    fixture_id: str
    title: str
    summary: str
    modules: tuple[SimulatorModule, ...]


@dataclass(frozen=True)
class SimulatorBootstrapResult:
    fixture_id: str
    course_id: int
    registration_id: int
    learner_subject: str
    instructor_subject: str
    launch_url: str
    instructor_launch_url: str
    chooser_url: str


@dataclass(frozen=True)
class SimulatorLaunchResult:
    fixture_id: str
    course_id: int
    registration_id: int
    actor: Literal["learner", "instructor"]
    subject: str
    launch_url: str
    chooser_url: str


SIMULATOR_COURSES = (
    SimulatorCourse(
        fixture_id="demo-ai",
        title="Проектная лаборатория: ИИ-сервисы",
        summary=(
            "Демо-курс показывает путь от идеи и данных до проверяемого "
            "прототипа. Все материалы синтетические."
        ),
        modules=(
            SimulatorModule(
                fixture_id="orientation",
                title="00. Старт проекта",
                items=(
                    SimulatorItem(
                        "brief",
                        "Как устроен курс и что мы создадим",
                        "Page",
                        "Курс ведёт от выбора полезной образовательной задачи к "
                        "прототипу, который отвечает по проверяемым источникам.",
                    ),
                    SimulatorItem(
                        "cases",
                        "Галерея полезных ИИ-сервисов",
                        "ExternalUrl",
                        "Полезный ИИ-сервис решает конкретную задачу пользователя и "
                        "показывает границы своей уверенности.",
                    ),
                    SimulatorItem(
                        "map",
                        "Карта проектного маршрута.pdf",
                        "File",
                        "Маршрут проекта: задача, корпус, поиск, проверка качества, "
                        "безопасность, демонстрация и рефлексия.",
                    ),
                ),
            ),
            SimulatorModule(
                fixture_id="rag",
                title="01. Данные и поиск",
                items=(
                    SimulatorItem("rag-section", "От документа к ответу", "SubHeader"),
                    SimulatorItem(
                        "rag-pipeline",
                        "Как устроен RAG-пайплайн",
                        "Page",
                        "RAG сначала находит подходящие фрагменты корпуса, затем "
                        "формирует ответ и прикладывает ссылки на использованные "
                        "источники.",
                    ),
                    SimulatorItem(
                        "chunking",
                        "Практикум: нарезка и поиск",
                        "Assignment",
                        "Сравните две стратегии нарезки документов и объясните, "
                        "какая лучше сохраняет смысл фрагмента.",
                    ),
                    SimulatorItem(
                        "retrieval",
                        "Визуальный разбор retrieval",
                        "ExternalUrl",
                        "Retrieval оценивают по тому, находятся ли релевантные "
                        "фрагменты и не смешиваются ли материалы разных курсов.",
                    ),
                ),
            ),
            SimulatorModule(
                fixture_id="quality",
                title="02. Качество и безопасность",
                items=(
                    SimulatorItem(
                        "evidence",
                        "Ответ, доказательство и уверенность",
                        "Page",
                        "Качественный ответ отделяет вывод от доказательства, "
                        "показывает источник и воздерживается от ответа при слабой "
                        "опоре.",
                    ),
                    SimulatorItem(
                        "red-team",
                        "Проверка границ помощника",
                        "Assignment",
                        "Проверьте помощника на вопросы вне курса, скрытые материалы "
                        "и попытки получить готовый ответ на оцениваемую работу.",
                    ),
                    SimulatorItem(
                        "rubric",
                        "Критерии качества прототипа.pdf",
                        "File",
                        "Критерии: полезность сценария, точность поиска, проверяемые "
                        "цитаты, безопасный отказ и понятный интерфейс.",
                    ),
                ),
            ),
            SimulatorModule(
                fixture_id="defense",
                title="03. Защита проекта",
                items=(
                    SimulatorItem(
                        "story",
                        "Как объяснить ценность продукта",
                        "Page",
                        "На защите покажите пользователя, его задачу, работающий "
                        "сценарий, доказательства качества и известные ограничения.",
                    ),
                    SimulatorItem(
                        "demo",
                        "Демо и защита ИИ-сервиса",
                        "Assignment",
                        "Проведите короткое демо от вопроса пользователя до ответа "
                        "с источником и объясните один безопасный отказ.",
                    ),
                ),
            ),
        ),
    ),
    SimulatorCourse(
        fixture_id="demo-review",
        title="Русский язык: мастерская рецензии",
        summary=(
            "Синтетический syllabus-first курс: цели, критерии и итоговые работы "
            "собраны на стартовой странице."
        ),
        modules=(
            SimulatorModule(
                fixture_id="reading",
                title="Неделя 1. Читаем как рецензенты",
                items=(
                    SimulatorItem(
                        "reading-section", "От наблюдения к аргументу", "SubHeader"
                    ),
                    SimulatorItem(
                        "lens",
                        "Три оптики внимательного чтения",
                        "Page",
                        "Рецензент различает наблюдение, интерпретацию и оценку. "
                        "Каждый вывод связывается с конкретной деталью произведения.",
                    ),
                    SimulatorItem(
                        "sample",
                        "Аннотированный пример рецензии.pdf",
                        "File",
                        "Сильная рецензия формулирует позицию, приводит точные "
                        "наблюдения и объясняет, как они подтверждают оценку.",
                    ),
                    SimulatorItem(
                        "notes",
                        "Черновик аналитических заметок",
                        "Assignment",
                        "Соберите наблюдения о композиции, языке и позиции автора, "
                        "не превращая заметки в готовую рецензию.",
                    ),
                ),
            ),
            SimulatorModule(
                fixture_id="writing",
                title="Неделя 2. Собираем текст",
                items=(
                    SimulatorItem(
                        "criteria",
                        "Критерии итоговой рецензии",
                        "Page",
                        "Итоговая рецензия оценивается по ясности тезиса, качеству "
                        "аргументов, точности примеров и самостоятельности вывода.",
                    ),
                    SimulatorItem(
                        "museum",
                        "Цифровая коллекция музея",
                        "ExternalUrl",
                        "Внешний источник используется как контекст; его факты нужно "
                        "отделять от собственной интерпретации произведения.",
                    ),
                    SimulatorItem(
                        "review",
                        "Итоговая рецензия",
                        "Assignment",
                        "Напишите рецензию с тезисом, двумя аргументами и выводом, "
                        "опираясь на выбранное произведение.",
                    ),
                ),
            ),
        ),
    ),
)

_COURSES_BY_ID = {course.fixture_id: course for course in SIMULATOR_COURSES}


def canvas_simulator_enabled() -> bool:
    return (
        os.getenv("APP_ENV", "development").strip().lower() != "production"
        and os.getenv("AUTH_MODE", "development").strip().lower() == "development"
        and os.getenv("CANVAS_SIMULATOR_ENABLED", "").strip().lower() == "true"
        and os.getenv("CANVAS_SIMULATOR_DATA_MODE", "").strip().lower() == "synthetic"
    )


def _loopback_origin(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("invalid simulator origin")
    try:
        parsed = urlparse(value)
        parsed.port
    except ValueError as exc:
        raise ValueError("invalid simulator origin") from exc
    if (
        parsed.scheme != "http"
        or parsed.hostname not in _LOOPBACK_HOSTS
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("simulator origin must be loopback HTTP")
    return value.rstrip("/")


def _upsert_organization(db: Session) -> Organization:
    organization = (
        db.query(Organization)
        .filter(Organization.slug == SIMULATOR_ORGANIZATION_SLUG)
        .first()
    )
    if organization is None:
        organization = Organization(
            slug=SIMULATOR_ORGANIZATION_SLUG,
            name="Canvas simulator · synthetic school",
            is_active=True,
        )
        db.add(organization)
        db.flush()
    else:
        organization.name = "Canvas simulator · synthetic school"
        organization.is_active = True
    return organization


def _upsert_actor(
    db: Session,
    organization: Organization,
    *,
    email: str,
    display_name: str,
    role: Literal["student", "instructor"],
) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        user = User(
            email=email,
            display_name=display_name,
            is_active=True,
        )
        db.add(user)
        db.flush()
    else:
        user.display_name = display_name
        user.is_active = True
    membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == organization.id,
            OrganizationMembership.user_id == user.id,
        )
        .first()
    )
    if membership is None:
        db.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
    else:
        membership.role = role
        membership.is_active = True
    return user


def _upsert_learner(db: Session, organization: Organization) -> User:
    return _upsert_actor(
        db,
        organization,
        email=SIMULATOR_LEARNER_EMAIL,
        display_name=SIMULATOR_LEARNER_NAME,
        role="student",
    )


def _upsert_instructor(db: Session, organization: Organization) -> User:
    return _upsert_actor(
        db,
        organization,
        email=SIMULATOR_INSTRUCTOR_EMAIL,
        display_name=SIMULATOR_INSTRUCTOR_NAME,
        role="instructor",
    )


def _item_url(canvas_origin: str, course_fixture_id: str, item: SimulatorItem) -> str:
    if item.canvas_type == "ExternalUrl":
        return f"https://example.edu/synthetic/{course_fixture_id}/{item.fixture_id}"
    query = urlencode({"view": "modules", "source": item.fixture_id})
    return f"{canvas_origin}/canvas-simulator/courses/{course_fixture_id}?{query}"


def _topology_item(
    canvas_origin: str,
    course_fixture_id: str,
    item: SimulatorItem,
    position: int,
) -> dict:
    value = {
        "id": item.fixture_id,
        "title": item.title,
        "type": item.canvas_type,
        "position": position,
        "student_visible": True,
        "canvas_published": True,
    }
    if item.canvas_type == "ExternalUrl":
        value["external_url"] = _item_url(canvas_origin, course_fixture_id, item)
    elif item.canvas_type != "SubHeader":
        value["html_url"] = _item_url(canvas_origin, course_fixture_id, item)
    return value


def _document_type(item: SimulatorItem) -> str | None:
    if item.canvas_type == "Page":
        return "lecture_material"
    if item.canvas_type == "File":
        return "resource"
    if item.canvas_type == "ExternalUrl":
        return "reference"
    if item.canvas_type == "Assignment":
        return "assignment"
    return None


def _upsert_course(
    db: Session,
    *,
    organization: Organization,
    learner: User,
    instructor: User,
    fixture: SimulatorCourse,
    canvas_origin: str,
) -> Course:
    external_id = f"canvas-simulator:{fixture.fixture_id}"
    course = (
        db.query(Course)
        .filter(
            Course.organization_id == organization.id,
            Course.source_type == "canvas",
            Course.external_id == external_id,
        )
        .first()
    )
    if course is None:
        dataset_name = f"canvas-simulator:{fixture.fixture_id}"
        dataset = db.query(Dataset).filter(Dataset.name == dataset_name).first()
        if dataset is None:
            dataset = Dataset(name=dataset_name)
            db.add(dataset)
            db.flush()
        elif db.query(Course).filter(Course.dataset_id == dataset.id).first():
            raise ValueError("simulator dataset belongs to another course")
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            external_id=external_id,
            title=fixture.title,
            description=fixture.summary,
            source_type="canvas",
            source_url=(
                f"{canvas_origin}/canvas-simulator/courses/"
                f"{fixture.fixture_id}?view=home"
            ),
            source_metadata={
                "synthetic": True,
                "canvas_simulator_fixture": fixture.fixture_id,
            },
        )
        db.add(course)
        db.flush()
    else:
        course.title = fixture.title
        course.description = fixture.summary
        course.source_url = (
            f"{canvas_origin}/canvas-simulator/courses/"
            f"{fixture.fixture_id}?view=home"
        )
        course.source_metadata = {
            "synthetic": True,
            "canvas_simulator_fixture": fixture.fixture_id,
        }

    for user, role in ((learner, "student"), (instructor, "instructor")):
        membership = (
            db.query(CourseMembership)
            .filter(
                CourseMembership.course_id == course.id,
                CourseMembership.user_id == user.id,
            )
            .first()
        )
        if membership is None:
            db.add(
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=user.id,
                    role=role,
                    is_active=True,
                )
            )
        else:
            membership.organization_id = organization.id
            membership.role = role
            membership.is_active = True

    for module_position, module_fixture in enumerate(fixture.modules, start=1):
        module = (
            db.query(CourseModule)
            .filter(
                CourseModule.course_id == course.id,
                CourseModule.external_id == module_fixture.fixture_id,
            )
            .first()
        )
        topology = [
            _topology_item(
                canvas_origin,
                fixture.fixture_id,
                item,
                item_position,
            )
            for item_position, item in enumerate(module_fixture.items, start=1)
        ]
        if module is None:
            module = CourseModule(
                course_id=course.id,
                external_id=module_fixture.fixture_id,
                title=module_fixture.title,
                position=module_position,
            )
            db.add(module)
            db.flush()
        module.title = module_fixture.title
        module.position = module_position
        module.source_url = (
            f"{canvas_origin}/canvas-simulator/courses/"
            f"{fixture.fixture_id}?view=modules"
        )
        module.meta = {
            "workflow_state": "active",
            "course_map_items": topology,
            "canvas_simulator_fixture": fixture.fixture_id,
        }

        for item_position, item in enumerate(module_fixture.items, start=1):
            document_type = _document_type(item)
            if document_type is None or item.content is None:
                continue
            document_external_id = f"simulator:{fixture.fixture_id}:{item.fixture_id}"
            document = (
                db.query(Document)
                .filter(
                    Document.dataset_id == course.dataset_id,
                    Document.external_id == document_external_id,
                )
                .first()
            )
            if document is None:
                document = Document(
                    dataset_id=course.dataset_id,
                    external_id=document_external_id,
                    title=item.title,
                    source=_item_url(canvas_origin, fixture.fixture_id, item),
                    mime="text/plain",
                    status="ready",
                    course_module_id=module.id,
                )
                db.add(document)
                db.flush()
            document.title = item.title
            document.source = _item_url(canvas_origin, fixture.fixture_id, item)
            document.status = "ready"
            document.course_module_id = module.id
            document.source_metadata = {
                "document_type": document_type,
                "student_visible": True,
                "canvas_published": True,
                "canvas_position": item_position,
                "synthetic": True,
                "canvas_simulator_fixture": fixture.fixture_id,
            }
            chunks = (
                db.query(Chunk)
                .filter(Chunk.document_id == document.id)
                .order_by(Chunk.idx)
                .all()
            )
            if not chunks:
                db.add(
                    Chunk(
                        document_id=document.id,
                        idx=0,
                        text=item.content,
                        meta={"source_start": 0, "source_end": len(item.content)},
                    )
                )
            else:
                chunks[0].idx = 0
                chunks[0].text = item.content
                chunks[0].meta = {
                    "source_start": 0,
                    "source_end": len(item.content),
                }
                for extra in chunks[1:]:
                    db.delete(extra)
    return course


def _upsert_synthetic_teacher_review(
    db: Session,
    *,
    course: Course,
    fixture: SimulatorCourse,
) -> None:
    """Keep the local Canvas demo useful without claiming a production audit."""

    run = (
        db.query(AuditRun)
        .filter(
            AuditRun.course_id == course.id,
            AuditRun.pipeline_version == "canvas-simulator-synthetic-v1",
        )
        .one_or_none()
    )
    if run is None:
        run = AuditRun(
            course_id=course.id,
            pipeline_version="canvas-simulator-synthetic-v1",
            extractor_version="synthetic-fixture-v1",
            classifier_version="synthetic-fixture-v1",
            embedding_model="none",
            relation_model="synthetic-fixture-v1",
        )
        db.add(run)
        db.flush()
    run.status = "done"
    run.config = {"synthetic": True, "fixture_id": fixture.fixture_id}
    run.error = None
    run.finished_at = datetime.now(timezone.utc)
    run.metrics = {
        "stage": "complete",
        "progress": 100,
        "synthetic": True,
        "summary": {
            "objectives_total": 4 if fixture.fixture_id == "demo-ai" else 3,
            "materials_total": 5 if fixture.fixture_id == "demo-ai" else 4,
            "assessments_total": 2,
            "objectives_with_material": 3,
            "objectives_with_assessment": 2,
            "objective_material_coverage": (
                0.75 if fixture.fixture_id == "demo-ai" else 1.0
            ),
            "objective_assessment_coverage": (
                0.5 if fixture.fixture_id == "demo-ai" else 0.6667
            ),
            "findings_total": 2,
            "high_severity_findings": 1,
        },
    }

    source_rows = (
        db.query(Document, Chunk)
        .join(Chunk, Chunk.document_id == Document.id)
        .filter(Document.dataset_id == course.dataset_id)
        .order_by(Document.id, Chunk.idx)
        .limit(2)
        .all()
    )
    if len(source_rows) < 2:
        raise ValueError("synthetic teacher review requires two course sources")

    finding_copy = {
        "demo-ai": (
            (
                "objective_without_assessment",
                "Цель по оценке качества не закреплена в итоговом задании",
                "В материалах качество описано как отдельный этап, но в задании нет явного критерия, по которому ученик должен его доказать.",
                "Добавьте в итоговое задание проверяемый критерий качества и попросите ученика сослаться на результат своей проверки.",
                0.86,
            ),
            (
                "bloom_mismatch",
                "Рефлексия проверяет описание, а не обоснование решения",
                "Формулировка позволяет перечислить шаги проекта без анализа причин выбранного подхода.",
                "Попросите сравнить два варианта решения и обосновать сделанный выбор.",
                0.68,
            ),
        ),
        "demo-review": (
            (
                "objective_without_assessment",
                "Аргументация не выделена отдельным критерием рецензии",
                "Курс учит подтверждать суждение текстом, но итоговая работа не требует показать эту связь явно.",
                "Добавьте критерий: каждый вывод рецензии должен опираться на конкретный фрагмент исходного текста.",
                0.88,
            ),
            (
                "objective_without_material",
                "Переход от наблюдения к тезису требует примера",
                "В курсе есть правило, но нет короткого разобранного образца этого перехода.",
                "Добавьте один аннотированный пример: наблюдение, тезис и пояснение связи между ними.",
                0.64,
            ),
        ),
    }[fixture.fixture_id]

    existing = {
        item.finding_type: item
        for item in db.query(CourseFinding)
        .filter(CourseFinding.audit_run_id == run.id)
        .all()
    }
    keep_types = set()
    for index, (
        finding_type,
        title,
        description,
        recommendation,
        confidence,
    ) in enumerate(finding_copy):
        keep_types.add(finding_type)
        document, chunk = source_rows[index]
        finding = existing.get(finding_type)
        if finding is None:
            finding = CourseFinding(
                course_id=course.id,
                audit_run_id=run.id,
                finding_type=finding_type,
            )
            db.add(finding)
        finding.severity = "high" if index == 0 else "medium"
        finding.title = title
        finding.description = description
        finding.evidence = [
            {
                "object_type": "course_source",
                "object_id": document.id,
                "document_id": document.id,
                "quote": " ".join(chunk.text.split())[:420],
                "start": 0,
                "end": min(len(chunk.text), 420),
            }
        ]
        finding.recommendation = recommendation
        finding.confidence = confidence
        finding.uncertainty_reasons = (
            []
            if index == 0
            else ["Сводка основана на текущей синтетической версии курса."]
        )
        finding.status = "new"
        finding.reviewed_by = None
        finding.reviewed_at = None
        finding.model_info = {"synthetic": True}
    for finding_type, finding in existing.items():
        if finding_type not in keep_types:
            db.delete(finding)


def _upsert_synthetic_learning_gap(
    db: Session,
    *,
    organization: Organization,
    course: Course,
    learner: User,
) -> None:
    """Seed one privacy-thresholded demo signal without exposing it as real data."""

    students = [learner]
    for email, display_name in SIMULATOR_SIGNAL_STUDENTS:
        student = _upsert_actor(
            db,
            organization,
            email=email,
            display_name=display_name,
            role="student",
        )
        students.append(student)
        membership = (
            db.query(CourseMembership)
            .filter(
                CourseMembership.course_id == course.id,
                CourseMembership.user_id == student.id,
            )
            .one_or_none()
        )
        if membership is None:
            db.add(
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=student.id,
                    role="student",
                    is_active=True,
                )
            )
        else:
            membership.organization_id = organization.id
            membership.role = "student"
            membership.is_active = True

    document, chunk = (
        db.query(Document, Chunk)
        .join(Chunk, Chunk.document_id == Document.id)
        .filter(
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .order_by(Document.id, Chunk.idx)
        .first()
    )
    citation = {
        "source_id": "S1",
        "document_id": document.id,
        "chunk_id": chunk.id,
        "quote": " ".join(chunk.text.split())[:900],
    }
    now = datetime.now(timezone.utc)
    for index, student in enumerate(students, start=1):
        answer = (
            db.query(CourseQuestionAnswer)
            .filter(
                CourseQuestionAnswer.course_id == course.id,
                CourseQuestionAnswer.asked_by_user_id == student.id,
                CourseQuestionAnswer.retrieval_method
                == "canvas-simulator-synthetic-gap-v1",
            )
            .one_or_none()
        )
        if answer is None:
            answer = CourseQuestionAnswer(
                course_id=course.id,
                asked_by_user_id=student.id,
                retrieval_method="canvas-simulator-synthetic-gap-v1",
                generation_provider="template",
            )
            db.add(answer)
        answer.question = (
            f"Синтетический вопрос {index}: как применить идею из этого материала?"
        )
        answer.answer = (
            "Синтетический честный отказ: в текущей опоре не хватило пояснения."
        )
        answer.citations = [citation]
        answer.confidence = 0.2
        answer.generation_model = None
        answer.insufficient_context = True
        answer.response_mode = "abstained"
        answer.policy_reason = "insufficient_context"
        answer.tutor_policy_version = 1
        answer.tutor_answer_style = "balanced"
        answer.feedback_status = "unreviewed"
        answer.feedback_comment = None
        answer.reviewed_by = None
        answer.reviewed_at = None
        answer.created_at = now


def _upsert_registration(
    db: Session,
    *,
    organization: Organization,
    learner: User,
    instructor: User,
    course: Course,
    fixture_id: str,
    lti_origin: str,
) -> SimulatorBootstrapResult:
    issuer = f"{lti_origin}/integrations/lti/development/platform/{fixture_id}"
    client_id = f"{LOCAL_CLIENT_ID}-{fixture_id}"
    deployment_id = f"{LOCAL_DEPLOYMENT_ID}-{fixture_id}"
    registration = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.client_id == client_id,
            LtiRegistration.deployment_id == deployment_id,
        )
        .order_by(LtiRegistration.id)
        .first()
    )
    if registration is None:
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer=issuer,
            client_id=client_id,
            deployment_id=deployment_id,
            authorization_endpoint=(
                f"{lti_origin}/integrations/lti/development/authorize"
            ),
            jwks_url=f"{lti_origin}/integrations/lti/development/jwks",
            tool_launch_url=f"{lti_origin}/integrations/lti/launch",
            is_active=True,
            is_development=True,
        )
        db.add(registration)
        db.flush()
    elif registration.organization_id != organization.id:
        raise ValueError("simulator registration belongs to another organization")
    else:
        registration.issuer = issuer
        registration.authorization_endpoint = (
            f"{lti_origin}/integrations/lti/development/authorize"
        )
        registration.jwks_url = f"{lti_origin}/integrations/lti/development/jwks"
        registration.tool_launch_url = f"{lti_origin}/integrations/lti/launch"
        registration.is_active = True
        registration.is_development = True

    context_id = f"canvas-simulator-context-{fixture_id}"
    context = (
        db.query(LtiContextBinding)
        .filter(LtiContextBinding.registration_id == registration.id)
        .first()
    )
    if context is None:
        context = LtiContextBinding(
            registration_id=registration.id,
            course_id=course.id,
            platform_context_id=context_id,
        )
        db.add(context)
    else:
        context.course_id = course.id
        context.platform_context_id = context_id

    subjects = {}
    for actor, user in (("learner", learner), ("instructor", instructor)):
        platform_subject = f"canvas-simulator-subject-{fixture_id}-{actor}"
        subject = (
            db.query(LtiSubjectBinding)
            .filter(
                LtiSubjectBinding.registration_id == registration.id,
                LtiSubjectBinding.user_id == user.id,
            )
            .first()
        )
        if subject is None:
            subject = LtiSubjectBinding(
                registration_id=registration.id,
                user_id=user.id,
                platform_subject=platform_subject,
            )
            db.add(subject)
        else:
            subject.platform_subject = platform_subject
        subjects[actor] = platform_subject

    launch_query = urlencode(
        {"registration_id": registration.id, "subject": subjects["learner"]}
    )
    instructor_launch_query = urlencode(
        {"registration_id": registration.id, "subject": subjects["instructor"]}
    )
    return SimulatorBootstrapResult(
        fixture_id=fixture_id,
        course_id=course.id,
        registration_id=registration.id,
        learner_subject=subjects["learner"],
        instructor_subject=subjects["instructor"],
        launch_url=(f"{lti_origin}/integrations/lti/development/start?{launch_query}"),
        instructor_launch_url=(
            f"{lti_origin}/integrations/lti/development/start?"
            f"{instructor_launch_query}"
        ),
        chooser_url=(
            f"{lti_origin}/integrations/lti/development?"
            f"registration_id={registration.id}"
        ),
    )


def bootstrap_canvas_simulator(
    db: Session, *, lti_base_url: str, canvas_base_url: str
) -> tuple[int, list[SimulatorBootstrapResult]]:
    if not canvas_simulator_enabled():
        raise PermissionError("canvas simulator is unavailable")
    lti_origin = _loopback_origin(lti_base_url)
    canvas_origin = _loopback_origin(canvas_base_url)
    organization = _upsert_organization(db)
    learner = _upsert_learner(db, organization)
    instructor = _upsert_instructor(db, organization)
    results = []
    for fixture in SIMULATOR_COURSES:
        course = _upsert_course(
            db,
            organization=organization,
            learner=learner,
            instructor=instructor,
            fixture=fixture,
            canvas_origin=canvas_origin,
        )
        _upsert_synthetic_teacher_review(db, course=course, fixture=fixture)
        _upsert_synthetic_learning_gap(
            db,
            organization=organization,
            course=course,
            learner=learner,
        )
        results.append(
            _upsert_registration(
                db,
                organization=organization,
                learner=learner,
                instructor=instructor,
                course=course,
                fixture_id=fixture.fixture_id,
                lti_origin=lti_origin,
            )
        )
    db.flush()
    return organization.id, results


def simulator_launch(
    db: Session,
    *,
    fixture_id: str,
    lti_base_url: str,
    actor: Literal["learner", "instructor"] = "learner",
) -> SimulatorLaunchResult | None:
    actor_contract = {
        "learner": (SIMULATOR_LEARNER_EMAIL, "student"),
        "instructor": (SIMULATOR_INSTRUCTOR_EMAIL, "instructor"),
    }
    if (
        not canvas_simulator_enabled()
        or fixture_id not in _COURSES_BY_ID
        or actor not in actor_contract
    ):
        return None
    lti_origin = _loopback_origin(lti_base_url)
    issuer = f"{lti_origin}/integrations/lti/development/platform/{fixture_id}"
    registration = (
        db.query(LtiRegistration)
        .filter(
            LtiRegistration.issuer == issuer,
            LtiRegistration.client_id == f"{LOCAL_CLIENT_ID}-{fixture_id}",
            LtiRegistration.deployment_id == f"{LOCAL_DEPLOYMENT_ID}-{fixture_id}",
            LtiRegistration.is_active.is_(True),
            LtiRegistration.is_development.is_(True),
        )
        .first()
    )
    if registration is None:
        return None
    context = (
        db.query(LtiContextBinding)
        .filter(LtiContextBinding.registration_id == registration.id)
        .first()
    )
    actor_email, expected_role = actor_contract[actor]
    subject = (
        db.query(LtiSubjectBinding)
        .join(User, User.id == LtiSubjectBinding.user_id)
        .filter(
            LtiSubjectBinding.registration_id == registration.id,
            User.email == actor_email,
            User.is_active.is_(True),
        )
        .first()
    )
    course = db.get(Course, context.course_id) if context else None
    organization_membership = (
        db.query(OrganizationMembership)
        .filter(
            OrganizationMembership.organization_id == registration.organization_id,
            OrganizationMembership.user_id == subject.user_id,
            OrganizationMembership.role == expected_role,
            OrganizationMembership.is_active.is_(True),
        )
        .first()
        if subject is not None
        else None
    )
    course_membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.organization_id == registration.organization_id,
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == subject.user_id,
            CourseMembership.role == expected_role,
            CourseMembership.is_active.is_(True),
        )
        .first()
        if subject is not None and course is not None
        else None
    )
    expected_subject = f"canvas-simulator-subject-{fixture_id}-{actor}"
    if (
        context is None
        or subject is None
        or course is None
        or organization_membership is None
        or course_membership is None
        or course.organization_id != registration.organization_id
        or course.external_id != f"canvas-simulator:{fixture_id}"
        or context.platform_context_id != f"canvas-simulator-context-{fixture_id}"
        or subject.platform_subject != expected_subject
    ):
        return None
    query = urlencode(
        {
            "registration_id": registration.id,
            "subject": subject.platform_subject,
        }
    )
    return SimulatorLaunchResult(
        fixture_id=fixture_id,
        course_id=course.id,
        registration_id=registration.id,
        actor=actor,
        subject=subject.platform_subject,
        launch_url=(f"{lti_origin}/integrations/lti/development/start?{query}"),
        chooser_url=(
            f"{lti_origin}/integrations/lti/development?"
            f"registration_id={registration.id}"
        ),
    )
