from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urlparse

from sqlalchemy.orm import Session

from ..models.models import Course, CourseModule, Document
from ..schemas.course_map import (
    CourseMapCourseOut,
    CourseMapItemOut,
    CourseMapModuleOut,
    CourseMapOut,
)

MAX_MODULES = 100
MAX_ITEMS = 500
_SAFE_REF = re.compile(r"^[A-Za-z0-9:_-]{1,120}$")
_ITEM_TYPES = {
    "page": "page",
    "assignment": "assignment",
    "file": "file",
    "externalurl": "external",
    "externaltool": "external",
    "subheader": "section",
    "header": "section",
    "section": "section",
}
_SENSITIVE_URL_PART = re.compile(
    r"(?:access[_-]?token|auth(?:orization)?|credential|password|passcode|"
    r"secret|signature|(?:^|[_-])sig(?:$|[_-])|api[_-]?key|verifier)",
    re.IGNORECASE,
)


def _bounded_text(value: object, limit: int, fallback: str = "Материал курса") -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return (text or fallback)[:limit]


def _source_ref(value: object, *, prefix: str) -> str:
    raw = str(value or "").strip()
    if _SAFE_REF.fullmatch(raw):
        return f"{prefix}:{raw}"[:160]
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:sha256:{digest}"


def document_source_ref(document: Document) -> str:
    """Return the same opaque reference used for document-backed map items."""

    return _source_ref(document.external_id or document.id, prefix="document")


