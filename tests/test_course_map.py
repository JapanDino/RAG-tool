from datetime import UTC, datetime, timedelta

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
    CourseModule,
    Dataset,
    Document,
    LtiProductSession,
    LtiRegistration,
    Organization,
    User,
)
from backend.app.services.course_map import build_course_map
from backend.app.services.product_session import issue_product_session


def _context(monkeypatch, *, role: str = "student"):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_MODE", "development")
    monkeypatch.delenv("API_WRITE_KEY", raising=False)
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_get_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with Session() as db:
        organization = Organization(slug="course-map", name="Course map school")
        dataset = Dataset(name="course-map-dataset")
        user = User(email=f"{role}@course-map.test", display_name="Learner")
        db.add_all([organization, dataset, user])
        db.flush()
        course = Course(
            organization_id=organization.id,
            dataset_id=dataset.id,
            external_id="42",
            title="Алгоритмы и структуры данных",
            description="  Маршрут по алгоритмам.  ",
            source_type="canvas",
            source_url="https://canvas.example.edu/courses/42",
        )
        registration = LtiRegistration(
            organization_id=organization.id,
            issuer="https://canvas.example.edu",
            client_id="course-map-client",
            deployment_id="course-map-deployment",
            authorization_endpoint="https://canvas.example.edu/api/lti/authorize_redirect",
            jwks_url="https://canvas.example.edu/api/lti/security/jwks",
            tool_launch_url="https://tool.example.edu/integrations/lti/launch",
            is_active=True,
        )
        db.add_all([course, registration])
        db.flush()
        db.add(
            CourseMembership(
                organization_id=organization.id,
                course_id=course.id,
                user_id=user.id,
                role=role,
                is_active=True,
            )
        )
        module = CourseModule(
            course_id=course.id,
            external_id="7",
            title="01. Данные и поиск",
            position=1,
            meta={
                "course_map_items": [
                    {
                        "id": "101",
                        "title": "От документа к ответу",
                        "type": "SubHeader",
                        "position": 1,
                        "student_visible": True,
                    },
                    {
                        "id": "102",
                        "title": "Как устроен поиск",
                        "type": "Page",
                        "position": 2,
                        "student_visible": True,
                        "html_url": "https://canvas.example.edu/courses/42/pages/search",
                    },
                    {
                        "id": "103",
                        "title": "Скрытый ключ ответа",
                        "type": "Page",
                        "position": 3,
                        "student_visible": False,
                        "html_url": "https://canvas.example.edu/courses/42/pages/hidden",
                    },
                    {
                        "id": "104",
                        "title": "Небезопасная ссылка",
                        "type": "ExternalUrl",
                        "position": 4,
                        "student_visible": True,
                        "external_url": "javascript:alert(1)",
                    },
                    {
                        "id": "105",
                        "title": "Новый тип Canvas",
                        "type": "Discussion",
                        "position": 5,
                        "student_visible": True,
                        "html_url": "https://canvas.example.edu/courses/42/discussion_topics/5",
                    },
                    {
                        "id": "106",
                        "title": "Будущий материал",
                        "type": "File",
                        "position": 6,
                        "student_visible": True,
                        "unlock_at": "2099-01-01T00:00:00Z",
                        "html_url": "https://canvas.example.edu/courses/42/files/6",
                    },
                    {
                        "id": "107",
                        "title": "Материал с неверной датой",
                        "type": "Page",
                        "position": "not-a-position",
                        "student_visible": True,
                        "unlock_at": "not-a-date",
                        "html_url": "https://canvas.example.edu/courses/42/pages/broken",
                    },
                    {
                        "id": "108",
                        "title": "Подменённая ссылка страницы",
                        "type": "Page",
                        "position": 8,
                        "student_visible": True,
                        "html_url": "https://external.example/page",
                    },
                    {
                        "id": "109",
                        "title": "Ссылка с параметром доступа",
                        "type": "File",
                        "position": 9,
                        "student_visible": True,
                        "html_url": "https://canvas.example.edu/files/9?access_token=secret-value",
                    },
                    {
                        "id": "110",
                        "title": "Противоречиво закрытый материал",
                        "type": "Page",
                        "position": 10,
                        "student_visible": True,
                        "locked_for_user": True,
                        "html_url": "https://canvas.example.edu/courses/42/pages/locked",
                    },
                    {
                        "id": "111",
                        "title": "Противоречиво неопубликованный материал",
                        "type": "Page",
                        "position": 11,
                        "student_visible": True,
                        "canvas_published": False,
                        "html_url": "https://canvas.example.edu/courses/42/pages/unpublished",
                    },
                    {
                        "id": "112",
                        "title": "Материал с повреждённой ссылкой",
                        "type": "Page",
                        "position": 12,
                        "student_visible": True,
                        "html_url": "https://[invalid",
                    },
                ]
            },
        )
        db.add(module)
        db.commit()
        issued = issue_product_session(
            db,
            registration_id=registration.id,
            user_id=user.id,
            course_id=course.id,
            role=role,
        )
        ids = {
            "course_id": course.id,
            "module_id": module.id,
            "session_id": issued.row.id,
        }
    client = TestClient(app)
    client.cookies.set("rag_lti_session", issued.raw_token)
    return client, Session, engine, ids


