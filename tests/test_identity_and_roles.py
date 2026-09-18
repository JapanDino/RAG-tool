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
    Organization,
    OrganizationMembership,
    User,
)


def _client(monkeypatch):
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

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), Session, engine


def _headers(email: str) -> dict[str, str]:
    return {"X-Dev-User": email}


def test_development_identity_bootstrap_and_role_specific_course_access(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        assert client.get("/courses").status_code == 401
        bootstrapped = client.post("/identity/development/bootstrap", json={})
        assert bootstrapped.status_code == 201
        organization_id = bootstrapped.json()["organization"]["id"]
        assert len(bootstrapped.json()["identities"]) == 5

        identities = client.get("/identity/development/users")
        assert identities.status_code == 200
        assert {item["primary_role"] for item in identities.json()} == {
            "student",
            "instructor",
            "methodologist",
            "program_designer",
            "administrator",
        }

        created = client.post(
            "/courses",
            headers=_headers("instructor@local.test"),
            json={
                "title": "Алгоритмы и структуры данных",
                "source_url": "https://canvas.internal/courses/42",
                "source_metadata": {"internal_note": "staff-only"},
                "modules": [{"title": "Неопубликованный модуль", "position": 1}],
            },
        )
        assert created.status_code == 201
        course_id = created.json()["id"]
        assert created.json()["organization_id"] == organization_id

        instructor_courses = client.get(
            "/courses", headers=_headers("instructor@local.test")
        )
        assert [item["id"] for item in instructor_courses.json()] == [course_id]
        assert (
            client.get(
                f"/courses/{course_id}/audits",
                headers=_headers("instructor@local.test"),
            ).status_code
            == 200
        )

        student_courses = client.get("/courses", headers=_headers("student@local.test"))
        assert student_courses.json() == []

        members = client.get(
            f"/identity/organizations/{organization_id}/members",
            headers=_headers("admin@local.test"),
        )
        student_id = next(
            item["id"]
            for item in members.json()
            if item["email"] == "student@local.test"
        )
        assigned = client.put(
            f"/identity/organizations/{organization_id}/courses/{course_id}/members/{student_id}",
            headers=_headers("admin@local.test"),
            json={"role": "student", "is_active": True},
        )
        assert assigned.status_code == 200

        member_ids = {item["email"]: item["id"] for item in members.json()}
        for email, role in (
            ("methodologist@local.test", "methodologist"),
            ("designer@local.test", "program_designer"),
        ):
            response = client.put(
                f"/identity/organizations/{organization_id}/courses/{course_id}/members/{member_ids[email]}",
                headers=_headers("admin@local.test"),
                json={"role": role, "is_active": True},
            )
            assert response.status_code == 200

        for email in (
            "instructor@local.test",
            "methodologist@local.test",
            "admin@local.test",
        ):
            protocol = client.post(
                f"/courses/{course_id}/evaluation-protocols",
                headers=_headers(email),
            )
            assert protocol.status_code == 201
            assert protocol.json()["status"] == "failed"

        designer_protocols = client.get(
            f"/courses/{course_id}/evaluation-protocols",
            headers=_headers("designer@local.test"),
        )
        assert designer_protocols.status_code == 200
        assert len(designer_protocols.json()) == 3
        assert (
            client.post(
                f"/courses/{course_id}/evaluation-protocols",
                headers=_headers("designer@local.test"),
            ).status_code
            == 404
        )
        for method in (client.get, client.post):
            denied = method(
                f"/courses/{course_id}/evaluation-protocols",
                headers=_headers("student@local.test"),
            )
            assert denied.status_code == 404
            assert denied.json()["detail"] == "resource not found"

        student_course = client.get(
            f"/courses/{course_id}", headers=_headers("student@local.test")
        )
        assert student_course.status_code == 200
        assert student_course.json()["modules"] == []
        assert student_course.json()["source_url"] is None
        assert student_course.json()["source_metadata"] == {}
        assert (
            client.get(
                f"/courses/{course_id}/documents",
                headers=_headers("student@local.test"),
            ).status_code
            == 404
        )
        assert (
            client.patch(
                f"/courses/{course_id}",
                headers=_headers("student@local.test"),
                json={"title": "Недопустимое изменение"},
            ).status_code
            == 404
        )

        student_context = client.get(
            "/identity/me", headers=_headers("student@local.test")
        ).json()
        instructor_context = client.get(
            "/identity/me", headers=_headers("instructor@local.test")
        ).json()
        assert student_context["courses"][0]["actions"] == [
            "ask_tutor",
            "open_course",
            "student_home",
        ]
        assert "run_audit" in instructor_context["courses"][0]["actions"]
        assert "manage_content" in instructor_context["courses"][0]["actions"]

        demo = client.post("/courses/demo", headers=_headers("instructor@local.test"))
        assert demo.status_code == 201
        audit_id = demo.json()["audit_run_id"]
        assert (
            client.get(
                f"/audits/{audit_id}/report",
                headers=_headers("instructor@local.test"),
            ).status_code
            == 200
        )
        denied_report = client.get(
            f"/audits/{audit_id}/report",
            headers=_headers("student@local.test"),
        )
        assert denied_report.status_code == 404
        assert denied_report.json()["detail"] == "resource not found"
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_cross_organization_requests_are_non_disclosing(monkeypatch):
    client, Session, engine = _client(monkeypatch)
    try:
        client.post("/identity/development/bootstrap", json={})
        with Session() as db:
            outsider = db.query(User).filter(User.email == "student@local.test").one()
            second_org = Organization(slug="second-school", name="Другая школа")
            db.add(second_org)
            db.flush()
            dataset = Dataset(name="private-course-dataset")
            db.add(dataset)
            db.flush()
            private_course = Course(
                organization_id=second_org.id,
                dataset_id=dataset.id,
                title="Закрытый курс",
                source_type="manual",
            )
            db.add(private_course)
            db.flush()
            other_user = User(
                email="teacher@second.test",
                display_name="Другой преподаватель",
            )
            db.add(other_user)
            db.flush()
            db.add(
                OrganizationMembership(
                    organization_id=second_org.id,
                    user_id=other_user.id,
                    role="instructor",
                )
            )
            db.add(
                CourseMembership(
                    organization_id=second_org.id,
                    course_id=private_course.id,
                    user_id=other_user.id,
                    role="instructor",
                )
            )
            private_course_id = private_course.id
            outsider_id = outsider.id
            db.commit()

        response = client.get(
            f"/courses/{private_course_id}",
            headers=_headers("student@local.test"),
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "resource not found"
        listed = client.get("/courses", headers=_headers("student@local.test"))
        assert all(item["id"] != private_course_id for item in listed.json())

        with Session() as db:
            assert db.get(User, outsider_id) is not None
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
