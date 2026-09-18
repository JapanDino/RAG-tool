from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
from sqlalchemy.orm import Session

from ..models.models import (
    CanvasOutcomeAlignment,
    Chunk,
    Course,
    CourseModule,
    Dataset,
    Document,
)
from .chunking import chunk_text_with_offsets

logger = logging.getLogger(__name__)


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def html_to_text(value: str | None) -> str:
    if not value:
        return ""
    parser = _TextExtractor()
    parser.feed(value)
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def validate_canvas_base_url(base_url: str) -> str:
    parsed = urlparse(base_url.strip())
    allow_insecure = os.getenv("ALLOW_INSECURE_CANVAS", "0") in {"1", "true", "True"}
    if parsed.scheme != "https" and not allow_insecure:
        raise ValueError("Canvas base URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Canvas base URL has no hostname")
    hostname = parsed.hostname.lower().rstrip(".")
    allowed_hosts = [
        item.strip().lower()
        for item in os.getenv("CANVAS_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    ]
    if allowed_hosts and not any(
        hostname == item or hostname.endswith(f".{item}") for item in allowed_hosts
    ):
        raise ValueError("Canvas host is not allow-listed")
    if hostname == "localhost":
        raise ValueError("local Canvas hosts are not allowed")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise ValueError("Canvas hostname cannot be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("private Canvas addresses are not allowed")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


class CanvasClient:
    def __init__(
        self, base_url: str, access_token: str, session: requests.Session | None = None
    ):
        self.base_url = validate_canvas_base_url(base_url)
        self.session = session or requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
        )
        self.timeout = float(os.getenv("CANVAS_TIMEOUT_SECONDS", "20"))
        self.max_pages = int(os.getenv("CANVAS_MAX_API_PAGES", "20"))

    def get(self, path: str, params: dict | None = None):
        response = self.session.get(
            urljoin(f"{self.base_url}/", path.lstrip("/")),
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def get_all(self, path: str, params: dict | None = None) -> list[dict]:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        query = {"per_page": 100, **(params or {})}
        rows: list[dict] = []
        for _ in range(self.max_pages):
            response = self.session.get(url, params=query, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
            rows.extend(payload if isinstance(payload, list) else [])
            next_url = response.links.get("next", {}).get("url")
            if not next_url:
                break
            url = next_url
            query = None
        return rows

    def get_all_optional(self, path: str, params: dict | None = None) -> list[dict]:
        try:
            return self.get_all(path, params)
        except requests.RequestException as exc:
            logger.warning(
                "Optional Canvas endpoint unavailable: %s (%s)",
                path,
                type(exc).__name__,
            )
            return []

    def get_all_optional_with_status(
        self, path: str, params: dict | None = None
    ) -> tuple[list[dict], bool]:
        try:
            return self.get_all(path, params), True
        except requests.RequestException as exc:
            logger.warning(
                "Optional Canvas endpoint unavailable: %s (%s)",
                path,
                type(exc).__name__,
            )
            return [], False

    def export_course(self, course_id: int) -> dict:
        prefix = f"/api/v1/courses/{course_id}"
        course = self.get(prefix, {"include[]": "syllabus_body"})
        modules = self.get_all(f"{prefix}/modules", {"include[]": "items"})
        assignments = self.get_all(f"{prefix}/assignments")
        quizzes = self.get_all_optional(f"{prefix}/quizzes")
        outcome_links = self.get_all_optional(
            f"{prefix}/outcome_group_links",
            {"outcome_style": "full", "outcome_group_style": "full"},
        )
        outcome_alignments, outcome_alignments_available = (
            self.get_all_optional_with_status(f"{prefix}/outcome_alignments")
        )

        module_by_content: dict[tuple[str, str], str] = {}
        module_item_by_content: dict[tuple[str, str], dict] = {}
        page_urls: dict[str, dict] = {}
        for module in modules:
            for item in module.get("items") or []:
                item_context = {
                    **item,
                    "module_unlock_at": module.get("unlock_at"),
                    "module_state": module.get("state"),
                    "module_published": module.get("published"),
                    "module_prerequisite_ids": module.get("prerequisite_module_ids")
                    or [],
                    "module_require_sequential_progress": bool(
                        module.get("require_sequential_progress")
                    ),
                }
                item_type = str(item.get("type") or "")
                content_id = item.get("content_id")
                page_url = item.get("page_url")
                if content_id is not None:
                    module_by_content[(item_type.lower(), str(content_id))] = str(
                        module.get("id")
                    )
                    module_item_by_content[(item_type.lower(), str(content_id))] = (
                        item_context
                    )
                if page_url:
                    module_by_content[("page", str(page_url))] = str(module.get("id"))
                    module_item_by_content[("page", str(page_url))] = item_context
                    page_urls[str(page_url)] = item_context

        pages = []
        for page_url, item in list(page_urls.items())[:500]:
            try:
                page = self.get(f"{prefix}/pages/{page_url}")
                pages.append(
                    {
                        **page,
                        "module_external_id": module_by_content.get(("page", page_url)),
                        "item": item,
                    }
                )
            except requests.RequestException as exc:
                logger.warning(
                    "Canvas page unavailable: %s (%s)", page_url, type(exc).__name__
                )

        quiz_questions = {}
        for quiz in quizzes[:200]:
            quiz_questions[str(quiz["id"])] = self.get_all_optional(
                f"{prefix}/quizzes/{quiz['id']}/questions"
            )

        return {
            "course": course,
            "modules": modules,
            "assignments": [
                {
                    **item,
                    "module_external_id": module_by_content.get(
                        ("assignment", str(item.get("id")))
                    ),
                    "module_item": module_item_by_content.get(
                        ("assignment", str(item.get("id")))
                    ),
                }
                for item in assignments
            ],
            "pages": pages,
            "quizzes": [
                {
                    **item,
                    "module_external_id": module_by_content.get(
                        ("quiz", str(item.get("id")))
                    ),
                    "module_item": module_item_by_content.get(
                        ("quiz", str(item.get("id")))
                    ),
                    "questions": quiz_questions.get(str(item.get("id")), []),
                }
                for item in quizzes
            ],
            "outcome_links": outcome_links,
            "outcome_alignments": outcome_alignments,
            "outcome_alignments_available": outcome_alignments_available,
        }


def _canvas_visibility_metadata(
    item: dict,
    module_item: dict | None = None,
) -> dict:
    module_item = module_item or {}
    content_details = module_item.get("content_details") or {}
    published = item.get("published")
    if published is None:
        workflow_state = str(item.get("workflow_state") or "").lower()
        published = workflow_state in {"available", "completed", "published"}
    module_published = module_item.get("module_published")
    item_published = module_item.get("published")
    module_state = str(module_item.get("module_state") or "").strip().lower()
    module_prerequisite_ids = module_item.get("module_prerequisite_ids") or []
    module_require_sequential_progress = bool(
        module_item.get("module_require_sequential_progress")
    )
    locked_for_user = bool(
        item.get("locked_for_user")
        or module_item.get("locked_for_user")
        or content_details.get("locked_for_user")
    )
    unlock_at = (
        item.get("unlock_at")
        or content_details.get("unlock_at")
        or module_item.get("module_unlock_at")
    )
    lock_at = item.get("lock_at") or content_details.get("lock_at")
    student_visible = bool(
        published is True
        and module_published is not False
        and item_published is not False
        and module_state not in {"locked", "unpublished"}
        and not module_prerequisite_ids
        and not module_require_sequential_progress
        and not locked_for_user
    )
    return {
        "student_visible": student_visible,
        "canvas_published": published is True,
        "locked_for_user": locked_for_user,
        "module_state": module_state or None,
        "module_prerequisite_ids": module_prerequisite_ids,
        "module_require_sequential_progress": module_require_sequential_progress,
        "unlock_at": unlock_at,
        "lock_at": lock_at,
    }


def _course_map_module_items(module: dict) -> list[dict]:
    result: list[dict] = []
    for fallback_position, item in enumerate(module.get("items") or [], start=1):
        context = {
            **item,
            "module_unlock_at": module.get("unlock_at"),
            "module_state": module.get("state"),
            "module_published": module.get("published"),
            "module_prerequisite_ids": module.get("prerequisite_module_ids") or [],
            "module_require_sequential_progress": bool(
                module.get("require_sequential_progress")
            ),
        }
        try:
            item_position = max(int(item.get("position") or fallback_position), 0)
        except (TypeError, ValueError):
            item_position = fallback_position
        result.append(
            {
                "id": str(item.get("id") or "")[:120],
                "content_id": str(item.get("content_id") or "")[:120] or None,
                "page_url": str(item.get("page_url") or "")[:200] or None,
                "title": str(item.get("title") or "Материал курса")[:300],
                "type": str(item.get("type") or "Unknown")[:50],
                "position": item_position,
                "html_url": str(item.get("html_url") or "")[:2000] or None,
                "external_url": str(item.get("external_url") or "")[:2000] or None,
                **_canvas_visibility_metadata(context),
            }
        )
    return result[:500]


def _normalized_documents(
    payload: dict, base_url: str, course_external_id: str
) -> list[dict]:
    result = []
    course = payload["course"]
    course_visibility = _canvas_visibility_metadata(course)
    syllabus = html_to_text(
        course.get("syllabus_body") or course.get("public_description")
    )
    if syllabus:
        result.append(
            {
                "external_id": f"canvas:course:{course_external_id}:syllabus",
                "title": f"{course.get('name', 'Course')} — описание",
                "text": syllabus,
                "document_type": "course_description",
                "module_external_id": None,
                "source_url": course.get("html_url")
                or f"{base_url}/courses/{course_external_id}",
                "metadata": course_visibility,
            }
        )
    for link in payload.get("outcome_links") or []:
        outcome = link.get("outcome") or {}
        text = (
            html_to_text(outcome.get("description"))
            or str(outcome.get("title") or "").strip()
        )
        outcome_id = outcome.get("id")
        if text and outcome_id is not None:
            result.append(
                {
                    "external_id": f"canvas:outcome:{outcome_id}",
                    "title": outcome.get("display_name")
                    or outcome.get("title")
                    or "Canvas outcome",
                    "text": text,
                    "document_type": "learning_objectives",
                    "module_external_id": None,
                    "source_url": outcome.get("html_url")
                    or f"{base_url}/courses/{course_external_id}/outcomes",
                    "metadata": {
                        "canvas_outcome_id": str(outcome_id),
                        # Canvas outcome APIs do not provide a reliable learner-visible flag.
                        "student_visible": False,
                    },
                }
            )
    for page in payload.get("pages") or []:
        text = html_to_text(page.get("body"))
        if text:
            result.append(
                {
                    "external_id": f"canvas:page:{page.get('page_id') or page.get('url')}",
                    "title": page.get("title") or "Canvas page",
                    "text": text,
                    "document_type": "lecture_material",
                    "module_external_id": page.get("module_external_id"),
                    "source_url": page.get("html_url")
                    or f"{base_url}/courses/{course_external_id}/pages/{page.get('url')}",
                    "metadata": _canvas_visibility_metadata(page, page.get("item")),
                }
            )
    for assignment in payload.get("assignments") or []:
        text = html_to_text(assignment.get("description"))
        if text:
            result.append(
                {
                    "external_id": f"canvas:assignment:{assignment.get('id')}",
                    "title": assignment.get("name") or "Canvas assignment",
                    "text": text,
                    "document_type": "assignment",
                    "module_external_id": assignment.get("module_external_id"),
                    "source_url": assignment.get("html_url"),
                    "metadata": {
                        "canvas_assignment_id": str(assignment.get("id")),
                        **_canvas_visibility_metadata(
                            assignment, assignment.get("module_item")
                        ),
                    },
                }
            )
    for quiz in payload.get("quizzes") or []:
        question_texts = [
            html_to_text(item.get("question_text"))
            for item in quiz.get("questions") or []
        ]
        text = "\n".join(
            item
            for item in [html_to_text(quiz.get("description")), *question_texts]
            if item
        )
        if text:
            result.append(
                {
                    "external_id": f"canvas:quiz:{quiz.get('id')}",
                    "title": quiz.get("title") or "Canvas quiz",
                    "text": text,
                    "document_type": "quiz",
                    "module_external_id": quiz.get("module_external_id"),
                    "source_url": quiz.get("html_url"),
                    "metadata": _canvas_visibility_metadata(
                        quiz, quiz.get("module_item")
                    ),
                }
            )
    return result


def persist_canvas_course(
    db: Session,
    payload: dict,
    base_url: str,
    organization_id: int | None = None,
) -> dict:
    canvas = payload["course"]
    external_id = str(canvas["id"])
    course_query = db.query(Course).filter(
        Course.source_type == "canvas",
        Course.external_id == external_id,
    )
    if organization_id is not None:
        course_query = course_query.filter(Course.organization_id == organization_id)
    course = course_query.first()
    if course is None:
        organization_suffix = (
            f":org-{organization_id}" if organization_id is not None else ""
        )
        dataset = Dataset(
            name=(
                f"canvas:{urlparse(base_url).hostname}:{external_id}"
                f"{organization_suffix}"
            )
        )
        db.add(dataset)
        db.flush()
        course = Course(
            organization_id=organization_id,
            dataset_id=dataset.id,
            external_id=external_id,
            title=canvas.get("name")
            or canvas.get("course_code")
            or f"Canvas {external_id}",
            description=html_to_text(canvas.get("public_description")),
            source_type="canvas",
            source_url=canvas.get("html_url") or f"{base_url}/courses/{external_id}",
            source_metadata={"canvas_course_code": canvas.get("course_code")},
        )
        db.add(course)
        db.flush()
    else:
        course.title = canvas.get("name") or course.title
        course.source_url = canvas.get("html_url") or course.source_url

    module_map: dict[str, CourseModule] = {}
    imported_module_ids: set[str] = set()
    for position, item in enumerate(payload.get("modules") or [], start=1):
        module_external_id = str(item["id"])
        imported_module_ids.add(module_external_id)
        module = (
            db.query(CourseModule)
            .filter(
                CourseModule.course_id == course.id,
                CourseModule.external_id == module_external_id,
            )
            .first()
        )
        if module is None:
            module = CourseModule(
                course_id=course.id,
                external_id=module_external_id,
                title=item.get("name") or "Module",
            )
            db.add(module)
        module.title = item.get("name") or module.title
        module.position = int(item.get("position") or position)
        module.source_url = (
            f"{base_url}/courses/{external_id}/modules/{module_external_id}"
        )
        module.meta = {
            "workflow_state": item.get("state"),
            "unlock_at": item.get("unlock_at"),
            "course_map_items": _course_map_module_items(item),
        }
        db.flush()
        module_map[module_external_id] = module

    existing_modules = (
        db.query(CourseModule).filter(CourseModule.course_id == course.id).all()
    )
    for module in existing_modules:
        if module.external_id is None or module.external_id in imported_module_ids:
            continue
        module.meta = {
            **(module.meta or {}),
            "course_map_items": [],
            "course_map_removed": True,
        }

    created = updated = 0
    for item in _normalized_documents(payload, base_url, external_id):
        text = item["text"].strip()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = (
            db.query(Document)
            .filter(
                Document.dataset_id == course.dataset_id,
                Document.external_id == item["external_id"],
            )
            .first()
        )
        if document is None:
            document = Document(
                dataset_id=course.dataset_id,
                external_id=item["external_id"],
                title=item["title"],
                source=item["source_url"] or "",
                mime="text/html",
            )
            db.add(document)
            created += 1
        elif document.content_hash == digest:
            expected_metadata = {
                "document_type": item["document_type"],
                "canvas_external_id": item["external_id"],
                **(item.get("metadata") or {}),
            }
            if document.source_metadata != expected_metadata:
                document.source_metadata = expected_metadata
            continue
        else:
            updated += 1
        document.title = item["title"]
        document.source = item["source_url"] or document.source
        document.status = "ready"
        document.content_hash = digest
        document.course_module_id = (
            module_map.get(str(item.get("module_external_id"))).id
            if item.get("module_external_id") in module_map
            else None
        )
        document.source_metadata = {
            "document_type": item["document_type"],
            "canvas_external_id": item["external_id"],
            **(item.get("metadata") or {}),
        }
        db.flush()
        db.query(Chunk).filter(Chunk.document_id == document.id).delete(
            synchronize_session="fetch"
        )
        for index, chunk in enumerate(chunk_text_with_offsets(text)):
            db.add(
                Chunk(
                    document_id=document.id,
                    idx=index,
                    text=chunk["text"],
                    meta={
                        "source_start": chunk["start"],
                        "source_end": chunk["end"],
                        "sentence_start": chunk["sentence_start"],
                        "sentence_end": chunk["sentence_end"],
                    },
                )
            )

    # Versions before 0020 stored every outcome in one document. Remove that
    # aggregate after individual outcome documents have been imported, otherwise
    # the extractor would see the same objective twice on the next audit.
    if payload.get("outcome_links"):
        legacy_outcomes = (
            db.query(Document)
            .filter(
                Document.dataset_id == course.dataset_id,
                Document.external_id == f"canvas:course:{external_id}:outcomes",
            )
            .first()
        )
        if legacy_outcomes is not None:
            db.delete(legacy_outcomes)
    seen_pairs: set[tuple[str, str]] = set()
    for item in payload.get("outcome_alignments") or []:
        outcome_id = item.get("id")
        assignment_id = item.get("assignment_id")
        if outcome_id is None or assignment_id is None:
            continue
        pair = (str(outcome_id), str(assignment_id))
        seen_pairs.add(pair)
        alignment = (
            db.query(CanvasOutcomeAlignment)
            .filter(
                CanvasOutcomeAlignment.course_id == course.id,
                CanvasOutcomeAlignment.outcome_external_id == pair[0],
                CanvasOutcomeAlignment.assignment_external_id == pair[1],
            )
            .first()
        )
        if alignment is None:
            alignment = CanvasOutcomeAlignment(
                course_id=course.id,
                outcome_external_id=pair[0],
                assignment_external_id=pair[1],
            )
            db.add(alignment)
        alignment.title = item.get("title")
        alignment.source_url = item.get("url")
        alignment.submission_types = item.get("submission_types") or []
        alignment.meta = {"assessment_id": item.get("assessment_id")}

    if payload.get("outcome_alignments_available") is True:
        for existing in (
            db.query(CanvasOutcomeAlignment)
            .filter(CanvasOutcomeAlignment.course_id == course.id)
            .all()
        ):
            if (
                existing.outcome_external_id,
                existing.assignment_external_id,
            ) not in seen_pairs:
                db.delete(existing)

    db.commit()
    return {
        "course_id": course.id,
        "dataset_id": course.dataset_id,
        "modules_imported": len(module_map),
        "documents_created": created,
        "documents_updated": updated,
        "explicit_alignments_imported": len(seen_pairs),
        "source_url": course.source_url,
    }
