from __future__ import annotations

import json as _json
import logging
import os

import requests
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db.session import SessionLocal, get_db
from ..models.models import Chunk, Dataset, Document, KnowledgeNode
from ..services import canvas_client as cc
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.chunking import split_into_chunks
from ..services.embedding import embed_texts
from ..services.embedding_provider import current_embedding_model
from ..services.node_extractor import get_node_extractor
from ..services.text_extract import extract_text as extract_file_text
from ..utils.bloom import LEVEL_ORDER
from ..utils.vector import vector_literal

SUPPORTED_MIME_PREFIXES = (
    "application/pdf",
    "text/",
    "application/msword",
    "application/vnd.openxmlformats",
)
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".doc", ".rtf", ".csv"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
CANVAS_TEXT_MAX_CHARS = int(os.getenv("CANVAS_TEXT_MAX_CHARS", "120000"))
CANVAS_PDF_MAX_PAGES = int(os.getenv("CANVAS_PDF_MAX_PAGES", "25"))
CANVAS_PDF_OCR_MAX_PAGES = int(os.getenv("CANVAS_PDF_OCR_MAX_PAGES", "4"))
CANVAS_ENABLE_FILE_OCR = os.getenv("CANVAS_ENABLE_FILE_OCR", "0").lower() in {"1", "true", "yes"}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/canvas", tags=["canvas"])

BLOOM_LEVELS = LEVEL_ORDER


def _html_to_text(html: str) -> str:
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
        import re

        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()


class IngestRequest(BaseModel):
    course_id: int
    dataset_id: int
    content_types: list[str] = [
        "syllabus",
        "pages",
        "assignments",
        "quizzes",
        "discussions",
        "files",
    ]
    max_nodes_per_doc: int = 30
    min_prob: float = 0.2
    max_files: int = 20


class IngestResponse(BaseModel):
    course_id: int
    documents_ingested: int
    nodes_created: int
    nodes_updated: int
    document_ids: list[int]
    documents: list["ImportedDocumentOut"]
    skipped: list[str]


class ImportedDocumentOut(BaseModel):
    document_id: int
    title: str
    source: str
    source_label: str
    nodes_created: int
    nodes_updated: int


def _check_canvas_configured() -> None:
    if not os.getenv("CANVAS_TOKEN"):
        raise HTTPException(400, "CANVAS_TOKEN не настроен в backend/.env")
    if not os.getenv("CANVAS_URL"):
        raise HTTPException(400, "CANVAS_URL не настроен в backend/.env")


def _sse(event: dict, pad: bool = False) -> str:
    payload = f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"
    if not pad:
        return payload
    # Some proxies/browser paths buffer tiny initial SSE chunks. Padding the first
    # control events helps the client receive them immediately instead of waiting
    # for the first large "progress" event.
    return (":" + (" " * 2048) + "\n\n") + payload


def _canvas_source_key(course_id: int, source_label: str) -> str:
    return f"canvas:course:{course_id}:{source_label}"


def _document_title(source_label: str) -> str:
    return (source_label.split(":", 1)[-1] or source_label)[:300]


def _download_canvas_file(download_url: str, auth_headers: dict[str, str]) -> bytes:
    token = auth_headers.get("Authorization", "")
    if not token or token == "Bearer ":
        raise ValueError("CANVAS_TOKEN пустой — невозможно скачать файл")
    resp = requests.get(download_url, headers=auth_headers, timeout=60, stream=True)
    resp.raise_for_status()
    size_header = resp.headers.get("Content-Length")
    if size_header:
        try:
            declared_size = int(size_header)
        except ValueError:
            declared_size = 0
        if declared_size > MAX_FILE_SIZE:
            raise ValueError(
                f"файл слишком большой: {declared_size / (1024 * 1024):.1f} MB > "
                f"{MAX_FILE_SIZE / (1024 * 1024):.0f} MB"
            )

    data = bytearray()
    for chunk in resp.iter_content(chunk_size=1024 * 1024):
        if not chunk:
            continue
        data.extend(chunk)
        if len(data) > MAX_FILE_SIZE:
            raise ValueError(
                f"файл превысил лимит {MAX_FILE_SIZE / (1024 * 1024):.0f} MB во время скачивания"
            )
    return bytes(data)


