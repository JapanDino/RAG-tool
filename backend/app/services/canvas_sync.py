from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol
from urllib.parse import urlparse

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..models.models import (
    CanvasOAuthConnection,
    Course,
    CourseMembership,
    LtiContextBinding,
)
from .authorization import Principal, development_auth_available

CANVAS_READ_SCOPES = (
    "url:GET|/api/v1/courses/:id",
    "url:GET|/api/v1/courses/:course_id/assignments",
    "url:GET|/api/v1/courses/:course_id/modules",
    "url:GET|/api/v1/courses/:course_id/pages",
)

CANVAS_SYNC_EXCLUDED_DATA = (
    "rosters",
    "users",
    "submissions",
    "grades",
    "student_activity",
    "canvas_writes",
)

CANVAS_MANIFEST_GROUP_KINDS = ("modules", "pages", "assignments")
CANVAS_MANIFEST_PREVIEW_LIMIT = 5
CANVAS_MANIFEST_DEVELOPMENT_SAMPLE_LIMIT = 3
CANVAS_MANIFEST_COLLECTION_LIMIT = 500
CANVAS_MANIFEST_PAGE_LIMIT = 10
CANVAS_MANIFEST_TITLE_LIMIT = 200
CANVAS_MANIFEST_REFERENCE_LIMIT = 100


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class CanvasReadUnavailable(RuntimeError):
    """A stable, content-free signal that an approved Canvas read failed."""


@dataclass(frozen=True)
class CanvasManifestItem:
    source_ref: str
    title: str
    published: bool | None


@dataclass(frozen=True)
class CanvasManifestGroup:
    kind: Literal["modules", "pages", "assignments"]
    total: int
    items: tuple[CanvasManifestItem, ...]
    read_truncated: bool = False


@dataclass(frozen=True)
class CanvasCourseManifest:
    course_title: str
    captured_at: datetime
    provenance_kind: Literal["synthetic_development", "test_fixture"]
    canvas_contacted: bool
    groups: tuple[CanvasManifestGroup, ...]


