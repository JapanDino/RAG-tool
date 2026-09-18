"""One-shot PostgreSQL rehearsal for the M05 LTI persistence boundary."""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

from backend.app.models.models import (
    CanvasOAuthAttempt,
    CanvasOAuthConfiguration,
    CanvasOAuthConnection,
    Course,
    CourseMembership,
    Dataset,
    LtiBindingCandidate,
    LtiBindingEvent,
    LtiContextBinding,
    LtiRegistration,
    LtiSubjectBinding,
    Organization,
    OrganizationMembership,
    User,
)
from backend.app.services.canvas_oauth import (
    CanvasOAuthError,
    FakeCanvasCodeExchanger,
    InMemoryDevelopmentSecretStore,
    complete_canvas_oauth_callback,
    start_instructor_canvas_oauth,
)
from backend.app.services.lti_binding import (
    LtiBindingError,
    bind_candidate,
    capture_unbound_candidates,
)
from backend.app.services.product_session import issue_product_session

EXPECTED_MIGRATIONS = {
    "0033_lti_launch_boundary.sql",
    "0034_lti_product_sessions.sql",
    "0035_lti_registration_events.sql",
    "0036_lti_binding_candidates.sql",
    "0037_canvas_oauth_lifecycle.sql",
    "0038_canvas_oauth_instructor_handoff.sql",
}
EXPECTED_CONSTRAINTS = {
    "ux_lti_registrations_platform_deployment",
    "ux_lti_subject_bindings_sub",
    "ux_lti_subject_bindings_user",
    "ux_lti_context_bindings_context",
    "ux_lti_context_bindings_course",
    "ck_lti_product_sessions_role",
    "ck_lti_registration_events_type",
    "ux_lti_binding_candidates_identifier",
    "ck_lti_binding_candidates_type",
    "ck_lti_binding_candidates_status",
    "ck_lti_binding_events_type",
    "ux_canvas_oauth_configurations_registration",
    "ck_canvas_oauth_configurations_version",
    "ux_canvas_oauth_connections_user",
    "ck_canvas_oauth_connections_mode",
    "ck_canvas_oauth_events_type",
    "ck_canvas_oauth_attempts_flow_context",
}
EXPECTED_INDEXES = {
    "ux_lti_product_sessions_active_scope",
    "ix_lti_binding_candidates_expires_at",
    "ix_lti_binding_events_candidate_id",
    "ix_canvas_oauth_attempts_expires_at",
    "ix_canvas_oauth_connections_revoked_at",
    "ix_canvas_oauth_events_registration_id",
    "ix_canvas_oauth_attempts_product_session_id",
    "ix_canvas_oauth_attempts_course_id",
    "ix_canvas_oauth_attempts_flow_kind",
}


def rehearsal_database_url() -> str:
    if os.getenv("M05_REHEARSAL_DISPOSABLE") != "1":
        raise RuntimeError("disposable rehearsal confirmation is required")
    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        raise RuntimeError("DATABASE_URL is required")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("PostgreSQL is required")
    database = url.database or ""
    if not re.search(
        r"(?:^|[_-])(?:rehearsal|test)(?:$|[_-])", database, re.IGNORECASE
    ):
        raise RuntimeError("database name must contain rehearsal or test")
    return raw


def _assert_schema(session_factory) -> dict[str, int]:
    with session_factory() as db:
        migrations = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT filename FROM schema_migrations "
                    "WHERE filename LIKE '003_.sql' OR filename LIKE '003_%'"
                )
            )
        }
        missing_migrations = EXPECTED_MIGRATIONS - migrations
        if missing_migrations:
            raise AssertionError("required LTI migrations are missing")

        constraints = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE connamespace = current_schema()::regnamespace"
                )
            )
        }
        if EXPECTED_CONSTRAINTS - constraints:
            raise AssertionError("required LTI constraints are missing")

        indexes = {
            row[0]
            for row in db.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
                )
            )
        }
        if EXPECTED_INDEXES - indexes:
            raise AssertionError("required LTI indexes are missing")

    return {
        "migrations_checked": len(EXPECTED_MIGRATIONS),
        "constraints_checked": len(EXPECTED_CONSTRAINTS),
        "indexes_checked": len(EXPECTED_INDEXES),
    }


