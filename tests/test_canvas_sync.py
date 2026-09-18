from dataclasses import replace
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.models import (
    Course,
    CourseMembership,
    Dataset,
    LtiContextBinding,
    LtiRegistration,
    Organization,
    User,
)
from backend.app.services.authorization import Principal, get_current_principal
from backend.app.services.canvas_sync import (
    CANVAS_READ_SCOPES,
    CanvasCourseManifest,
    CanvasManifestGroup,
    CanvasManifestItem,
    CanvasReadUnavailable,
    FakeCanvasConnectionProvider,
    FakeCanvasReadConnection,
    get_canvas_connection_provider,
)


def _setup(monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.setenv("APP_ENV", "development")
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as db:
        organization = Organization(
            slug="canvas-sync-school", name="Canvas Sync School", is_active=True
        )
        dataset = Dataset(name="canvas-sync-course")
        user = User(
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            is_active=True,
        )
        db.add_all([organization, dataset, user])
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            external_id="314",
            title="Applied Evidence",
            description="A bound Canvas course.",
            source_type="canvas",
            source_url="https://canvas.school.test/courses/314",
        )
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer="https://canvas.school.test",
            client_id="client-sync",
            deployment_id="deployment-sync",
            authorization_endpoint="https://canvas.school.test/authorize",
            jwks_url="https://canvas.school.test/jwks",
            tool_launch_url="https://tool.school.test/integrations/lti/launch",
            is_active=True,
        )
        db.add_all([course, registration])
        db.flush()
        db.add_all(
            [
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=user.id,
                    role="instructor",
                    is_active=True,
                ),
                LtiContextBinding(
                    registration_id=registration.id,
                    course_id=course.id,
                    platform_context_id="canvas-course-314",
                ),
            ]
        )
        db.commit()
        ids = {
            "course_id": course.id,
            "user_id": user.id,
            "registration_id": registration.id,
        }

    principal = {
        "value": Principal(
            user_id=ids["user_id"],
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            auth_mode="lti_session",
            course_scope_id=ids["course_id"],
            session_id=71,
            registration_id=ids["registration_id"],
        )
    }
    provider = FakeCanvasConnectionProvider()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_principal():
        return principal["value"]

    def override_provider():
        return provider

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_principal] = override_principal
    app.dependency_overrides[get_canvas_connection_provider] = override_provider
    return TestClient(app), Session, engine, ids, principal, provider


def _fixture_manifest() -> CanvasCourseManifest:
    return CanvasCourseManifest(
        course_title="Applied Evidence",
        captured_at=datetime(2026, 7, 18, 9, 30, tzinfo=timezone.utc),
        provenance_kind="test_fixture",
        canvas_contacted=False,
        groups=(
            CanvasManifestGroup(
                kind="modules",
                total=6,
                items=(
                    CanvasManifestItem("module:101", "Evidence map", True),
                    CanvasManifestItem("module:102", "Review workshop", False),
                ),
            ),
            CanvasManifestGroup(
                kind="pages",
                total=14,
                items=(
                    CanvasManifestItem("page:intro", "Course guide", True),
                    CanvasManifestItem("page:rubric", "Evidence rubric", True),
                ),
            ),
            CanvasManifestGroup(
                kind="assignments",
                total=4,
                items=(
                    CanvasManifestItem("assignment:201", "Audit memo", True),
                    CanvasManifestItem("assignment:202", "Peer review", None),
                ),
            ),
        ),
    )


def _connection(
    *,
    scopes=frozenset(CANVAS_READ_SCOPES),
    failure=False,
    manifest: CanvasCourseManifest | None = None,
):
    return FakeCanvasReadConnection(
        expected_origin="https://canvas.school.test",
        expected_course_id="314",
        granted_scopes=scopes,
        failure=failure,
        manifest=manifest or _fixture_manifest(),
    )