def _extract_canvas_file_text(filename: str, content_type: str, data: bytes) -> str:
    return extract_file_text(
        filename,
        content_type,
        data,
        max_chars=CANVAS_TEXT_MAX_CHARS,
        pdf_max_pages=CANVAS_PDF_MAX_PAGES,
        allow_ocr=CANVAS_ENABLE_FILE_OCR,
        ocr_max_pages=CANVAS_PDF_OCR_MAX_PAGES,
    )


def _safe_list_pages(course_id: int) -> list[dict]:
    try:
        return cc.list_pages(course_id)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            logger.info("Canvas course %s has no pages endpoint", course_id)
            return []
        raise


def _ensure_canvas_document_and_chunks(
    raw_text: str,
    course_id: int,
    source_label: str,
    dataset_id: int,
    db: Session,
) -> tuple[Document, list[Chunk]]:
    source_key = _canvas_source_key(course_id, source_label)
    doc = (
        db.query(Document)
        .filter(Document.dataset_id == dataset_id, Document.source == source_key)
        .one_or_none()
    )
    if doc is None:
        doc = Document(
            dataset_id=dataset_id,
            title=_document_title(source_label),
            source=source_key,
            mime="text/plain",
            status="ready",
        )
        db.add(doc)
        db.flush()
    else:
        doc.title = _document_title(source_label)
        doc.mime = "text/plain"
        doc.status = "ready"
        db.execute(text("DELETE FROM chunks WHERE document_id = :did"), {"did": doc.id})
        db.flush()

    parts = split_into_chunks(raw_text, max_chars=1500, overlap_chars=150) or [raw_text[:1500]]
    chunks: list[Chunk] = []
    for idx, part in enumerate(parts):
        chunk = Chunk(
            document_id=doc.id,
            idx=idx,
            text=part,
            meta={"source": "canvas", "course_id": course_id, "canvas_label": source_label},
        )
        db.add(chunk)
        chunks.append(chunk)
    db.flush()
    return doc, chunks


def _pick_chunk_for_node(node: dict, chunks: list[Chunk]) -> Chunk | None:
    if not chunks:
        return None
    ctx = " ".join((node.get("context_snippet") or "").split()).strip()
    ctx_tokens = {tok for tok in ctx.lower().split() if tok}
    best: Chunk | None = None
    best_score = (-1, -1)
    for chunk in chunks:
        chunk_text = " ".join((chunk.text or "").split())
        contains = 1 if ctx and ctx[:80] in chunk_text else 0
        overlap = 0
        if ctx_tokens:
            chunk_tokens = {tok for tok in chunk_text.lower().split() if tok}
            overlap = len(ctx_tokens.intersection(chunk_tokens))
        score = (contains, overlap)
        if score > best_score:
            best = chunk
            best_score = score
    return best or chunks[0]


