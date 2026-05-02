import json as _json
import os
import logging
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

from ..db.session import get_db
from ..models.models import Dataset, KnowledgeNode
from ..services import canvas_client as cc
from ..services.node_extractor import get_node_extractor
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.embedding import embed_texts
from ..services.embedding_provider import current_embedding_model
from ..services.text_extract import extract_text as extract_file_text
from ..utils.bloom import LEVEL_ORDER
from ..utils.vector import vector_literal

# File types we can extract text from
SUPPORTED_MIME_PREFIXES = ("application/pdf", "text/", "application/msword",
                           "application/vnd.openxmlformats")
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".csv"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canvas", tags=["canvas"])

BLOOM_LEVELS = LEVEL_ORDER  # ["remember","understand","apply","analyze","evaluate","create"]


# ── HTML stripping ──────────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not html:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        lines = [line.strip() for line in soup.get_text(separator="\n").splitlines()]
        return "\n".join(line for line in lines if line)
    except ImportError:
        # Fallback: naive tag strip without bs4
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


# ── Schemas ─────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    course_id: int
    dataset_id: int
    content_types: list[str] = ["syllabus", "pages", "assignments", "quizzes", "discussions", "files"]
    max_nodes_per_doc: int = 30
    min_prob: float = 0.2
    document_id: Optional[int] = None
    max_files: int = 20  # safety cap — large courses can have hundreds of files


class IngestResponse(BaseModel):
    course_id: int
    documents_ingested: int
    nodes_created: int
    nodes_updated: int
    skipped: list[str]


# ── Helpers ─────────────────────────────────────────────────────────────────

def _check_canvas_configured() -> None:
    if not os.getenv("CANVAS_TOKEN"):
        raise HTTPException(400, "CANVAS_TOKEN не настроен в backend/.env")
    if not os.getenv("CANVAS_URL"):
        raise HTTPException(400, "CANVAS_URL не настроен в backend/.env")


def _sse(event: dict) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"


def _process_document(
    raw_text: str,
    source_label: str,
    dataset_id: int,
    document_id: Optional[int],
    max_nodes: int,
    min_prob: float,
    extractor,
    embedding_model: str,
    db: Session,
    skipped: list[str],
) -> tuple[int, int]:
    """
    Extract knowledge nodes from *raw_text*, classify by Bloom taxonomy,
    embed and upsert into DB.  Returns (nodes_created, nodes_updated).
    Appends to *skipped* on soft errors.
    """
    raw_text = raw_text.strip()
    if not raw_text:
        skipped.append(f"{source_label}: пустой текст")
        return 0, 0

    raw_nodes = extractor.extract(raw_text, max_nodes=max_nodes, min_freq=1)
    if not raw_nodes:
        skipped.append(f"{source_label}: узлы не найдены")
        return 0, 0

    titles = [n["title"] for n in raw_nodes]
    q = db.query(KnowledgeNode).filter(
        KnowledgeNode.dataset_id == dataset_id,
        KnowledgeNode.title.in_(titles),
    )
    if document_id is not None:
        q = q.filter(KnowledgeNode.document_id == document_id)
    existing_map: dict[str, KnowledgeNode] = {kn.title: kn for kn in q.all()}

    stored: list[KnowledgeNode] = []
    nodes_created = 0
    nodes_updated = 0

    for node in raw_nodes:
        title = node["title"]
        ctx = node.get("context_snippet") or raw_text[:600]

        cls = classify_bloom_multilabel(ctx, min_prob=min_prob, max_levels=2)
        prob_vector = cls["prob_vector"]
        top_levels = cls["top_levels"]

        model_info = {
            "extractor": extractor.name,
            "source": "canvas",
            "canvas_label": source_label,
            "frequency": node.get("frequency"),
        }

        existing = existing_map.get(title)
        if existing:
            existing.context_text = ctx
            existing.prob_vector = prob_vector
            existing.top_levels = top_levels
            existing.embedding_model = embedding_model
            existing.model_info = model_info
            stored.append(existing)
            nodes_updated += 1
        else:
            kn = KnowledgeNode(
                dataset_id=dataset_id,
                document_id=document_id,
                title=title,
                context_text=ctx,
                prob_vector=prob_vector,
                top_levels=top_levels,
                embedding_model=embedding_model,
                model_info=model_info,
            )
            db.add(kn)
            stored.append(kn)
            nodes_created += 1

    db.commit()
    for kn in stored:
        db.refresh(kn)

    # Embed and store vectors
    embed_inputs = [f"{kn.title}. {kn.context_text}".strip() for kn in stored]
    try:
        vecs = embed_texts(embed_inputs, dim=1536)
        for kn, vec in zip(stored, vecs):
            db.execute(
                text("UPDATE knowledge_nodes SET vec = CAST(:v AS vector) WHERE id = :id"),
                {"v": vector_literal(vec), "id": kn.id},
            )
        db.commit()
    except Exception as e:
        logger.warning("Embedding failed for %s: %s", source_label, e)

    return nodes_created, nodes_updated


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.get("/courses")
def list_courses():
    """Список активных курсов Canvas для владельца токена."""
    _check_canvas_configured()
    try:
        courses = cc.list_courses()
    except Exception as e:
        raise HTTPException(502, f"Canvas API error: {e}")
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "course_code": c.get("course_code"),
            "start_at": c.get("start_at"),
            "workflow_state": c.get("workflow_state"),
        }
        for c in courses
    ]