def _seed(session_factory) -> dict[str, object]:
    with session_factory.begin() as db:
        organization = Organization(
            slug="m05-postgres-rehearsal", name="M05 PostgreSQL Rehearsal"
        )
        dataset = Dataset(name="m05-postgres-rehearsal-course")
        actor = User(email="actor@m05-rehearsal.test", display_name="Actor")
        first_target = User(
            email="first-target@m05-rehearsal.test", display_name="First target"
        )
        second_target = User(
            email="second-target@m05-rehearsal.test", display_name="Second target"
        )
        db.add_all([organization, dataset, actor, first_target, second_target])
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            external_id="314",
            title="Rehearsal course",
            source_type="canvas",
            source_url="https://canvas.m05-rehearsal.test/courses/314",
        )
        db.add(course)
        db.flush()
        db.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=actor.id,
                    role="administrator",
                    is_active=True,
                ),
                CourseMembership(
                    organization_id=organization.id,
                    course_id=course.id,
                    user_id=actor.id,
                    role="instructor",
                    is_active=True,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=first_target.id,
                    role="student",
                    is_active=True,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=second_target.id,
                    role="instructor",
                    is_active=True,
                ),
            ]
        )
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer="https://canvas.m05-rehearsal.test",
            client_id="m05-rehearsal-client",
            deployment_id="m05-rehearsal-deployment",
            authorization_endpoint="https://canvas.m05-rehearsal.test/authorize",
            jwks_url="https://canvas.m05-rehearsal.test/jwks",
            tool_launch_url="https://tool.m05-rehearsal.test/launch",
            is_active=True,
            is_development=False,
        )
        db.add(registration)
        db.flush()
        db.add(
            LtiContextBinding(
                registration_id=registration.id,
                course_id=course.id,
                platform_context_id="opaque-rehearsal-context",
            )
        )
        db.add(
            CanvasOAuthConfiguration(
                registration_id=registration.id,
                organization_id=organization.id,
                canvas_api_origin="https://canvas.m05-rehearsal.test",
                oauth_client_id="m05-rehearsal-oauth-client",
                version=1,
            )
        )
        ids: dict[str, object] = {
            "organization_id": organization.id,
            "registration_id": registration.id,
            "course_id": course.id,
            "actor_id": actor.id,
            "first_target_id": first_target.id,
            "second_target_id": second_target.id,
        }
    with session_factory() as db:
        issued = issue_product_session(
            db,
            registration_id=int(ids["registration_id"]),
            user_id=int(ids["actor_id"]),
            course_id=int(ids["course_id"]),
            role="instructor",
        )
        ids["product_session_id"] = issued.row.id
        ids["raw_product_session"] = issued.raw_token
    return ids


def _capture_race(session_factory, ids: dict[str, object]) -> dict[str, object]:
    barrier = Barrier(2)

    def worker() -> int:
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '10s'"))
            registration = db.get(LtiRegistration, ids["registration_id"])
            if registration is None:
                raise AssertionError("registration missing")
            barrier.wait(timeout=10)
            captured = capture_unbound_candidates(
                db,
                registration=registration,
                subject="opaque-rehearsal-subject",
                context_id="opaque-rehearsal-context",
            )
            db.commit()
            return captured

    with ThreadPoolExecutor(max_workers=2) as executor:
        captures = [
            future.result(timeout=20)
            for future in [executor.submit(worker), executor.submit(worker)]
        ]

    with session_factory() as db:
        candidates = (
            db.query(LtiBindingCandidate)
            .filter(
                LtiBindingCandidate.registration_id == ids["registration_id"],
                LtiBindingCandidate.candidate_type == "subject",
            )
            .all()
        )
        if len(candidates) != 1 or candidates[0].seen_count != 2:
            raise AssertionError("concurrent capture did not converge")

    return {
        "worker_captures": sorted(captures),
        "candidate_count": 1,
        "seen_count": 2,
    }