def _process_document(
    raw_text: str,
    course_id: int,
    source_label: str,
    dataset_id: int,
    max_nodes: int,
    min_prob: float,
    extractor,
    embedding_model: str,
    db: Session,
    skipped: list[str],
) -> ImportedDocumentOut | None:
    raw_text = raw_text.strip()
    if not raw_text:
        skipped.append(f"{source_label}: пустой текст")
        return None

    raw_nodes = extractor.extract(raw_text, max_nodes=max_nodes, min_freq=1)
    if not raw_nodes:
        skipped.append(f"{source_label}: узлы не найдены")
        return None

    doc, chunks = _ensure_canvas_document_and_chunks(raw_text, course_id, source_label, dataset_id, db)
    document_id = doc.id
    source_key = _canvas_source_key(course_id, source_label)

    titles = [n["title"] for n in raw_nodes]
    existing_rows = (
        db.query(KnowledgeNode)
        .filter(
            KnowledgeNode.dataset_id == dataset_id,
            KnowledgeNode.document_id == document_id,
            KnowledgeNode.title.in_(titles),
        )
        .all()
    )
    existing_map: dict[str, KnowledgeNode] = {kn.title: kn for kn in existing_rows}

    stored: list[KnowledgeNode] = []
    nodes_created = 0
    nodes_updated = 0
    seen_titles: set[str] = set()

    for node in raw_nodes:
        title = node["title"]
        ctx = node.get("context_snippet") or raw_text[:600]
        seen_titles.add(title)
        best_chunk = _pick_chunk_for_node(node, chunks)

        cls = classify_bloom_multilabel(
            f"{source_label}\n\n{ctx}".strip(),
            min_prob=min_prob,
            max_levels=2,
        )
        model_info = {
            "extractor": extractor.name,
            "source": {
                "kind": "canvas",
                "course_id": course_id,
                "label": source_label,
                "document_source": source_key,
            },
            "frequency": node.get("frequency"),
            "node_type": node.get("node_type"),
            "rationale": cls.get("rationale"),
        }

        existing = existing_map.get(title)
        if existing:
            existing.document_id = document_id
            existing.chunk_id = best_chunk.id if best_chunk else None
            existing.context_text = ctx
            existing.prob_vector = cls["prob_vector"]
            existing.top_levels = cls["top_levels"]
            existing.embedding_model = embedding_model
            existing.model_info = model_info
            stored.append(existing)
            nodes_updated += 1
        else:
            kn = KnowledgeNode(
                dataset_id=dataset_id,
                document_id=document_id,
                chunk_id=best_chunk.id if best_chunk else None,
                title=title,
                context_text=ctx,
                prob_vector=cls["prob_vector"],
                top_levels=cls["top_levels"],
                embedding_model=embedding_model,
                model_info=model_info,
            )
            db.add(kn)
            stored.append(kn)
            nodes_created += 1

    stale_ids = [kn.id for title, kn in existing_map.items() if title not in seen_titles]
    if stale_ids:
        db.execute(text("DELETE FROM knowledge_nodes WHERE id = ANY(:ids)"), {"ids": stale_ids})

    # flush → get DB-assigned IDs without committing yet
    db.flush()
    for kn in stored:
        db.refresh(kn)

    # Attempt embeddings; failures are logged but never abort the commit —
    # nodes with vec=NULL are saved and can be re-embedded later.
    try:
        chunk_vecs = embed_texts([chunk.text for chunk in chunks], dim=1536)
        for chunk, vec in zip(chunks, chunk_vecs):
            db.execute(
                text(
                    """
                    INSERT INTO embeddings (chunk_id, dim, model, vec)
                    VALUES (:cid, :dim, :model, CAST(:v AS vector))
                    ON CONFLICT (chunk_id)
                    DO UPDATE SET dim = EXCLUDED.dim,
                                  model = EXCLUDED.model,
                                  vec = EXCLUDED.vec
                    """
                ),
                {"cid": chunk.id, "dim": 1536, "model": embedding_model, "v": vector_literal(vec)},
            )
    except Exception as exc:
        logger.warning("Chunk embedding failed for %s: %s", source_label, exc)

    try:
        node_vecs = embed_texts([f"{kn.title}. {kn.context_text}".strip() for kn in stored], dim=1536)
        for kn, vec in zip(stored, node_vecs):
            db.execute(
                text("UPDATE knowledge_nodes SET vec = CAST(:v AS vector) WHERE id = :id"),
                {"v": vector_literal(vec), "id": kn.id},
            )
    except Exception as exc:
        logger.warning("Node embedding failed for %s: %s", source_label, exc)

    # Single commit: nodes + chunk embeddings + node vectors land atomically.
    # If anything above raised outside the try/except the caller's session
    # will roll back the whole document — no partial writes.
    db.commit()

    return ImportedDocumentOut(
        document_id=document_id,
        title=doc.title,
        source=source_key,
        source_label=source_label,
        nodes_created=nodes_created,
        nodes_updated=nodes_updated,
    )