def test_course_map_api_is_exact_ordered_bounded_and_fail_closed(monkeypatch):
    client, Session, engine, ids = _context(monkeypatch)
    try:
        response = client.get("/course-map")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store, max-age=0"
        payload = response.json()
        assert payload["version"] == "1"
        assert payload["read_only"] is True
        assert payload["exact_context"] is True
        assert payload["course"] == {
            "id": ids["course_id"],
            "title": "Алгоритмы и структуры данных",
            "syllabus_summary": "Маршрут по алгоритмам.",
            "destination_url": "https://canvas.example.edu/courses/42",
        }
        items = payload["modules"][0]["items"]
        assert [item["item_type"] for item in items] == [
            "section",
            "page",
            "external",
            "unsupported",
            "page",
            "file",
            "page",
        ]
        assert "Скрытый ключ ответа" not in response.text
        assert "Будущий материал" not in response.text
        assert "Материал с неверной датой" not in response.text
        assert "Противоречиво закрытый материал" not in response.text
        assert "Противоречиво неопубликованный материал" not in response.text
        assert items[2]["destination_url"] is None
        assert items[2]["destination_provenance"] is None
        assert items[3]["supported"] is False
        assert items[4]["destination_provenance"] == "external"
        assert items[5]["destination_url"] is None
        assert items[6]["destination_url"] is None
        assert "secret-value" not in response.text
        assert "javascript:" not in response.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_course_map_rejects_development_identity_instructor_and_expired_session(
    monkeypatch,
):
    client, Session, engine, ids = _context(monkeypatch, role="instructor")
    try:
        assert client.get("/course-map").status_code == 404
        raw_token = client.cookies.get("rag_lti_session")
        assert raw_token
        client.cookies.clear()
        assert (
            client.get(
                "/course-map", headers={"X-Dev-User": "instructor@course-map.test"}
            ).status_code
            == 401
        )
        with Session() as db:
            session = db.get(LtiProductSession, ids["session_id"])
            session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        client.cookies.set("rag_lti_session", raw_token)
        assert client.get("/course-map").status_code == 401
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_course_map_document_fallback_keeps_only_explicitly_visible_material():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    try:
        with Session() as db:
            dataset = Dataset(name="fallback-map")
            db.add(dataset)
            db.flush()
            course = Course(
                dataset_id=dataset.id,
                title="Fallback course",
                source_type="canvas",
                source_url="https://canvas.example.edu/courses/8",
            )
            db.add(course)
            db.flush()
            module = CourseModule(course_id=course.id, title="Модуль", position=1)
            db.add(module)
            db.flush()
            db.add_all(
                [
                    Document(
                        dataset_id=dataset.id,
                        course_module_id=module.id,
                        title="Опубликованная страница",
                        source="https://canvas.example.edu/courses/8/pages/visible",
                        mime="text/html",
                        source_metadata={
                            "document_type": "lecture_material",
                            "student_visible": True,
                            "canvas_position": 2,
                        },
                    ),
                    Document(
                        dataset_id=dataset.id,
                        course_module_id=module.id,
                        title="Неизвестная видимость",
                        source="https://canvas.example.edu/courses/8/pages/unknown",
                        mime="text/html",
                        source_metadata={"document_type": "lecture_material"},
                    ),
                    Document(
                        dataset_id=dataset.id,
                        course_module_id=module.id,
                        title="Документ с ошибкой обработки",
                        source="https://canvas.example.edu/courses/8/pages/error",
                        mime="text/html",
                        status="error",
                        source_metadata={
                            "document_type": "lecture_material",
                            "student_visible": True,
                        },
                    ),
                ]
            )
            db.commit()
            result = build_course_map(db, course)
            assert result.total_items == 1
            assert result.modules[0].items[0].title == "Опубликованная страница"
            assert result.modules[0].items[0].destination_provenance == "canvas"
    finally:
        engine.dispose()