def _binding_race(session_factory, ids: dict[str, object]) -> dict[str, object]:
    with session_factory() as db:
        candidate_id = (
            db.query(LtiBindingCandidate.id)
            .filter(
                LtiBindingCandidate.registration_id == ids["registration_id"],
                LtiBindingCandidate.candidate_type == "subject",
            )
            .scalar()
        )
    if candidate_id is None:
        raise AssertionError("candidate missing")

    barrier = Barrier(2)

    def worker(target_id: int) -> str:
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                bind_candidate(
                    db,
                    organization_id=ids["organization_id"],
                    registration_id=ids["registration_id"],
                    candidate_id=candidate_id,
                    target_id=target_id,
                    actor_user_id=ids["actor_id"],
                )
                db.commit()
                return "bound"
            except LtiBindingError as exc:
                db.rollback()
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(worker, ids["first_target_id"]),
                executor.submit(worker, ids["second_target_id"]),
            ]
        ]

    with session_factory() as db:
        candidate = db.get(LtiBindingCandidate, candidate_id)
        binding_count = (
            db.query(LtiSubjectBinding)
            .filter(LtiSubjectBinding.registration_id == ids["registration_id"])
            .count()
        )
        event_count = (
            db.query(LtiBindingEvent)
            .filter(LtiBindingEvent.registration_id == ids["registration_id"])
            .count()
        )
        if sorted(results) != ["bound", "candidate_unavailable"]:
            raise AssertionError("concurrent binding results are unsafe")
        if (
            candidate is None
            or candidate.status != "bound"
            or candidate.platform_identifier is not None
            or binding_count != 1
            or event_count != 1
        ):
            raise AssertionError("concurrent binding invariants failed")

    return {
        "worker_results": sorted(results),
        "binding_count": 1,
        "event_count": 1,
        "plaintext_cleared": True,
    }


def _oauth_callback_relaunch_race(
    session_factory, ids: dict[str, object]
) -> dict[str, object]:
    raw_session = str(ids["raw_product_session"])
    with session_factory() as db:
        started = start_instructor_canvas_oauth(
            db,
            organization_id=int(ids["organization_id"]),
            registration_id=int(ids["registration_id"]),
            user_id=int(ids["actor_id"]),
            product_session_id=int(ids["product_session_id"]),
            course_id=int(ids["course_id"]),
            raw_session_token=raw_session,
        )
    authorization_params = parse_qs(urlparse(started["authorization_url"]).query)
    state = authorization_params["state"][0]
    redirect_uri = authorization_params["redirect_uri"][0]
    exchanger = FakeCanvasCodeExchanger()
    store = InMemoryDevelopmentSecretStore()
    code = exchanger.issue_code(
        state=state,
        redirect_uri=redirect_uri,
    )
    barrier = Barrier(2)

    def callback_worker() -> str:
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            try:
                return complete_canvas_oauth_callback(
                    db,
                    state=state,
                    code=code,
                    error=None,
                    exchanger=exchanger,
                    store=store,
                    raw_product_session_token=raw_session,
                ).result
            except CanvasOAuthError as exc:
                db.rollback()
                if (
                    exc.code != "callback_authorization_changed"
                    or exc.return_flow_kind != "instructor"
                    or exc.return_course_id != int(ids["course_id"])
                ):
                    raise
                return exc.code

    def relaunch_worker() -> str:
        with session_factory() as db:
            db.execute(text("SET LOCAL lock_timeout = '10s'"))
            barrier.wait(timeout=10)
            issue_product_session(
                db,
                registration_id=int(ids["registration_id"]),
                user_id=int(ids["actor_id"]),
                course_id=int(ids["course_id"]),
                role="instructor",
            )
            return "relaunched"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=20)
            for future in [
                executor.submit(callback_worker),
                executor.submit(relaunch_worker),
            ]
        ]
    if results[1] != "relaunched" or results[0] not in {
        "connected",
        "callback_authorization_changed",
    }:
        raise AssertionError("OAuth callback/relaunch race did not fail safely")
    with session_factory() as db:
        attempt = db.query(CanvasOAuthAttempt).one()
        connection_count = db.query(CanvasOAuthConnection).count()
        if attempt.consumed_at is None or connection_count not in {0, 1}:
            raise AssertionError("OAuth callback/relaunch invariants failed")
    return {
        "worker_results": results,
        "attempt_consumed": True,
        "connection_count": connection_count,
    }


def run() -> dict[str, object]:
    engine = create_engine(
        rehearsal_database_url(),
        future=True,
        pool_pre_ping=True,
        pool_size=4,
        max_overflow=0,
    )
    session_factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    try:
        schema = _assert_schema(session_factory)
        ids = _seed(session_factory)
        capture = _capture_race(session_factory, ids)
        binding = _binding_race(session_factory, ids)
        oauth = _oauth_callback_relaunch_race(session_factory, ids)
        return {
            "status": "passed",
            "database_guard": "passed",
            "schema": schema,
            "capture_race": capture,
            "binding_race": binding,
            "oauth_callback_relaunch_race": oauth,
        }
    finally:
        engine.dispose()


def main() -> int:
    try:
        report = run()
    except Exception as exc:
        print(
            json.dumps(
                {"status": "failed", "error_type": type(exc).__name__},
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
