import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    AuditRun,
    Chunk,
    Course,
    CourseMembership,
    CourseModule,
    Dataset,
    Document,
    Job,
    JobStatus,
    JobType,
)
from ..schemas.canvas_changes import CanvasChangeSetOut
from ..schemas.course_audit import (
    CourseCreate,
    CourseDetailOut,
    CourseDocumentOut,
    CourseModuleCreate,
    CourseModuleOut,
    CourseOut,
    CourseUpdate,
    DemoCourseOut,
)
from ..schemas.ml_feedback import MlFeedbackSummaryOut
from ..services.authorization import (
    MANAGE_ROLES,
    Principal,
    accessible_courses,
    course_roles,
    default_manageable_organization,
    get_current_principal,
    require_course_route_access,
    require_organization_role,
)
from ..services.canvas_change_set import (
    build_canvas_change_set,
    canvas_change_set_markdown,
)
from ..services.course_audit import CourseAuditService
from ..services.course_import import persist_upload, read_validated_upload
from ..services.ml_feedback_export import build_ml_feedback_rows, ml_feedback_summary
from ..tasks.queue import enqueue_or_mark

router = APIRouter(
    prefix="/courses",
    tags=["courses"],
    dependencies=[Depends(require_course_route_access)],
)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/app/uploads")
MAX_COURSE_DOCUMENTS = int(os.getenv("MAX_COURSE_DOCUMENTS", "100"))
DEMO_EXTERNAL_ID = "builtin:course-copilot-v1"


def _course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "course not found")
    return course


def _resolve_organization_id(
    db: Session,
    principal: Principal,
    requested_id: int | None,
) -> int | None:
    if principal.bypass:
        return requested_id
    organization_id = requested_id or default_manageable_organization(db, principal)
    require_organization_role(db, principal, organization_id, MANAGE_ROLES)
    return organization_id


def _ensure_creator_membership(
    db: Session,
    principal: Principal,
    course: Course,
) -> None:
    if principal.bypass or principal.user_id is None or course.organization_id is None:
        return
    membership = (
        db.query(CourseMembership)
        .filter(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == principal.user_id,
        )
        .first()
    )
    if membership is None:
        db.add(
            CourseMembership(
                organization_id=course.organization_id,
                course_id=course.id,
                user_id=principal.user_id,
                role="instructor",
                is_active=True,
            )
        )
    else:
        membership.organization_id = course.organization_id
        membership.is_active = True