@router.get("/courses/{course_id}/files")
def list_course_files(course_id: int):
    """Список файлов курса (только поддерживаемые форматы)."""
    _check_canvas_configured()
    try:
        all_files = cc.list_files(course_id)
    except Exception as e:
        raise HTTPException(502, f"Canvas API error: {e}")
    return [
        {
            "id": f["id"],
            "name": f.get("display_name") or f.get("filename"),
            "content_type": f.get("content-type"),
            "size": f.get("size"),
            "supported": (
                any(f.get("content-type", "").startswith(p) for p in SUPPORTED_MIME_PREFIXES)
                or any((f.get("filename") or "").lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
            ),
        }
        for f in all_files
    ]


@router.post("/ingest", response_model=IngestResponse)
def ingest_course(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Забирает текстовый контент из курса Canvas и прогоняет его
    через пайплайн извлечения узлов + классификации по Блуму.
    Результаты сохраняются в указанный dataset_id.
    """
    _check_canvas_configured()

    ds = db.get(Dataset, payload.dataset_id)
    if not ds:
        raise HTTPException(404, f"Dataset {payload.dataset_id} не найден")

    extractor = get_node_extractor()
    embedding_model = current_embedding_model()
    documents_ingested = 0
    nodes_created = 0
    nodes_updated = 0
    skipped: list[str] = []

    def process(raw_text: str, label: str) -> None:
        nonlocal nodes_created, nodes_updated, documents_ingested
        nc, nu = _process_document(
            raw_text, label, payload.dataset_id, payload.document_id,
            payload.max_nodes_per_doc, payload.min_prob,
            extractor, embedding_model, db, skipped,
        )
        nodes_created += nc
        nodes_updated += nu
        documents_ingested += 1

    cid = payload.course_id
    ctypes = set(payload.content_types)

    if "syllabus" in ctypes:
        try:
            course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
            body = _html_to_text(course.get("syllabus_body") or "")
            if body:
                process(body, f"syllabus:{cid}")
        except Exception as e:
            skipped.append(f"syllabus: {e}")

    if "pages" in ctypes:
        try:
            pages = cc.list_pages(cid)
            for page in pages:
                try:
                    full = cc.get_page(cid, page["url"])
                    process(_html_to_text(full.get("body") or ""), f"page:{page.get('title', page['url'])}")
                except Exception as e:
                    skipped.append(f"page {page.get('url')}: {e}")
        except Exception as e:
            skipped.append(f"pages list: {e}")

    if "assignments" in ctypes:
        try:
            assignments = cc.list_assignments(cid)
            for a in assignments:
                desc = _html_to_text(a.get("description") or "")
                combined = f"{a.get('name', '')}\n\n{desc}".strip()
                process(combined, f"assignment:{a.get('name', a['id'])}")
        except Exception as e:
            skipped.append(f"assignments: {e}")

    if "quizzes" in ctypes:
        try:
            quizzes = cc.list_quizzes(cid)
            for q in quizzes:
                try:
                    questions = cc.list_quiz_questions(cid, q["id"])
                    parts = [q.get("title", "")]
                    for qq in questions:
                        parts.append(_html_to_text(qq.get("question_text") or ""))
                        for ans in qq.get("answers") or []:
                            parts.append(_html_to_text(ans.get("text") or ans.get("html") or ""))
                    combined = "\n".join(p for p in parts if p.strip())
                    process(combined, f"quiz:{q.get('title', q['id'])}")
                except Exception as e:
                    skipped.append(f"quiz {q.get('id')}: {e}")
        except Exception as e:
            skipped.append(f"quizzes: {e}")

    if "discussions" in ctypes:
        try:
            topics = cc.list_discussions(cid)
            for t in topics:
                msg = _html_to_text(t.get("message") or "")
                combined = f"{t.get('title', '')}\n\n{msg}".strip()
                process(combined, f"discussion:{t.get('title', t['id'])}")
        except Exception as e:
            skipped.append(f"discussions: {e}")

    if "files" in ctypes:
        try:
            all_files = cc.list_files(cid)
            supported = [
                f for f in all_files
                if (
                    any(f.get("content-type", "").startswith(p) for p in SUPPORTED_MIME_PREFIXES)
                    or any((f.get("filename") or "").lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
                )
                and (f.get("size") or 0) <= MAX_FILE_SIZE
            ]
            capped = supported[: payload.max_files]
            if len(supported) > payload.max_files:
                skipped.append(
                    f"files: показано {payload.max_files} из {len(supported)} "
                    f"(увеличь max_files чтобы обработать больше)"
                )
            token = os.getenv("CANVAS_TOKEN", "")
            auth_headers = {"Authorization": f"Bearer {token}"}
            for f in capped:
                fname = f.get("display_name") or f.get("filename") or f"file_{f['id']}"
                download_url = f.get("url") or ""
                label = f"file:{fname}"
                if not download_url:
                    skipped.append(f"{label}: нет URL для скачивания")
                    continue
                try:
                    resp = requests.get(download_url, headers=auth_headers, timeout=60)
                    resp.raise_for_status()
                    text_content = extract_file_text(fname, f.get("content-type") or "", resp.content)
                    process(text_content, label)
                except Exception as e:
                    skipped.append(f"{label}: {e}")
        except Exception as e:
            skipped.append(f"files list: {e}")

    return IngestResponse(
        course_id=cid,
        documents_ingested=documents_ingested,
        nodes_created=nodes_created,
        nodes_updated=nodes_updated,
        skipped=skipped,
    )


@router.post("/ingest-stream")
def ingest_course_stream(payload: IngestRequest, db: Session = Depends(get_db)):
    """
    Идентично /ingest, но возвращает Server-Sent Events для отображения
    прогресса в реальном времени. Каждое событие — JSON-объект с полем type:
      • "start"    — начало обработки
      • "stage"    — переход к новому разделу курса
      • "progress" — документ обработан
      • "done"     — всё готово, содержит итоговый result
      • "error"    — фатальная ошибка
    """
    _check_canvas_configured()

    ds_obj = db.get(Dataset, payload.dataset_id)
    if not ds_obj:
        raise HTTPException(404, f"Dataset {payload.dataset_id} не найден")

    extractor = get_node_extractor()
    embedding_model = current_embedding_model()

    def generate():
        documents_ingested = 0
        nodes_created = 0
        nodes_updated = 0
        skipped: list[str] = []
        cid = payload.course_id
        ctypes = set(payload.content_types)

        def process(raw_text: str, label: str) -> None:
            nonlocal nodes_created, nodes_updated, documents_ingested
            nc, nu = _process_document(
                raw_text, label, payload.dataset_id, payload.document_id,
                payload.max_nodes_per_doc, payload.min_prob,
                extractor, embedding_model, db, skipped,
            )
            nodes_created += nc
            nodes_updated += nu
            documents_ingested += 1

        try:
            yield _sse({"type": "start", "label": "Подключение к Canvas..."})

            # ── Syllabus ──
            if "syllabus" in ctypes:
                yield _sse({"type": "stage", "stage": "syllabus", "label": "Силлабус"})
                try:
                    course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
                    body = _html_to_text(course.get("syllabus_body") or "")
                    if body:
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": "Обрабатываем силлабус...",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        process(body, f"syllabus:{cid}")
                        yield _sse({"type": "progress", "current": documents_ingested,
                                    "label": "Силлабус готов",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                except Exception as e:
                    skipped.append(f"syllabus: {e}")

            # ── Pages ──
            if "pages" in ctypes:
                yield _sse({"type": "stage", "stage": "pages", "label": "Страницы курса"})
                try:
                    pages = cc.list_pages(cid)
                    total_pages = len(pages)
                    for i, page in enumerate(pages, 1):
                        page_title = page.get("title") or page["url"]
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": f"Страница {i}/{total_pages}: {page_title}",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        try:
                            full = cc.get_page(cid, page["url"])
                            process(_html_to_text(full.get("body") or ""), f"page:{page_title}")
                        except Exception as e:
                            skipped.append(f"page {page.get('url')}: {e}")
                except Exception as e:
                    skipped.append(f"pages list: {e}")

            # ── Assignments ──
            if "assignments" in ctypes:
                yield _sse({"type": "stage", "stage": "assignments", "label": "Задания"})
                try:
                    assignments = cc.list_assignments(cid)
                    total = len(assignments)
                    for i, a in enumerate(assignments, 1):
                        name = a.get("name", f"#{a['id']}")
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": f"Задание {i}/{total}: {name}",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        desc = _html_to_text(a.get("description") or "")
                        combined = f"{name}\n\n{desc}".strip()
                        process(combined, f"assignment:{name}")
                except Exception as e:
                    skipped.append(f"assignments: {e}")

            # ── Quizzes ──
            if "quizzes" in ctypes:
                yield _sse({"type": "stage", "stage": "quizzes", "label": "Тесты"})
                try:
                    quizzes = cc.list_quizzes(cid)
                    total = len(quizzes)
                    for i, q in enumerate(quizzes, 1):
                        title = q.get("title", f"#{q['id']}")
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": f"Тест {i}/{total}: {title}",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        try:
                            questions = cc.list_quiz_questions(cid, q["id"])
                            parts = [title]
                            for qq in questions:
                                parts.append(_html_to_text(qq.get("question_text") or ""))
                                for ans in qq.get("answers") or []:
                                    parts.append(_html_to_text(ans.get("text") or ans.get("html") or ""))
                            combined = "\n".join(p for p in parts if p.strip())
                            process(combined, f"quiz:{title}")
                        except Exception as e:
                            skipped.append(f"quiz {q.get('id')}: {e}")
                except Exception as e:
                    skipped.append(f"quizzes: {e}")

            # ── Discussions ──
            if "discussions" in ctypes:
                yield _sse({"type": "stage", "stage": "discussions", "label": "Обсуждения"})
                try:
                    topics = cc.list_discussions(cid)
                    total = len(topics)
                    for i, t in enumerate(topics, 1):
                        title = t.get("title", f"#{t['id']}")
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": f"Обсуждение {i}/{total}: {title}",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        msg = _html_to_text(t.get("message") or "")
                        combined = f"{title}\n\n{msg}".strip()
                        process(combined, f"discussion:{title}")
                except Exception as e:
                    skipped.append(f"discussions: {e}")

            # ── Files ──
            if "files" in ctypes:
                yield _sse({"type": "stage", "stage": "files", "label": "Файлы курса"})
                try:
                    all_files = cc.list_files(cid)
                    supported = [
                        f for f in all_files
                        if (
                            any(f.get("content-type", "").startswith(p) for p in SUPPORTED_MIME_PREFIXES)
                            or any((f.get("filename") or "").lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
                        )
                        and (f.get("size") or 0) <= MAX_FILE_SIZE
                    ]
                    capped = supported[: payload.max_files]
                    if len(supported) > payload.max_files:
                        skipped.append(
                            f"files: показано {payload.max_files} из {len(supported)} "
                            f"(увеличь max_files чтобы обработать больше)"
                        )
                    token = os.getenv("CANVAS_TOKEN", "")
                    auth_headers = {"Authorization": f"Bearer {token}"}
                    total = len(capped)
                    for i, f in enumerate(capped, 1):
                        fname = f.get("display_name") or f.get("filename") or f"file_{f['id']}"
                        download_url = f.get("url") or ""
                        label = f"file:{fname}"
                        yield _sse({"type": "progress", "current": documents_ingested + 1,
                                    "label": f"Файл {i}/{total}: {fname}",
                                    "nodes_created": nodes_created, "nodes_updated": nodes_updated})
                        if not download_url:
                            skipped.append(f"{label}: нет URL для скачивания")
                            continue
                        try:
                            resp = requests.get(download_url, headers=auth_headers, timeout=60)
                            resp.raise_for_status()
                            text_content = extract_file_text(fname, f.get("content-type") or "", resp.content)
                            process(text_content, label)
                        except Exception as e:
                            skipped.append(f"{label}: {e}")
                except Exception as e:
                    skipped.append(f"files list: {e}")

            yield _sse({
                "type": "done",
                "result": {
                    "course_id": cid,
                    "documents_ingested": documents_ingested,
                    "nodes_created": nodes_created,
                    "nodes_updated": nodes_updated,
                    "skipped": skipped,
                },
            })

        except Exception as e:
            logger.exception("ingest-stream fatal error: %s", e)
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