def _safe_url(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw or len(raw) > 2000:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    if any(_SENSITIVE_URL_PART.search(key) for key, _ in parse_qsl(parsed.query)):
        return None
    if parsed.fragment and _SENSITIVE_URL_PART.search(unquote(parsed.fragment)):
        return None
    return raw


def _origin(value: str | None) -> tuple[str, str, int] | None:
    try:
        parsed = urlparse(value or "")
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError:
        return None
    return parsed.scheme, parsed.hostname.lower().rstrip("."), port


def _parse_time(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    )


def _available(metadata: dict, now: datetime) -> bool:
    if metadata.get("student_visible") is not True:
        return False
    if metadata.get("canvas_published") is False:
        return False
    if metadata.get("locked_for_user") is True or metadata.get("hidden") is True:
        return False
    if str(metadata.get("module_state") or "").strip().lower() in {
        "locked",
        "unpublished",
    }:
        return False
    if metadata.get("module_prerequisite_ids"):
        return False
    if metadata.get("module_require_sequential_progress") is True:
        return False
    unlock_at = _parse_time(metadata.get("unlock_at"))
    lock_at = _parse_time(metadata.get("lock_at"))
    if metadata.get("unlock_at") and unlock_at is None:
        return False
    if metadata.get("lock_at") and lock_at is None:
        return False
    return not (
        (unlock_at is not None and unlock_at > now)
        or (lock_at is not None and lock_at <= now)
    )


def _normalized_type(raw_type: object) -> str:
    return _ITEM_TYPES.get(str(raw_type or "").replace("_", "").lower(), "unsupported")


def _document_type(document: Document) -> str:
    metadata = document.source_metadata or {}
    raw_type = str(metadata.get("document_type") or "").lower()
    if raw_type == "assignment":
        return "assignment"
    if raw_type in {"file", "document"}:
        return "file"
    if raw_type in {"lecture_material", "course_description"}:
        return "page"
    return "unsupported"


def _topology_item(
    raw: dict, now: datetime, *, course_origin: tuple[str, str, int] | None
) -> CourseMapItemOut | None:
    if not isinstance(raw, dict) or not _available(raw, now):
        return None
    item_type = _normalized_type(raw.get("type"))
    destination = _safe_url(
        raw.get("external_url") if item_type == "external" else raw.get("html_url")
    )
    provenance = (
        "canvas"
        if item_type != "external"
        and course_origin is not None
        and _origin(destination) == course_origin
        else "external"
    )
    if item_type == "section":
        destination = None
        provenance = None
    source_value = (
        raw.get("id")
        or raw.get("content_id")
        or raw.get("page_url")
        or f"{raw.get('position')}:{raw.get('title')}"
    )
    try:
        position = max(int(raw.get("position") or 0), 0)
    except (TypeError, ValueError):
        position = 0
    return CourseMapItemOut(
        source_ref=_source_ref(source_value, prefix="canvas:module-item"),
        title=_bounded_text(raw.get("title"), 300),
        item_type=item_type,
        position=position,
        available=True,
        supported=item_type != "unsupported",
        destination_url=destination,
        destination_provenance=provenance if destination else None,
    )


def _document_item(
    document: Document, course: Course, now: datetime
) -> CourseMapItemOut | None:
    metadata = document.source_metadata or {}
    if document.status != "ready" or not _available(metadata, now):
        return None
    item_type = _document_type(document)
    destination = _safe_url(document.source)
    course_origin = _origin(course.source_url)
    provenance = (
        "canvas"
        if course_origin is not None and _origin(destination) == course_origin
        else "external"
    )
    raw_position = (
        metadata.get("canvas_position") or metadata.get("position") or document.id
    )
    try:
        position = max(int(raw_position), 0)
    except (TypeError, ValueError):
        position = document.id
    return CourseMapItemOut(
        source_ref=document_source_ref(document),
        title=_bounded_text(document.title, 300),
        item_type=item_type,
        position=position,
        available=True,
        supported=item_type != "unsupported",
        destination_url=destination,
        destination_provenance=provenance if destination else None,
    )


def build_course_map(
    db: Session, course: Course, *, now: datetime | None = None
) -> CourseMapOut:
    current_time = now or datetime.now(UTC)
    modules = (
        db.query(CourseModule)
        .filter(CourseModule.course_id == course.id)
        .order_by(CourseModule.position, CourseModule.id)
        .all()
    )
    documents = (
        db.query(Document)
        .filter(
            Document.dataset_id == course.dataset_id,
            Document.course_module_id.is_not(None),
        )
        .order_by(Document.id)
        .all()
    )
    documents_by_module: dict[int, list[Document]] = {}
    for document in documents:
        documents_by_module.setdefault(int(document.course_module_id), []).append(
            document
        )

    result_modules: list[CourseMapModuleOut] = []
    item_count = 0
    truncated = len(modules) > MAX_MODULES
    course_origin = _origin(course.source_url)
    for module in modules[:MAX_MODULES]:
        metadata = module.meta or {}
        topology = metadata.get("course_map_items")
        items: list[CourseMapItemOut] = []
        if isinstance(topology, list):
            for raw in topology:
                item = _topology_item(raw, current_time, course_origin=course_origin)
                if item is not None:
                    items.append(item)
        else:
            for document in documents_by_module.get(module.id, []):
                item = _document_item(document, course, current_time)
                if item is not None:
                    items.append(item)
        items.sort(key=lambda item: (item.position, item.source_ref))
        remaining = MAX_ITEMS - item_count
        if remaining <= 0:
            truncated = truncated or bool(items)
            break
        if len(items) > remaining:
            items = items[:remaining]
            truncated = True
        if not items:
            continue
        result_modules.append(
            CourseMapModuleOut(
                id=module.id,
                source_ref=_source_ref(
                    module.external_id or module.id, prefix="module"
                ),
                title=_bounded_text(module.title, 300, "Раздел курса"),
                position=max(int(module.position or 0), 0),
                items=items,
            )
        )
        item_count += len(items)

    summary = (
        _bounded_text(course.description, 1200, "") or None
        if course.source_type == "canvas"
        else None
    )
    course_destination = (
        _safe_url(course.source_url) if course.source_type == "canvas" else None
    )
    return CourseMapOut(
        course=CourseMapCourseOut(
            id=course.id,
            title=_bounded_text(course.title, 300, "Курс"),
            syllabus_summary=summary,
            destination_url=course_destination,
        ),
        modules=result_modules,
        total_items=item_count,
        truncated=truncated,
    )


def resolve_document_course_map_item(
    db: Session,
    course: Course,
    document: Document,
) -> CourseMapItemOut | None:
    """Resolve a currently available document to one unambiguous map destination."""

    if document.dataset_id != course.dataset_id or document.course_module_id is None:
        return None
    course_map = build_course_map(db, course)
    modules = [
        module
        for module in course_map.modules
        if module.id == document.course_module_id
    ]
    if len(modules) != 1:
        return None
    expected_ref = document_source_ref(document)
    matches = [item for item in modules[0].items if item.source_ref == expected_ref]
    if not matches:
        destination = _safe_url(document.source)
        if destination is not None:
            matches = [
                item for item in modules[0].items if item.destination_url == destination
            ]
    if len(matches) != 1:
        return None
    item = matches[0]
    if (
        not item.available
        or item.destination_url is None
        or item.destination_provenance not in {"canvas", "external"}
    ):
        return None
    return item