@router.get("", response_model=list[CourseOut])
def list_courses(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    visible = []
    for course in accessible_courses(db, principal):
        payload = CourseOut.model_validate(course)
        if not principal.bypass and course_roles(db, principal, course) <= {"student"}:
            payload = payload.model_copy(
                update={"source_url": None, "source_metadata": {}}
            )
        visible.append(payload)
    return visible


@router.post("", response_model=CourseDetailOut, status_code=201)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    organization_id = _resolve_organization_id(db, principal, payload.organization_id)
    if payload.external_id:
        existing_query = db.query(Course).filter(
            Course.source_type == payload.source_type,
            Course.external_id == payload.external_id,
        )
        if not principal.bypass:
            existing_query = existing_query.filter(
                Course.organization_id == organization_id
            )
        existing = existing_query.first()
        if existing:
            _ensure_creator_membership(db, principal, existing)
            db.commit()
            modules = (
                db.query(CourseModule)
                .filter(CourseModule.course_id == existing.id)
                .order_by(CourseModule.position, CourseModule.id)
                .all()
            )
            return CourseDetailOut.model_validate(existing).model_copy(
                update={
                    "modules": [
                        CourseModuleOut.model_validate(module) for module in modules
                    ]
                }
            )

    if payload.dataset_id is not None:
        dataset = db.get(Dataset, payload.dataset_id)
        if dataset is None:
            raise HTTPException(404, "dataset not found")
        if db.query(Course).filter(Course.dataset_id == dataset.id).first():
            raise HTTPException(409, "dataset is already assigned to a course")
    else:
        dataset = Dataset(name=f"course:{payload.title}:{uuid.uuid4().hex[:8]}")
        db.add(dataset)
        db.flush()

    course = Course(
        organization_id=organization_id,
        dataset_id=dataset.id,
        external_id=payload.external_id,
        title=payload.title,
        description=payload.description,
        source_type=payload.source_type,
        source_url=payload.source_url,
        source_metadata=payload.source_metadata,
    )
    db.add(course)
    db.flush()
    _ensure_creator_membership(db, principal, course)

    modules = []
    for item in payload.modules:
        module = CourseModule(
            course_id=course.id,
            external_id=item.external_id,
            title=item.title,
            description=item.description,
            position=item.position,
            source_url=item.source_url,
            meta=item.metadata,
        )
        db.add(module)
        modules.append(module)

    db.commit()
    db.refresh(course)
    for module in modules:
        db.refresh(module)
    return CourseDetailOut.model_validate(course).model_copy(
        update={
            "modules": [CourseModuleOut.model_validate(module) for module in modules]
        }
    )


@router.post("/demo", response_model=DemoCourseOut, status_code=201)
def create_demo_course(
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    default_enabled = "0" if app_env == "production" else "1"
    if os.getenv("ENABLE_DEMO_SEED", default_enabled) in {"0", "false", "False"}:
        raise HTTPException(403, "demo seed is disabled")
    organization_id = _resolve_organization_id(db, principal, None)
    existing_query = db.query(Course).filter(Course.external_id == DEMO_EXTERNAL_ID)
    if not principal.bypass:
        existing_query = existing_query.filter(
            Course.organization_id == organization_id
        )
    existing = existing_query.first()
    if existing is not None:
        _ensure_creator_membership(db, principal, existing)
        db.commit()
        latest = (
            db.query(AuditRun)
            .filter(AuditRun.course_id == existing.id, AuditRun.status == "done")
            .order_by(AuditRun.id.desc())
            .first()
        )
        if latest is not None:
            return DemoCourseOut(
                course_id=existing.id, audit_run_id=latest.id, created=False
            )

    dataset = Dataset(name=f"demo:course-copilot:{uuid.uuid4().hex[:8]}")
    db.add(dataset)
    db.flush()
    course = Course(
        organization_id=organization_id,
        dataset_id=dataset.id,
        external_id=DEMO_EXTERNAL_ID,
        title="Демо: алгоритмы сортировки",
        description="Проблемный учебный модуль для демонстрации Course Auditor и RAG Copilot.",
        source_type="manual",
        source_metadata={"demo": True},
    )
    db.add(course)
    db.flush()
    _ensure_creator_membership(db, principal, course)
    module = CourseModule(
        course_id=course.id,
        external_id="demo-module-1",
        title="Алгоритмы сортировки",
        position=1,
    )
    db.add(module)
    db.flush()
    documents = (
        (
            "Цели модуля",
            "learning_objectives",
            "После модуля студент сможет анализировать временную сложность алгоритмов сортировки.",
        ),
        (
            "Материал о сортировках",
            "lecture_material",
            "Quicksort в среднем работает за O(n log n), но в худшем случае за O(n²). "
            "Mergesort гарантирует O(n log n) и требует дополнительную память. "
            "Алгоритмы сравнивают по времени работы, памяти и устойчивости.",
        ),
        (
            "Контрольный вопрос",
            "quiz",
            "Перечислите алгоритмы сортировки и укажите их временную сложность.",
        ),
    )
    for title, document_type, text in documents:
        document = Document(
            dataset_id=dataset.id,
            course_module_id=module.id,
            title=title,
            source="",
            mime="text/plain",
            status="ready",
            source_metadata={"document_type": document_type, "demo": True},
        )
        db.add(document)
        db.flush()
        db.add(
            Chunk(
                document_id=document.id,
                idx=0,
                text=text,
                meta={"source_start": 0, "source_end": len(text)},
            )
        )
    run = AuditRun(
        course_id=course.id,
        status="queued",
        pipeline_version="course-audit-v1",
        extractor_version="objective-assessment-baseline-v1",
        classifier_version="bloom-keyword-v1",
        embedding_model="hash:v1:1536",
        relation_model="hybrid-baseline-v1",
        config={"min_relation_score": 0.22, "top_k": 5},
        metrics={},
    )
    db.add(run)
    db.commit()
    CourseAuditService(db).run(course.id, run.id)
    return DemoCourseOut(course_id=course.id, audit_run_id=run.id, created=True)


@router.get("/{course_id}", response_model=CourseDetailOut)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    course = _course_or_404(db, course_id)
    if not principal.bypass and course_roles(db, principal, course) <= {"student"}:
        return CourseDetailOut.model_validate(course).model_copy(
            update={"modules": [], "source_url": None, "source_metadata": {}}
        )
    modules = (
        db.query(CourseModule)
        .filter(CourseModule.course_id == course_id)
        .order_by(CourseModule.position, CourseModule.id)
        .all()
    )
    return CourseDetailOut.model_validate(course).model_copy(
        update={
            "modules": [CourseModuleOut.model_validate(module) for module in modules]
        }
    )


@router.get("/{course_id}/canvas-change-set", response_model=CanvasChangeSetOut)
def canvas_change_set(course_id: int, db: Session = Depends(get_db)):
    return build_canvas_change_set(db, _course_or_404(db, course_id))


@router.get("/{course_id}/canvas-change-set/download")
def download_canvas_change_set(
    course_id: int,
    format: str = Query(default="markdown", pattern="^(markdown|json)$"),
    db: Session = Depends(get_db),
):
    change_set = build_canvas_change_set(db, _course_or_404(db, course_id))
    if not change_set.available:
        raise HTTPException(409, change_set.reason)
    if format == "json":
        return Response(
            content=change_set.model_dump_json(indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="canvas-change-set-{course_id}.json"'
            },
        )
    return Response(
        content=canvas_change_set_markdown(change_set),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="canvas-change-set-{course_id}.md"'
        },
    )


@router.get("/{course_id}/ml-feedback", response_model=MlFeedbackSummaryOut)
def course_ml_feedback_summary(course_id: int, db: Session = Depends(get_db)):
    course = _course_or_404(db, course_id)
    rows, warnings = build_ml_feedback_rows(db, course)
    return ml_feedback_summary(course, rows, warnings)


@router.get("/{course_id}/ml-feedback/download")
def download_course_ml_feedback(
    course_id: int,
    include_review_metadata: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    rows, _ = build_ml_feedback_rows(
        db,
        course,
        include_review_metadata=include_review_metadata,
    )
    content = "\n".join(
        json.dumps(item, ensure_ascii=False, separators=(",", ":")) for item in rows
    )
    if content:
        content += "\n"
    return Response(
        content=content,
        media_type="application/x-ndjson; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="course-ml-feedback-{course_id}.jsonl"'
        },
    )


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(course_id: int, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = _course_or_404(db, course_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, key, value)
    db.commit()
    db.refresh(course)
    return course


@router.post("/{course_id}/modules", response_model=CourseModuleOut, status_code=201)
def create_module(
    course_id: int, payload: CourseModuleCreate, db: Session = Depends(get_db)
):
    _course_or_404(db, course_id)
    if payload.external_id:
        existing = (
            db.query(CourseModule)
            .filter(
                CourseModule.course_id == course_id,
                CourseModule.external_id == payload.external_id,
            )
            .first()
        )
        if existing:
            return existing
    module = CourseModule(
        course_id=course_id,
        external_id=payload.external_id,
        title=payload.title,
        description=payload.description,
        position=payload.position,
        source_url=payload.source_url,
        meta=payload.metadata,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


@router.get("/{course_id}/documents", response_model=list[CourseDocumentOut])
def list_course_documents(course_id: int, db: Session = Depends(get_db)):
    course = _course_or_404(db, course_id)
    return (
        db.query(Document)
        .filter(Document.dataset_id == course.dataset_id)
        .order_by(Document.id)
        .all()
    )


@router.post(
    "/{course_id}/documents", response_model=CourseDocumentOut, status_code=201
)
def upload_course_document(
    course_id: int,
    file: UploadFile = File(...),
    module_id: int | None = Form(default=None),
    document_type: str = Form(default="unknown"),
    db: Session = Depends(get_db),
):
    course = _course_or_404(db, course_id)
    if module_id is not None:
        module = db.get(CourseModule, module_id)
        if module is None or module.course_id != course_id:
            raise HTTPException(400, "module does not belong to course")
    document_count = (
        db.query(Document).filter(Document.dataset_id == course.dataset_id).count()
    )
    if document_count >= MAX_COURSE_DOCUMENTS:
        raise HTTPException(409, "course document limit reached")

    filename, content_type, data, digest = read_validated_upload(file)
    duplicate = (
        db.query(Document)
        .filter(
            Document.dataset_id == course.dataset_id, Document.content_hash == digest
        )
        .first()
    )
    if duplicate and duplicate.status != "failed":
        result = CourseDocumentOut.model_validate(duplicate)
        return result.model_copy(update={"duplicate": True})

    file_path, source = persist_upload(data, filename, UPLOAD_DIR)
    if duplicate:
        document = duplicate
        document.course_module_id = module_id
        document.title = filename
        document.source = source
        document.mime = content_type
        document.status = "processing"
        document.source_metadata = {
            "document_type": document_type,
            "original_filename": filename,
        }
    else:
        document = Document(
            dataset_id=course.dataset_id,
            course_module_id=module_id,
            title=filename,
            source=source,
            mime=content_type,
            status="processing",
            content_hash=digest,
            source_metadata={
                "document_type": document_type,
                "original_filename": filename,
            },
        )
        db.add(document)
    db.flush()
    job = Job(
        type=JobType.parse,
        status=JobStatus.queued,
        payload={
            "document_id": document.id,
            "file_path": file_path,
            "filename": filename,
            "content_type": content_type,
        },
    )
    db.add(job)
    db.commit()
    db.refresh(document)
    db.refresh(job)
    enqueue_or_mark(db, job)
    return CourseDocumentOut.model_validate(document).model_copy(
        update={"job_id": job.id}
    )


@router.delete("/{course_id}")
def delete_course(course_id: int, db: Session = Depends(get_db)):
    course = _course_or_404(db, course_id)
    db.delete(course)
    db.commit()
    return {"ok": True}