class CanvasReadConnection(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def granted_scopes(self) -> frozenset[str]: ...

    def read_course_manifest(
        self, *, canvas_origin: str, canvas_course_id: str
    ) -> CanvasCourseManifest: ...


class CanvasConnectionProvider(Protocol):
    def connection_for(
        self, *, registration_id: int, user_id: int
    ) -> CanvasReadConnection | None: ...


class UnavailableCanvasConnectionProvider:
    """Production-safe default until encrypted OAuth custody is implemented."""

    def connection_for(
        self, *, registration_id: int, user_id: int
    ) -> CanvasReadConnection | None:
        del registration_id, user_id
        return None


class FakeCanvasReadConnection:
    """Deterministic adapter for tests; it contains no credential or HTTP path."""

    def __init__(
        self,
        *,
        expected_origin: str,
        expected_course_id: str,
        manifest: CanvasCourseManifest,
        granted_scopes: frozenset[str] = frozenset(CANVAS_READ_SCOPES),
        failure: bool = False,
    ):
        self.expected_origin = expected_origin
        self.expected_course_id = expected_course_id
        self.manifest = manifest
        self._granted_scopes = granted_scopes
        self.failure = failure
        self.calls: list[tuple[str, str]] = []

    @property
    def mode(self) -> str:
        return "test"

    @property
    def granted_scopes(self) -> frozenset[str]:
        return self._granted_scopes

    def read_course_manifest(
        self, *, canvas_origin: str, canvas_course_id: str
    ) -> CanvasCourseManifest:
        if (
            canvas_origin != self.expected_origin
            or canvas_course_id != self.expected_course_id
        ):
            raise CanvasReadUnavailable("fake connection target is outside its grant")
        self.calls.append((canvas_origin, canvas_course_id))
        if self.failure:
            raise CanvasReadUnavailable("fake Canvas source unavailable")
        return self.manifest


class FakeCanvasConnectionProvider:
    """Exact registration/user lookup used only through test dependency overrides."""

    def __init__(self):
        self.connections: dict[tuple[int, int], CanvasReadConnection] = {}
        self.requests: list[tuple[int, int]] = []

    def add(
        self,
        *,
        registration_id: int,
        user_id: int,
        connection: CanvasReadConnection,
    ) -> None:
        self.connections[(registration_id, user_id)] = connection

    def connection_for(
        self, *, registration_id: int, user_id: int
    ) -> CanvasReadConnection | None:
        self.requests.append((registration_id, user_id))
        return self.connections.get((registration_id, user_id))


_unavailable_provider = UnavailableCanvasConnectionProvider()


class SecretReferenceStore(Protocol):
    def contains(self, reference: str) -> bool: ...


class DevelopmentCanvasOAuthReadConnection:
    """A local-only bridge from fake OAuth custody to a synthetic manifest."""

    mode = "fake_development"

    def __init__(
        self,
        *,
        db: Session,
        organization_id: int,
        expected_origin: str,
        granted_scopes: frozenset[str],
        vault_reference: str,
        store: SecretReferenceStore,
    ) -> None:
        self.db = db
        self.organization_id = organization_id
        self.expected_origin = expected_origin
        self._granted_scopes = granted_scopes
        self.vault_reference = vault_reference
        self.store = store

    @property
    def granted_scopes(self) -> frozenset[str]:
        if not self.store.contains(self.vault_reference):
            raise CanvasReadUnavailable("fake credential custody is unavailable")
        return self._granted_scopes

    def read_course_manifest(
        self, *, canvas_origin: str, canvas_course_id: str
    ) -> CanvasCourseManifest:
        if canvas_origin != self.expected_origin or not self.store.contains(
            self.vault_reference
        ):
            raise CanvasReadUnavailable("fake connection target is outside its grant")
        candidates = (
            self.db.query(Course)
            .filter(
                Course.organization_id == self.organization_id,
                Course.source_type == "canvas",
                Course.external_id == canvas_course_id,
            )
            .all()
        )
        courses = [
            course
            for course in candidates
            if canvas_target(course) == (canvas_origin, canvas_course_id)
        ]
        if len(courses) != 1:
            raise CanvasReadUnavailable("fake course target is not exact")
        seed = int(
            hashlib.sha256(
                f"{canvas_origin}|{canvas_course_id}".encode("utf-8")
            ).hexdigest()[:8],
            16,
        )
        totals = {
            "modules": 4 + seed % 5,
            "pages": 9 + (seed // 5) % 12,
            "assignments": 3 + (seed // 17) % 6,
        }
        labels = {
            "modules": "Синтетический модуль",
            "pages": "Синтетическая страница",
            "assignments": "Синтетическое задание",
        }
        groups = tuple(
            CanvasManifestGroup(
                kind=kind,
                total=totals[kind],
                items=tuple(
                    CanvasManifestItem(
                        source_ref=f"{kind}:synthetic:{canvas_course_id}:{position}",
                        title=f"{labels[kind]} {position}",
                        published=(position % 3 != 0),
                    )
                    for position in range(
                        1,
                        min(totals[kind], CANVAS_MANIFEST_DEVELOPMENT_SAMPLE_LIMIT) + 1,
                    )
                ),
            )
            for kind in CANVAS_MANIFEST_GROUP_KINDS
        )
        return CanvasCourseManifest(
            course_title=courses[0].title,
            captured_at=datetime.now(timezone.utc),
            provenance_kind="synthetic_development",
            canvas_contacted=False,
            groups=groups,
        )


class DevelopmentCanvasOAuthConnectionProvider:
    def __init__(self, db: Session, store: SecretReferenceStore) -> None:
        self.db = db
        self.store = store

    def connection_for(
        self, *, registration_id: int, user_id: int
    ) -> CanvasReadConnection | None:
        row = (
            self.db.query(CanvasOAuthConnection)
            .filter(
                CanvasOAuthConnection.registration_id == registration_id,
                CanvasOAuthConnection.user_id == user_id,
                CanvasOAuthConnection.connection_mode == "fake_development",
                CanvasOAuthConnection.revoked_at.is_(None),
            )
            .first()
        )
        if (
            row is None
            or _aware(row.expires_at) <= datetime.now(timezone.utc)
            or not self.store.contains(row.vault_reference)
        ):
            return None
        try:
            granted_scopes = frozenset(row.granted_scopes)
        except (TypeError, ValueError):
            return None
        if granted_scopes != frozenset(CANVAS_READ_SCOPES):
            return None
        return DevelopmentCanvasOAuthReadConnection(
            db=self.db,
            organization_id=row.organization_id,
            expected_origin=row.canvas_api_origin,
            granted_scopes=granted_scopes,
            vault_reference=row.vault_reference,
            store=self.store,
        )


def get_canvas_connection_provider(
    db: Session = Depends(get_db),
) -> CanvasConnectionProvider:
    if not development_auth_available():
        return _unavailable_provider
    from .canvas_oauth import get_canvas_secret_store

    return DevelopmentCanvasOAuthConnectionProvider(db, get_canvas_secret_store())


def canvas_target(course: Course) -> tuple[str, str] | None:
    canvas_course_id = (course.external_id or "").strip()
    if (
        course.source_type != "canvas"
        or not canvas_course_id.isdecimal()
        or int(canvas_course_id) < 1
        or not course.source_url
    ):
        return None

    parsed = urlparse(course.source_url.strip())
    try:
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.path.rstrip("/") != f"/courses/{canvas_course_id}"
    ):
        return None
    hostname = parsed.hostname.lower().rstrip(".")
    if not hostname or hostname == "localhost":
        return None
    origin = f"https://{hostname}"
    if port is not None and port != 443:
        origin = f"{origin}:{port}"
    return origin, canvas_course_id


def _bounded_text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str):
        raise CanvasReadUnavailable("manifest text is invalid")
    if any(not character.isprintable() for character in value):
        raise CanvasReadUnavailable("manifest text is outside its boundary")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise CanvasReadUnavailable("manifest text is outside its boundary")
    return normalized


def _serialize_manifest(
    connection: CanvasReadConnection, manifest: CanvasCourseManifest
) -> dict:
    mode = getattr(connection, "mode", None)
    expected_provenance = {
        "fake_development": "synthetic_development",
        "test": "test_fixture",
    }.get(mode)
    if (
        not isinstance(manifest, CanvasCourseManifest)
        or expected_provenance is None
        or manifest.provenance_kind != expected_provenance
        or manifest.canvas_contacted is not False
        or not isinstance(manifest.groups, tuple)
        or len(manifest.groups) != len(CANVAS_MANIFEST_GROUP_KINDS)
    ):
        raise CanvasReadUnavailable("manifest provenance or groups are invalid")

    captured_at = manifest.captured_at
    if not isinstance(captured_at, datetime):
        raise CanvasReadUnavailable("manifest capture time is invalid")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise CanvasReadUnavailable("manifest capture time is not timezone-aware")
    captured_at = captured_at.astimezone(timezone.utc)

    seen_references: set[str] = set()
    serialized_groups: list[dict] = []
    for expected_kind, group in zip(CANVAS_MANIFEST_GROUP_KINDS, manifest.groups):
        if (
            not isinstance(group, CanvasManifestGroup)
            or group.kind != expected_kind
            or not isinstance(group.items, tuple)
            or isinstance(group.total, bool)
            or not isinstance(group.total, int)
            or group.total < 0
            or group.total > CANVAS_MANIFEST_COLLECTION_LIMIT
            or not isinstance(group.read_truncated, bool)
            or (
                group.read_truncated and group.total != CANVAS_MANIFEST_COLLECTION_LIMIT
            )
            or len(group.items) > CANVAS_MANIFEST_PREVIEW_LIMIT
            or len(group.items) > group.total
        ):
            raise CanvasReadUnavailable("manifest group is outside its boundary")
        items: list[dict] = []
        for item in group.items:
            if not isinstance(item, CanvasManifestItem):
                raise CanvasReadUnavailable("manifest item is invalid")
            source_ref = _bounded_text(
                item.source_ref, maximum=CANVAS_MANIFEST_REFERENCE_LIMIT
            )
            if (
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", source_ref)
                or source_ref in seen_references
                or (item.published is not None and not isinstance(item.published, bool))
            ):
                raise CanvasReadUnavailable("manifest item is invalid")
            seen_references.add(source_ref)
            items.append(
                {
                    "source_ref": source_ref,
                    "title": _bounded_text(
                        item.title, maximum=CANVAS_MANIFEST_TITLE_LIMIT
                    ),
                    "published": item.published,
                }
            )
        serialized_groups.append(
            {
                "kind": group.kind,
                "total": group.total,
                "returned": len(items),
                "preview_truncated": group.total > len(items),
                "read_truncated": group.read_truncated,
                "items": items,
            }
        )

    if manifest.provenance_kind == "synthetic_development":
        provenance = {
            "kind": "synthetic_development",
            "canvas_contacted": False,
            "generator_version": "canvas-manifest-v1",
        }
    else:
        provenance = {
            "kind": "test_fixture",
            "canvas_contacted": False,
            "fixture_version": "canvas-manifest-fixture-v1",
        }
    return {
        "course_title": _bounded_text(manifest.course_title, maximum=500),
        "captured_at": captured_at,
        "provenance": provenance,
        "limits": {
            "source_pages_per_collection": CANVAS_MANIFEST_PAGE_LIMIT,
            "objects_per_collection": CANVAS_MANIFEST_COLLECTION_LIMIT,
            "preview_items_per_group": CANVAS_MANIFEST_PREVIEW_LIMIT,
            "title_characters": CANVAS_MANIFEST_TITLE_LIMIT,
        },
        "groups": serialized_groups,
    }


def _base_preview(course: Course) -> dict:
    return {
        "schema_version": 2,
        "read_only": True,
        "course_id": course.id,
        "course_title": course.title,
        "required_scopes": list(CANVAS_READ_SCOPES),
        "missing_scopes": [],
        "excluded_data": list(CANVAS_SYNC_EXCLUDED_DATA),
        "manifest": None,
    }


def build_canvas_sync_preview(
    db: Session,
    *,
    course_id: int,
    principal: Principal,
    provider: CanvasConnectionProvider,
) -> dict:
    if (
        principal.auth_mode != "lti_session"
        or principal.user_id is None
        or principal.registration_id is None
        or principal.course_scope_id != course_id
    ):
        raise HTTPException(404, "resource not found")

    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "resource not found")
    instructor = (
        db.query(CourseMembership.id)
        .filter(
            CourseMembership.course_id == course.id,
            CourseMembership.user_id == principal.user_id,
            CourseMembership.role == "instructor",
            CourseMembership.is_active.is_(True),
        )
        .first()
    )
    binding = (
        db.query(LtiContextBinding.id)
        .filter(
            LtiContextBinding.registration_id == principal.registration_id,
            LtiContextBinding.course_id == course.id,
        )
        .first()
    )
    if instructor is None or binding is None:
        raise HTTPException(404, "resource not found")

    response = _base_preview(course)
    target = canvas_target(course)
    if target is None:
        return {
            **response,
            "state": "course_source_unverified",
            "boundary": None,
        }

    canvas_origin, canvas_course_id = target
    boundary = {
        "selection": "lti_current_course",
        "canvas_origin": canvas_origin,
        "canvas_course_id": canvas_course_id,
        "exact_context_binding": True,
    }
    try:
        connection = provider.connection_for(
            registration_id=principal.registration_id,
            user_id=principal.user_id,
        )
    except CanvasReadUnavailable:
        return {
            **response,
            "state": "source_unavailable",
            "boundary": boundary,
        }
    if connection is None:
        return {
            **response,
            "state": "oauth_required",
            "boundary": boundary,
        }

    try:
        granted_scopes = frozenset(connection.granted_scopes)
        missing_scopes = sorted(set(CANVAS_READ_SCOPES) - granted_scopes)
    except (CanvasReadUnavailable, TypeError, ValueError):
        return {
            **response,
            "state": "source_unavailable",
            "boundary": boundary,
        }
    if missing_scopes or granted_scopes != frozenset(CANVAS_READ_SCOPES):
        return {
            **response,
            "state": "scope_mismatch",
            "boundary": boundary,
            "missing_scopes": missing_scopes,
        }

    try:
        manifest = connection.read_course_manifest(
            canvas_origin=canvas_origin,
            canvas_course_id=canvas_course_id,
        )
        serialized_manifest = _serialize_manifest(connection, manifest)
    except CanvasReadUnavailable:
        return {
            **response,
            "state": "source_unavailable",
            "boundary": boundary,
        }

    return {
        **response,
        "state": "ready",
        "boundary": boundary,
        "manifest": serialized_manifest,
    }
