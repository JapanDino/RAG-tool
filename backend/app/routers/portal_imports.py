"""Bounded, observable Canvas import, executed outside the request's DB session."""

import json
import os
from pathlib import PurePosixPath
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import text

from ..db.session import SessionLocal
from ..services import canvas_client
from ..services.canvas_images import (
    download_image,
    extract_canvas_images,
    file_available,
    file_version,
    page_hash,
)
from ..services.lti_security import rate_limit, require_teacher
from . import portal

router = APIRouter(prefix="/portal/imports", tags=["Canvas import"])


def module_available(module):
    return module.get("published") is True and not any(
        module.get(k)
        for k in (
            "unlock_at",
            "prerequisite_module_ids",
            "require_sequential_progress",
            "locked_for_user",
            "assignment_overrides",
        )
    )


def update(db, job_id, status, details, progress=0, total=0):
    db.execute(
        text(
            "UPDATE portal_imports SET status=:status,details=CAST(:details AS jsonb),progress=:progress,total=:total,updated_at=NOW() WHERE id=:id"
        ),
        {
            "id": job_id,
            "status": status,
            "details": json.dumps(details, ensure_ascii=False),
            "progress": progress,
            "total": total,
        },
    )
    db.commit()


def import_course(job_id, session):
    # Hold a dedicated connection for the lifetime of the worker. PostgreSQL
    # releases this lock on process death; a stalled job cannot overlap a retry.
    with SessionLocal() as guard:
        locked = guard.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": -session["course_id"]}
        ).scalar()
        if not locked:
            update(
                guard,
                job_id,
                "failed",
                [
                    {
                        "title": "Импорт курса",
                        "status": "error",
                        "reason": "Другой импорт этого курса ещё работает. Дождитесь его завершения.",
                    }
                ],
            )
            return
        try:
            _import_course(job_id, session)
        finally:
            guard.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": -session["course_id"]}
            )


def _import_course(job_id, session):
    with SessionLocal() as db:
        details = []
        try:
            update(db, job_id, "running", details)
            course = session["canvas_course_id"]
            db.execute(
                text(
                    "UPDATE portal_materials SET published=FALSE,unavailable_reason='Ожидает проверки после импорта' WHERE course_id=:course AND kind IN ('canvas_page','canvas_file')"
                ),
                {"course": session["course_id"]},
            )
            db.commit()
            modules = canvas_client.get_all(
                f"/courses/{course}/modules", {"per_page": 100}
            )
            links, blocked, refs = {}, set(), {}
            for module in modules:
                items = canvas_client.get_all(
                    f"/courses/{course}/modules/{module['id']}/items", {"per_page": 100}
                )
                for item in items:
                    if item.get("type") not in ("Page", "File"):
                        details.append(
                            {
                                "title": item.get("title", "Элемент модуля"),
                                "status": "skipped",
                                "reason": "Поддерживаются страницы и файлы; задания и тесты не импортируются",
                            }
                        )
                        continue
                    key = (
                        item["type"],
                        str(
                            item.get("page_url")
                            if item["type"] == "Page"
                            else item.get("content_id")
                        ),
                    )
                    if (
                        not module_available(module)
                        or item.get("published") is False
                        or item.get("locked_for_user")
                    ):
                        blocked.add(key)
                    links.setdefault(key, (module, item))
                    refs.setdefault(key, []).append(
                        {"module": module["id"], "item": item["id"]}
                    )
            pages = canvas_client.list_pages(course)
            files = canvas_client.get_all(f"/courses/{course}/files", {"per_page": 100})
            resources = [("Page", str(p["url"]), p) for p in pages] + [
                ("File", str(f["id"]), f) for f in files
            ]
            if len(resources) > 300:
                raise ValueError(
                    "Лимит пилота — 300 страниц и файлов на курс. Разделите курс перед импортом."
                )
            for number, (kind, ref, info) in enumerate(resources, 1):
                title = (
                    info.get("title")
                    or info.get("display_name")
                    or info.get("filename")
                    or ref
                )
                try:
                    if (kind, ref) in blocked:
                        raise ValueError(
                            "Закрыт или имеет условия доступа в модуле Canvas"
                        )
                    base = os.environ["CANVAS_URL"].rstrip("/") + f"/courses/{course}"
                    if kind == "Page":
                        full = canvas_client.get_page(course, quote(ref, safe=""))
                        title = full.get("title") or title
                        if full.get("published") is not True or full.get(
                            "locked_for_user"
                        ):
                            raise ValueError("Страница не опубликована или закрыта")
                        body = full.get("body") or ""
                        extracted = extract_canvas_images(body, course)
                        doc_id = portal.save_material(
                            db,
                            session,
                            title,
                            portal._html_to_text(body),
                            kind="canvas_page",
                            source_ref=ref,
                            source_url=base + "/pages/" + quote(ref, safe=""),
                            source_hash=page_hash(body),
                            images=extracted.images,
                        )
                    else:
                        full = canvas_client.get_file(course, int(ref))
                        if full.get("id") != int(ref) or not file_available(full):
                            raise ValueError("Файл скрыт или закрыт")
                        suffix = PurePosixPath(
                            full.get("filename") or title
                        ).suffix.lower()
                        if suffix not in (".pdf", ".docx", ".txt", ".md"):
                            raise ValueError(
                                "Формат не поддерживается: нужны PDF, DOCX, TXT или MD"
                            )
                        if int(full.get("size", 0)) > 10 * 1024 * 1024:
                            raise ValueError("Размер файла превышает 10 МБ")
                        data = download_image(full["url"], max_bytes=10 * 1024 * 1024)
                        extracted = (
                            portal.extract_pdf(data)
                            if suffix == ".pdf"
                            else portal.extract_docx(data)
                            if suffix == ".docx"
                            else None
                        )
                        content = (
                            extracted.text
                            if extracted
                            else portal.extract_text(
                                title,
                                "text/plain",
                                data,
                                max_chars=60001,
                                allow_ocr=False,
                            )
                        )
                        mime = (
                            "application/pdf"
                            if suffix == ".pdf"
                            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            if suffix == ".docx"
                            else "text/plain"
                        )
                        doc_id = portal.save_material(
                            db,
                            session,
                            title,
                            content,
                            kind="canvas_file",
                            source_ref=ref,
                            source_url=base + "/files/" + ref,
                            source_hash=file_version(full),
                            images=extracted.images if extracted else None,
                            page_texts=extracted.page_texts if extracted else None,
                            original=(mime, data),
                        )
                    module, item = links.get((kind, ref), ({}, {}))
                    db.execute(
                        text(
                            "UPDATE portal_materials SET module_name=:name,module_position=:position,item_position=:item,module_refs=CAST(:refs AS jsonb) WHERE document_id=:doc"
                        ),
                        {
                            "doc": doc_id,
                            "name": module.get("name"),
                            "position": module.get("position"),
                            "item": item.get("position"),
                            "refs": json.dumps(refs.get((kind, ref), [])),
                        },
                    )
                    db.commit()
                    details.append(
                        {
                            "title": title,
                            "status": "imported",
                            "document_id": doc_id,
                            "module": module.get("name"),
                        }
                    )
                except (ValueError, HTTPException) as exc:
                    db.rollback()
                    details.append(
                        {
                            "title": title,
                            "status": "skipped",
                            "reason": str(exc.detail)
                            if isinstance(exc, HTTPException)
                            else str(exc),
                        }
                    )
                except Exception:  # noqa: BLE001 - Fail closed at the external service boundary.
                    db.rollback()
                    details.append(
                        {
                            "title": title,
                            "status": "error",
                            "reason": "Ошибка получения или обработки. Проверьте доступ Canvas, формат и доступность модели.",
                        }
                    )
                update(db, job_id, "running", details, number, len(resources))
            update(db, job_id, "complete", details, len(resources), len(resources))
        except Exception:  # noqa: BLE001 - Fail closed at the external service boundary.
            db.rollback()
            details.append(
                {
                    "title": "Импорт курса",
                    "status": "error",
                    "reason": "Импорт прерван. Проверьте Canvas API, права токена и лимит 300 материалов. Можно повторить импорт.",
                }
            )
            update(db, job_id, "failed", details)


