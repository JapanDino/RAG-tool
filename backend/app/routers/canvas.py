import os
import logging
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
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

    def process_document(text: str, source_label: str) -> None:
        nonlocal nodes_created, nodes_updated
        text = text.strip()
        if not text:
            skipped.append(f"{source_label}: пустой текст")
            return

        raw_nodes = extractor.extract(
            text,
            max_nodes=payload.max_nodes_per_doc,
            min_freq=1,
        )
        if not raw_nodes:
            skipped.append(f"{source_label}: узлы не найдены")
            return

        titles = [n["title"] for n in raw_nodes]
        existing_rows = (
            db.query(KnowledgeNode)
            .filter(
                KnowledgeNode.dataset_id == payload.dataset_id,
                KnowledgeNode.title.in_(titles),
            )
            .all()
        )
        existing_map: dict[str, KnowledgeNode] = {kn.title: kn for kn in existing_rows}

        stored: list[KnowledgeNode] = []
        for node in raw_nodes:
            title = node["title"]
            ctx = node.get("context_snippet") or text[:600]

            # Bloom classification
            cls = classify_bloom_multilabel(ctx, min_prob=payload.min_prob, max_levels=2)
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
                    dataset_id=payload.dataset_id,
                    document_id=payload.document_id,
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

    cid = payload.course_id
    ctypes = set(payload.content_types)

    # ── Syllabus ──
    if "syllabus" in ctypes:
        try:
            course = cc.get_one(f"/courses/{cid}", {"include[]": "syllabus_body"})
            body = _html_to_text(course.get("syllabus_body") or "")
            if body:
                process_document(body, f"syllabus:{cid}")
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"syllabus: {e}")

    # ── Pages ──
    if "pages" in ctypes:
        try:
            pages = cc.list_pages(cid)
            for page in pages:
                try:
                    full = cc.get_page(cid, page["url"])
                    text_body = _html_to_text(full.get("body") or "")
                    label = f"page:{page.get('title', page['url'])}"
                    process_document(text_body, label)
                    documents_ingested += 1
                except Exception as e:
                    skipped.append(f"page {page.get('url')}: {e}")
        except Exception as e:
            skipped.append(f"pages list: {e}")

    # ── Assignments ──
    if "assignments" in ctypes:
        try:
            assignments = cc.list_assignments(cid)
            for a in assignments:
                desc = _html_to_text(a.get("description") or "")
                name = a.get("name", "")
                combined = f"{name}\n\n{desc}".strip()
                label = f"assignment:{a.get('name', a['id'])}"
                process_document(combined, label)
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"assignments: {e}")

    # ── Quizzes ──
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
                            ans_text = ans.get("text") or ans.get("html") or ""
                            parts.append(_html_to_text(ans_text))
                    combined = "\n".join(p for p in parts if p.strip())
                    label = f"quiz:{q.get('title', q['id'])}"
                    process_document(combined, label)
                    documents_ingested += 1
                except Exception as e:
                    skipped.append(f"quiz {q.get('id')}: {e}")
        except Exception as e:
            skipped.append(f"quizzes: {e}")

    # ── Discussions ──
    if "discussions" in ctypes:
        try:
            topics = cc.list_discussions(cid)
            for t in topics:
                msg = _html_to_text(t.get("message") or "")
                title = t.get("title", "")
                combined = f"{title}\n\n{msg}".strip()
                label = f"discussion:{t.get('title', t['id'])}"
                process_document(combined, label)
                documents_ingested += 1
        except Exception as e:
            skipped.append(f"discussions: {e}")

    # ── Files ──
    if "files" in ctypes:
        try:
            all_files = cc.list_files(cid)
            # Filter to supported types only
            supported = [
                f for f in all_files
                if (
                    any(f.get("content-type", "").startswith(p) for p in SUPPORTED_MIME_PREFIXES)
                    or any((f.get("filename") or "").lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
                )
                and (f.get("size") or 0) <= MAX_FILE_SIZE
            ]
            # Apply cap
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
                content_type = f.get("content-type") or ""
                label = f"file:{fname}"
                if not download_url:
                    skipped.append(f"{label}: нет URL для скачивания")
                    continue
                try:
                    resp = requests.get(download_url, headers=auth_headers, timeout=60)
                    resp.raise_for_status()
                    file_bytes = resp.content
                    text_content = extract_file_text(fname, content_type, file_bytes)
                    text_content = text_content.strip()
                    if not text_content:
                        skipped.append(f"{label}: пустой текст после извлечения")
                        continue
                    process_document(text_content, label)
                    documents_ingested += 1
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