def test_bound_lti_instructor_gets_exact_read_only_preview(monkeypatch):
    client, _, engine, ids, _, provider = _setup(monkeypatch)
    connection = _connection()
    provider.add(
        registration_id=ids["registration_id"],
        user_id=ids["user_id"],
        connection=connection,
    )
    try:
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        payload = response.json()
        assert payload == {
            "schema_version": 2,
            "state": "ready",
            "read_only": True,
            "course_id": ids["course_id"],
            "course_title": "Applied Evidence",
            "boundary": {
                "selection": "lti_current_course",
                "canvas_origin": "https://canvas.school.test",
                "canvas_course_id": "314",
                "exact_context_binding": True,
            },
            "required_scopes": list(CANVAS_READ_SCOPES),
            "missing_scopes": [],
            "excluded_data": [
                "rosters",
                "users",
                "submissions",
                "grades",
                "student_activity",
                "canvas_writes",
            ],
            "manifest": {
                "course_title": "Applied Evidence",
                "captured_at": "2026-07-18T09:30:00Z",
                "provenance": {
                    "kind": "test_fixture",
                    "canvas_contacted": False,
                    "fixture_version": "canvas-manifest-fixture-v1",
                },
                "limits": {
                    "source_pages_per_collection": 10,
                    "objects_per_collection": 500,
                    "preview_items_per_group": 5,
                    "title_characters": 200,
                },
                "groups": [
                    {
                        "kind": "modules",
                        "total": 6,
                        "returned": 2,
                        "preview_truncated": True,
                        "read_truncated": False,
                        "items": [
                            {
                                "source_ref": "module:101",
                                "title": "Evidence map",
                                "published": True,
                            },
                            {
                                "source_ref": "module:102",
                                "title": "Review workshop",
                                "published": False,
                            },
                        ],
                    },
                    {
                        "kind": "pages",
                        "total": 14,
                        "returned": 2,
                        "preview_truncated": True,
                        "read_truncated": False,
                        "items": [
                            {
                                "source_ref": "page:intro",
                                "title": "Course guide",
                                "published": True,
                            },
                            {
                                "source_ref": "page:rubric",
                                "title": "Evidence rubric",
                                "published": True,
                            },
                        ],
                    },
                    {
                        "kind": "assignments",
                        "total": 4,
                        "returned": 2,
                        "preview_truncated": True,
                        "read_truncated": False,
                        "items": [
                            {
                                "source_ref": "assignment:201",
                                "title": "Audit memo",
                                "published": True,
                            },
                            {
                                "source_ref": "assignment:202",
                                "title": "Peer review",
                                "published": None,
                            },
                        ],
                    },
                ],
            },
        }
        assert provider.requests == [(ids["registration_id"], ids["user_id"])]
        assert connection.calls == [("https://canvas.school.test", "314")]
        assert "token" not in response.text.lower()
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_absent_connection_and_missing_scopes_make_no_canvas_read(monkeypatch):
    client, _, engine, ids, _, provider = _setup(monkeypatch)
    try:
        absent = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert absent.status_code == 200
        assert absent.json()["state"] == "oauth_required"
        assert absent.json()["manifest"] is None

        missing_scope = CANVAS_READ_SCOPES[-1]
        connection = _connection(
            scopes=frozenset(set(CANVAS_READ_SCOPES) - {missing_scope})
        )
        provider.add(
            registration_id=ids["registration_id"],
            user_id=ids["user_id"],
            connection=connection,
        )
        mismatch = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert mismatch.status_code == 200
        assert mismatch.json()["state"] == "scope_mismatch"
        assert mismatch.json()["missing_scopes"] == [missing_scope]
        assert connection.calls == []

        extra_scope = "url:GET|/api/v1/courses/:course_id/grades"
        extra = _connection(scopes=frozenset((*CANVAS_READ_SCOPES, extra_scope)))
        provider.add(
            registration_id=ids["registration_id"],
            user_id=ids["user_id"],
            connection=extra,
        )
        over_scoped = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert over_scoped.status_code == 200
        assert over_scoped.json()["state"] == "scope_mismatch"
        assert over_scoped.json()["missing_scopes"] == []
        assert extra.calls == []
        assert set(mismatch.json()) == {
            "schema_version",
            "state",
            "read_only",
            "course_id",
            "course_title",
            "boundary",
            "required_scopes",
            "missing_scopes",
            "excluded_data",
            "manifest",
        }
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_production_default_returns_no_manifest_or_connection(monkeypatch):
    client, _, engine, ids, _, _ = _setup(monkeypatch)
    monkeypatch.setenv("AUTH_MODE", "external")
    app.dependency_overrides.pop(get_canvas_connection_provider)
    try:
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.json()["state"] == "oauth_required"
        assert response.json()["manifest"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_provider_failure_is_recoverable_without_changing_target(monkeypatch):
    client, _, engine, ids, _, provider = _setup(monkeypatch)
    connection = _connection(failure=True)
    provider.add(
        registration_id=ids["registration_id"],
        user_id=ids["user_id"],
        connection=connection,
    )
    try:
        failed = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert failed.status_code == 200
        assert failed.json()["state"] == "source_unavailable"
        assert failed.json()["manifest"] is None

        connection.failure = False
        recovered = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "ready"
        assert connection.calls == [
            ("https://canvas.school.test", "314"),
            ("https://canvas.school.test", "314"),
        ]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "case",
    [
        "provenance",
        "canvas_contacted",
        "group_order",
        "duplicate_reference",
        "oversized_title",
        "too_many_items",
        "inconsistent_total",
        "inconsistent_read_truncation",
        "invalid_reference",
        "control_character",
        "c1_control",
        "line_separator",
        "bidi_override",
        "leading_bidi_override",
        "trailing_c1_control",
        "naive_captured_at",
    ],
)
def test_malformed_manifest_fails_closed(monkeypatch, case):
    client, _, engine, ids, _, provider = _setup(monkeypatch)
    manifest = _fixture_manifest()
    groups = list(manifest.groups)
    if case == "provenance":
        manifest = replace(manifest, provenance_kind="synthetic_development")
    elif case == "canvas_contacted":
        manifest = replace(manifest, canvas_contacted=True)
    elif case == "group_order":
        manifest = replace(manifest, groups=tuple(reversed(groups)))
    elif case == "duplicate_reference":
        duplicate = replace(
            groups[1].items[0], source_ref=groups[0].items[0].source_ref
        )
        groups[1] = replace(groups[1], items=(duplicate, *groups[1].items[1:]))
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "oversized_title":
        item = replace(groups[0].items[0], title="x" * 201)
        groups[0] = replace(groups[0], items=(item, *groups[0].items[1:]))
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "too_many_items":
        groups[0] = replace(
            groups[0],
            items=tuple(
                CanvasManifestItem(f"module:{index}", f"Module {index}", True)
                for index in range(6)
            ),
        )
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "inconsistent_total":
        groups[0] = replace(groups[0], total=1)
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "inconsistent_read_truncation":
        groups[0] = replace(groups[0], read_truncated=True)
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "invalid_reference":
        item = replace(groups[0].items[0], source_ref="module/unsafe")
        groups[0] = replace(groups[0], items=(item, *groups[0].items[1:]))
        manifest = replace(manifest, groups=tuple(groups))
    elif case == "naive_captured_at":
        manifest = replace(manifest, captured_at=datetime(2026, 7, 18, 9, 30))
    else:
        unsafe_character = {
            "control_character": "\n",
            "c1_control": "\u0085",
            "line_separator": "\u2028",
            "bidi_override": "\u202e",
            "leading_bidi_override": "\u202e",
            "trailing_c1_control": "\u0085",
        }[case]
        title = f"Unsafe{unsafe_character}module"
        if case == "leading_bidi_override":
            title = f"{unsafe_character}Unsafe module"
        elif case == "trailing_c1_control":
            title = f"Unsafe module{unsafe_character}"
        item = replace(groups[0].items[0], title=title)
        groups[0] = replace(groups[0], items=(item, *groups[0].items[1:]))
        manifest = replace(manifest, groups=tuple(groups))

    connection = _connection(manifest=manifest)
    provider.add(
        registration_id=ids["registration_id"],
        user_id=ids["user_id"],
        connection=connection,
    )
    try:
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.json()["state"] == "source_unavailable"
        assert response.json()["manifest"] is None
        assert connection.calls == [("https://canvas.school.test", "314")]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize("shape", ["object", "group", "items"])