@router.post("")
def start(tasks: BackgroundTasks, session: portal.SessionUser, db: portal.Database):
    require_teacher(session)
    rate_limit(session, "import", 5)
    # Course advisory lock prevents two workers from scheduling the same import.
    db.execute(
        text("SELECT pg_advisory_xact_lock(:course)"), {"course": session["course_id"]}
    )
    db.execute(
        text(
            "UPDATE portal_imports SET status='failed' WHERE course_id=:course AND status IN ('queued','running') AND updated_at < NOW()-INTERVAL '15 minutes'"
        ),
        {"course": session["course_id"]},
    )
    existing = db.execute(
        text(
            "SELECT id FROM portal_imports WHERE course_id=:course AND status IN ('queued','running')"
        ),
        {"course": session["course_id"]},
    ).scalar()
    if existing:
        db.commit()
        return {"id": existing}
    job_id = str(uuid4())
    db.execute(
        text("INSERT INTO portal_imports(id,course_id) VALUES (:id,:course)"),
        {"id": job_id, "course": session["course_id"]},
    )
    db.commit()
    tasks.add_task(import_course, job_id, dict(session))
    return {"id": job_id}


@router.get("/latest")
def latest(session: portal.SessionUser, db: portal.Database):
    require_teacher(session)
    result = (
        db.execute(
            text(
                "SELECT id,status,progress,total,details,updated_at FROM portal_imports WHERE course_id=:course ORDER BY updated_at DESC LIMIT 1"
            ),
            {"course": session["course_id"]},
        )
        .mappings()
        .first()
    )
    if result and result["status"] in ("queued", "running"):
        from datetime import datetime, timezone

        if (datetime.now(timezone.utc) - result["updated_at"]).total_seconds() > 900:
            db.execute(
                text("UPDATE portal_imports SET status='failed' WHERE id=:id"),
                {"id": result["id"]},
            )
            db.commit()
            return {**dict(result), "status": "failed"}
    return dict(result) if result else None