@router.get("/courses")
def list_courses():
    _check_canvas_configured()
    try:
        courses = cc.list_courses()
    except Exception as exc:
        raise HTTPException(502, f"Canvas API error: {exc}")
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
    _check_canvas_configured()
    try:
        all_files = cc.list_files(course_id)
    except Exception as exc:
        raise HTTPException(502, f"Canvas API error: {exc}")
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
    _check_canvas_configured()

    ds = db.get(Dataset, payload.dataset_id)
    if not ds:
        raise HTTPException(404, f"Dataset {payload.dataset_id} не найден")

    extractor = get_node_extractor()
    embedding_model = current_embedding_model()
    documents_ingested = 0
    nodes_created = 0
    nodes_updated = 0
    documents: list[ImportedDocumentOut] = []
    skipped: list[str] = []

    def process(raw_text: str, label: str) -> None:
        nonlocal nodes_created, nodes_updated, documents_ingested
        imported = _process_document(
            raw_text,
            payload.course_id,
            label,
            payload.dataset_id,
            payload.max_nodes_per_doc,
            payload.min_prob,
            extractor,
            embedding_model,
            db,
            skipped,
        )
        if imported and (imported.nodes_created > 0 or imported.nodes_updated > 0):
            documents.append(imported)
            documents_ingested += 1
            nodes_created += imported.nodes_created
            nodes_updated += imported.nodes_updated

    cid = payload.course_id
    ctypes = set(payload.content_types)

    if "syllabus" in ctypes:
        try:
            course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
            body = _html_to_text(course.get("syllabus_body") or "")
            if body:
                process(body, f"syllabus:{cid}")
        except Exception as exc:
            skipped.append(f"syllabus: {exc}")

    if "pages" in ctypes:
        try:
            pages = _safe_list_pages(cid)
            for page in pages:
                try:
                    full = cc.get_page(cid, page["url"])
                    process(_html_to_text(full.get("body") or ""), f"page:{page.get('title', page['url'])}")
                except Exception as exc:
                    skipped.append(f"page {page.get('url')}: {exc}")
        except Exception as exc:
            skipped.append(f"pages list: {exc}")

    if "assignments" in ctypes:
        try:
            assignments = cc.list_assignments(cid)
            for assignment in assignments:
                desc = _html_to_text(assignment.get("description") or "")
                combined = f"{assignment.get('name', '')}\n\n{desc}".strip()
                process(combined, f"assignment:{assignment.get('name', assignment['id'])}")
        except Exception as exc:
            skipped.append(f"assignments: {exc}")

    if "quizzes" in ctypes:
        try:
            quizzes = cc.list_quizzes(cid)
            for quiz in quizzes:
                try:
                    questions = cc.list_quiz_questions(cid, quiz["id"])
                    parts = [quiz.get("title", "")]
                    for question in questions:
                        parts.append(_html_to_text(question.get("question_text") or ""))
                        for answer in question.get("answers") or []:
                            parts.append(_html_to_text(answer.get("text") or answer.get("html") or ""))
                    process("\n".join(p for p in parts if p.strip()), f"quiz:{quiz.get('title', quiz['id'])}")
                except Exception as exc:
                    skipped.append(f"quiz {quiz.get('id')}: {exc}")
        except Exception as exc:
            skipped.append(f"quizzes: {exc}")

    if "discussions" in ctypes:
        try:
            topics = cc.list_discussions(cid)
            for topic in topics:
                msg = _html_to_text(topic.get("message") or "")
                combined = f"{topic.get('title', '')}\n\n{msg}".strip()
                process(combined, f"discussion:{topic.get('title', topic['id'])}")
        except Exception as exc:
            skipped.append(f"discussions: {exc}")

    if "files" in ctypes:
        try:
            all_files = cc.list_files(cid)
            supported = [
                f
                for f in all_files
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
            for file_meta in capped:
                fname = file_meta.get("display_name") or file_meta.get("filename")
                if not fname:
                    fname = f"file_{file_meta['id']}"
                    logger.warning("Canvas file %s has no name/extension — text extraction may fail", file_meta['id'])
                download_url = file_meta.get("url") or ""
                label = f"file:{fname}"
                if not download_url:
                    skipped.append(f"{label}: нет URL для скачивания")
                    continue
                try:
                    file_bytes = _download_canvas_file(download_url, auth_headers)
                    text_content = _extract_canvas_file_text(
                        fname,
                        file_meta.get("content-type") or "",
                        file_bytes,
                    )
                    process(text_content, label)
                except Exception as exc:
                    skipped.append(f"{label}: {exc}")
        except Exception as exc:
            skipped.append(f"files list: {exc}")

    return IngestResponse(
        course_id=cid,
        documents_ingested=documents_ingested,
        nodes_created=nodes_created,
        nodes_updated=nodes_updated,
        document_ids=[doc.document_id for doc in documents],
        documents=documents,
        skipped=skipped,
    )


@router.post("/ingest-stream")
def ingest_course_stream(payload: IngestRequest, db: Session = Depends(get_db)):
    _check_canvas_configured()

    # Validate BEFORE opening the stream so we can return HTTP 404 synchronously.
    # The `db` dependency session is used only for this check and then closed
    # normally by FastAPI — it is NOT passed into the generator.
    ds_obj = db.get(Dataset, payload.dataset_id)
    if not ds_obj:
        raise HTTPException(404, f"Dataset {payload.dataset_id} не найден")

    extractor = get_node_extractor()
    embedding_model = current_embedding_model()

    def generate():
        # Open a dedicated session whose lifetime is tied to the generator,
        # not to FastAPI's dependency teardown (which fires when the Response
        # object is GC-d, potentially racing with ongoing generator commits).
        with SessionLocal() as gen_db:
            documents_ingested = 0
            nodes_created = 0
            nodes_updated = 0
            documents: list[ImportedDocumentOut] = []
            skipped: list[str] = []
            cid = payload.course_id
            ctypes = set(payload.content_types)

            def process(raw_text: str, label: str) -> None:
                nonlocal nodes_created, nodes_updated, documents_ingested
                imported = _process_document(
                    raw_text,
                    payload.course_id,
                    label,
                    payload.dataset_id,
                    payload.max_nodes_per_doc,
                    payload.min_prob,
                    extractor,
                    embedding_model,
                    gen_db,
                    skipped,
                )
                if imported and (imported.nodes_created > 0 or imported.nodes_updated > 0):
                    documents.append(imported)
                    documents_ingested += 1
                    nodes_created += imported.nodes_created
                    nodes_updated += imported.nodes_updated

            try:
                yield _sse({"type": "start", "label": "Подключение к Canvas..."}, pad=True)

                if "syllabus" in ctypes:
                    yield _sse({"type": "stage", "stage": "syllabus", "label": "Силлабус"}, pad=True)
                    try:
                        course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
                        body = _html_to_text(course.get("syllabus_body") or "")
                        if body:
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": "Обрабатываем силлабус...",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            process(body, f"syllabus:{cid}")
                    except Exception as exc:
                        skipped.append(f"syllabus: {exc}")

                if "pages" in ctypes:
                    yield _sse({"type": "stage", "stage": "pages", "label": "Страницы курса"}, pad=True)
                    try:
                        pages = _safe_list_pages(cid)
                        total_pages = len(pages)
                        for i, page in enumerate(pages, 1):
                            page_title = page.get("title") or page["url"]
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": f"Страница {i}/{total_pages}: {page_title}",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            try:
                                full = cc.get_page(cid, page["url"])
                                process(_html_to_text(full.get("body") or ""), f"page:{page_title}")
                            except Exception as exc:
                                skipped.append(f"page {page.get('url')}: {exc}")
                    except Exception as exc:
                        skipped.append(f"pages list: {exc}")

                if "assignments" in ctypes:
                    yield _sse({"type": "stage", "stage": "assignments", "label": "Задания"}, pad=True)
                    try:
                        assignments = cc.list_assignments(cid)
                        total = len(assignments)
                        for i, assignment in enumerate(assignments, 1):
                            name = assignment.get("name", f"#{assignment['id']}")
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": f"Задание {i}/{total}: {name}",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            desc = _html_to_text(assignment.get("description") or "")
                            process(f"{name}\n\n{desc}".strip(), f"assignment:{name}")
                    except Exception as exc:
                        skipped.append(f"assignments: {exc}")

                if "quizzes" in ctypes:
                    yield _sse({"type": "stage", "stage": "quizzes", "label": "Тесты"}, pad=True)
                    try:
                        quizzes = cc.list_quizzes(cid)
                        total = len(quizzes)
                        for i, quiz in enumerate(quizzes, 1):
                            title = quiz.get("title", f"#{quiz['id']}")
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": f"Тест {i}/{total}: {title}",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            try:
                                questions = cc.list_quiz_questions(cid, quiz["id"])
                                parts = [title]
                                for question in questions:
                                    parts.append(_html_to_text(question.get("question_text") or ""))
                                    for answer in question.get("answers") or []:
                                        parts.append(_html_to_text(answer.get("text") or answer.get("html") or ""))
                                process("\n".join(p for p in parts if p.strip()), f"quiz:{title}")
                            except Exception as exc:
                                skipped.append(f"quiz {quiz.get('id')}: {exc}")
                    except Exception as exc:
                        skipped.append(f"quizzes: {exc}")

                if "discussions" in ctypes:
                    yield _sse({"type": "stage", "stage": "discussions", "label": "Обсуждения"}, pad=True)
                    try:
                        topics = cc.list_discussions(cid)
                        total = len(topics)
                        for i, topic in enumerate(topics, 1):
                            title = topic.get("title", f"#{topic['id']}")
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": f"Обсуждение {i}/{total}: {title}",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            msg = _html_to_text(topic.get("message") or "")
                            process(f"{title}\n\n{msg}".strip(), f"discussion:{title}")
                    except Exception as exc:
                        skipped.append(f"discussions: {exc}")

                if "files" in ctypes:
                    yield _sse({"type": "stage", "stage": "files", "label": "Файлы курса"}, pad=True)
                    try:
                        all_files = cc.list_files(cid)
                        supported = [
                            f
                            for f in all_files
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
                        for i, file_meta in enumerate(capped, 1):
                            fname = file_meta.get("display_name") or file_meta.get("filename")
                            if not fname:
                                fname = f"file_{file_meta['id']}"
                                logger.warning(
                                    "Canvas file %s has no name/extension — text extraction may fail",
                                    file_meta["id"],
                                )
                            download_url = file_meta.get("url") or ""
                            label = f"file:{fname}"
                            yield _sse(
                                {
                                    "type": "progress",
                                    "current": documents_ingested + 1,
                                    "label": f"Файл {i}/{total}: {fname}",
                                    "nodes_created": nodes_created,
                                    "nodes_updated": nodes_updated,
                                }
                            )
                            if not download_url:
                                skipped.append(f"{label}: нет URL для скачивания")
                                continue
                            try:
                                file_bytes = _download_canvas_file(download_url, auth_headers)
                                text_content = _extract_canvas_file_text(
                                    fname,
                                    file_meta.get("content-type") or "",
                                    file_bytes,
                                )
                                process(text_content, label)
                            except Exception as exc:
                                skipped.append(f"{label}: {exc}")
                    except Exception as exc:
                        skipped.append(f"files list: {exc}")

                yield _sse(
                    {
                        "type": "done",
                        "result": {
                            "course_id": cid,
                            "documents_ingested": documents_ingested,
                            "nodes_created": nodes_created,
                            "nodes_updated": nodes_updated,
                            "document_ids": [doc.document_id for doc in documents],
                            "documents": [doc.model_dump() for doc in documents],
                            "skipped": skipped,
                        },
                    }
                )
            except Exception as exc:
                logger.exception("ingest-stream fatal error: %s", exc)
                yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