def test_arbitrary_adapter_output_fails_to_bounded_state(monkeypatch, shape):
    client, _, engine, ids, _, provider = _setup(monkeypatch)
    manifest: object = _fixture_manifest()
    if shape == "object":
        manifest = object()
    elif shape == "group":
        manifest = replace(manifest, groups=(object(), *manifest.groups[1:]))
    else:
        broken_group = replace(manifest.groups[0], items=None)
        manifest = replace(manifest, groups=(broken_group, *manifest.groups[1:]))
    connection = _connection(manifest=manifest)
    provider.add(
        registration_id=ids["registration_id"],
        user_id=ids["user_id"],
        connection=connection,
    )
    try:
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.json()["state"] == "source_unavailable"
        assert response.json()["manifest"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_connection_lookup_failure_maps_to_stable_state_and_recovers(monkeypatch):
    client, _, engine, ids, _, provider = _setup(monkeypatch)

    class FailingProvider:
        def connection_for(self, *, registration_id: int, user_id: int):
            del registration_id, user_id
            raise CanvasReadUnavailable("credential store unavailable")

    app.dependency_overrides[get_canvas_connection_provider] = lambda: FailingProvider()
    try:
        failed = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert failed.status_code == 200
        assert failed.headers["cache-control"] == "no-store"
        assert failed.json()["state"] == "source_unavailable"
        assert failed.json()["manifest"] is None

        connection = _connection()
        provider.add(
            registration_id=ids["registration_id"],
            user_id=ids["user_id"],
            connection=connection,
        )
        app.dependency_overrides[get_canvas_connection_provider] = lambda: provider
        recovered = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert recovered.status_code == 200
        assert recovered.json()["state"] == "ready"
        assert connection.calls == [("https://canvas.school.test", "314")]
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.mark.parametrize(
    "scope_metadata",
    [
        pytest.param(CanvasReadUnavailable("scope metadata unavailable"), id="error"),
        pytest.param(None, id="none"),
        pytest.param([[]], id="unhashable"),
    ],
)
def test_scope_metadata_failure_maps_to_stable_state_without_read(
    monkeypatch, scope_metadata
):
    client, _, engine, ids, _, provider = _setup(monkeypatch)

    class FailingScopeConnection:
        @property
        def granted_scopes(self):
            if isinstance(scope_metadata, Exception):
                raise scope_metadata
            return scope_metadata

        def read_course_manifest(self, *, canvas_origin: str, canvas_course_id: str):
            raise AssertionError(
                f"unexpected read for {canvas_origin}/courses/{canvas_course_id}"
            )

    provider.add(
        registration_id=ids["registration_id"],
        user_id=ids["user_id"],
        connection=FailingScopeConnection(),
    )
    try:
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.json()["state"] == "source_unavailable"
        assert response.json()["manifest"] is None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_sync_preview_fails_closed_outside_exact_lti_boundary(monkeypatch):
    client, Session, engine, ids, principal, provider = _setup(monkeypatch)
    try:
        principal["value"] = Principal(
            user_id=ids["user_id"],
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            auth_mode="development",
        )
        local = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert local.status_code == 404

        principal["value"] = Principal(
            user_id=ids["user_id"],
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            auth_mode="lti_session",
            course_scope_id=ids["course_id"] + 1,
            session_id=71,
            registration_id=ids["registration_id"],
        )
        wrong_course = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert wrong_course.status_code == 404

        principal["value"] = Principal(
            user_id=ids["user_id"],
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            auth_mode="lti_session",
            course_scope_id=ids["course_id"],
            session_id=71,
            registration_id=ids["registration_id"],
        )
        with Session() as db:
            db.query(LtiContextBinding).delete()
            db.commit()
        unbound = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert unbound.status_code == 404
        assert provider.requests == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_student_and_different_registration_cannot_open_preview(monkeypatch):
    client, Session, engine, ids, principal, provider = _setup(monkeypatch)
    try:
        with Session() as db:
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.course_id == ids["course_id"])
                .one()
            )
            membership.role = "student"
            db.commit()
        student = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert student.status_code == 404

        with Session() as db:
            membership = (
                db.query(CourseMembership)
                .filter(CourseMembership.course_id == ids["course_id"])
                .one()
            )
            membership.role = "instructor"
            db.commit()
        principal["value"] = Principal(
            user_id=ids["user_id"],
            email="teacher@canvas.test",
            display_name="Canvas Teacher",
            auth_mode="lti_session",
            course_scope_id=ids["course_id"],
            session_id=71,
            registration_id=ids["registration_id"] + 1,
        )
        other_registration = client.get(
            f"/courses/{ids['course_id']}/canvas-sync-preview"
        )
        assert other_registration.status_code == 404
        assert provider.requests == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_unverified_course_source_stops_before_connection_lookup(monkeypatch):
    client, Session, engine, ids, _, provider = _setup(monkeypatch)
    try:
        with Session() as db:
            course = db.get(Course, ids["course_id"])
            course.source_url = "https://canvas.school.test/courses/999"
            db.commit()
        response = client.get(f"/courses/{ids['course_id']}/canvas-sync-preview")
        assert response.status_code == 200
        assert response.json()["state"] == "course_source_unverified"
        assert response.json()["boundary"] is None
        assert provider.requests == []
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_fake_connection_rejects_cross_target_without_reading():
    connection = _connection()
    with pytest.raises(CanvasReadUnavailable):
        connection.read_course_manifest(
            canvas_origin="https://other.school.test",
            canvas_course_id="314",
        )
    with pytest.raises(CanvasReadUnavailable):
        connection.read_course_manifest(
            canvas_origin="https://canvas.school.test",
            canvas_course_id="315",
        )
    assert connection.calls == []
