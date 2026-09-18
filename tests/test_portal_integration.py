"""Run against a disposable PostgreSQL/pgvector DB and Redis; see admin handoff."""

import io
import json
import os
import time
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.routers import portal
from backend.app.services import lti_security as sec

pytestmark = pytest.mark.skipif(
    not os.getenv("PORTAL_TEST_DATABASE_URL"),
    reason="Requires disposable PostgreSQL/pgvector and Redis",
)


@pytest.fixture(scope="module")
def database():
    engine = create_engine(os.environ["PORTAL_TEST_DATABASE_URL"])
    # Only explicitly named disposable databases are accepted.
    assert engine.url.database == "portal_test"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for migration in sorted(
            (Path(__file__).parents[1] / "backend/migrations").glob("*.sql")
        ):
            conn.exec_driver_sql(
                migration.read_text(encoding="utf-8"),
                execution_options={"no_parameters": True},
            )
    yield sessionmaker(bind=engine)
    engine.dispose()


@pytest.fixture
def pilot(database, monkeypatch):
    monkeypatch.setenv("APP_MODE", "lti")
    monkeypatch.setenv("CANVAS_URL", "https://canvas.test")
    monkeypatch.setenv(
        "REDIS_URL", os.getenv("PORTAL_TEST_REDIS_URL", "redis://localhost:56379/0")
    )
    sec.redis_client.cache_clear()
    db = database()
    ident = uuid.uuid4().hex
    ds = db.execute(
        text("INSERT INTO datasets(name) VALUES (:name) RETURNING id"),
        {"name": "test-" + ident},
    ).scalar_one()
    cid = db.execute(
        text(
            "INSERT INTO portal_courses(binding,canvas_course_id,title,dataset_id) VALUES (:binding,123,'Test course',:ds) RETURNING id"
        ),
        {"binding": ident, "ds": ds},
    ).scalar_one()
    db.commit()
    session = {
        "role": "teacher",
        "course_id": cid,
        "canvas_course_id": 123,
        "dataset_id": ds,
        "subject": ident,
        "title": "Test course",
    }
    token = sec.put_token("session", session, 120)

    def connection():
        unit = database()
        try:
            yield unit
        finally:
            unit.close()

    app.dependency_overrides[get_db] = connection
    monkeypatch.setattr(portal, "current_embedding_model", lambda: "test:semantic")
    monkeypatch.setattr(
        portal, "embed_texts", lambda parts: [[1.0] + [0.0] * 1535 for _ in parts]
    )
    monkeypatch.setattr(portal, "embed_query", lambda _: [1.0] + [0.0] * 1535)
    client = TestClient(
        app,
        base_url="https://assistant.test",
        headers={"Authorization": "Bearer " + token},
    )
    yield client, db, session
    app.dependency_overrides.clear()
    db.execute(text("DELETE FROM datasets WHERE id=:id"), {"id": ds})
    db.commit()
    db.close()
    sec.redis_client.cache_clear()


def student(client, session):
    token = sec.put_token("session", {**session, "role": "student"}, 120)
    client.headers["Authorization"] = "Bearer " + token


def upload(client, publish=True):
    response = client.post(
        "/portal/materials",
        files={
            "file": (
                "lesson.txt",
                "Объясните фотосинтез и сравните его этапы.".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    doc = response.json()["document_id"]
    if publish:
        assert (
            client.patch(
                f"/portal/materials/{doc}", json={"published": True}
            ).status_code
            == 200
        )
    return doc


def test_upload_publication_and_student_permissions(pilot):
    client, _db, session = pilot
    doc = upload(client, publish=False)
    student(client, session)
    assert client.get("/portal/materials").json() == []
    assert client.get(f"/portal/materials/{doc}").status_code == 404
    for method, path, kwargs in [
        ("post", "/portal/import-canvas", {}),
        ("get", "/portal/analysis", {}),
        ("get", "/portal/summary", {}),
        ("patch", f"/portal/materials/{doc}", {"json": {"published": True}}),
        ("delete", f"/portal/materials/{doc}", {}),
        (
            "post",
            "/portal/materials",
            {"files": {"file": ("bad.txt", b"test", "text/plain")}},
        ),
    ]:
        assert getattr(client, method)(path, **kwargs).status_code == 403


def test_course_isolation_and_client_cannot_override_dataset(pilot):
    client, _db, session = pilot
    doc = upload(client)
    client.headers["Authorization"] = "Bearer " + sec.put_token(
        "session", {**session, "course_id": -999, "dataset_id": -999}, 120
    )
    assert client.get(f"/portal/materials/{doc}").status_code == 404
    assert (
        client.patch(f"/portal/materials/{doc}", json={"published": True}).status_code
        == 404
    )
    assert (
        client.post(
            f"/portal/materials/{doc}/feedback", json={"rating": "clear"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/portal/chat",
            json={"message": "test", "dataset_id": session["dataset_id"]},
        ).status_code
        == 422
    )


def test_chat_uses_only_published_chunks_and_valid_citations(pilot, monkeypatch):
    client, db, session = pilot
    visible, hidden = upload(client), upload(client, publish=False)
    chunk = db.execute(
        text("SELECT id FROM chunks WHERE document_id=:doc"), {"doc": visible}
    ).scalar_one()

    def answer(model, prompt, max_tokens):
        body = json.loads(prompt.split("\n", 1)[1])
        assert [p["id"] for p in body["sources"]] == [chunk]
        return json.dumps({"answer": "Объяснение по источнику", "citations": [chunk]})

    monkeypatch.setattr(portal, "chat_completion_json", answer)
    student(client, session)
    response = client.post("/portal/chat", json={"message": "Что такое фотосинтез?"})
    assert response.status_code == 200, response.text
    assert response.json()["citations"][0]["document_id"] == visible
    assert client.get(f"/portal/materials/{hidden}").status_code == 404


def test_invalid_citation_refuses_answer(pilot, monkeypatch):
    client, _, _ = pilot
    upload(client)
    monkeypatch.setattr(
        portal,
        "chat_completion_json",
        lambda *a, **k: '{"answer":"invented","citations":[-1]}',
    )
    result = client.post("/portal/chat", json={"message": "test"}).json()
    assert result == {"answer": portal.NO_ANSWER, "citations": []}


def test_no_context_never_calls_llm(pilot, monkeypatch):
    client, _, _ = pilot

    def unexpected(*args, **kwargs):
        pytest.fail("LLM called without context")

    monkeypatch.setattr(portal, "chat_completion_json", unexpected)
    assert (
        client.post("/portal/chat", json={"message": "test"}).json()["citations"] == []
    )


def test_feedback_has_no_identity_and_small_counts_suppressed(pilot):
    client, db, session = pilot
    doc = upload(client)
    teacher_auth = client.headers["Authorization"]
    student(client, session)
    assert (
        client.post(
            f"/portal/materials/{doc}/feedback",
            json={"rating": "difficult", "comment": "Private comment"},
        ).status_code
        == 200
    )
    stored = (
        db.execute(
            text("SELECT * FROM portal_feedback WHERE course_id=:id"),
            {"id": session["course_id"]},
        )
        .mappings()
        .one()
    )
    assert "subject" not in stored and "user_id" not in stored
    client.headers["Authorization"] = teacher_auth
    response = client.get("/portal/summary")
    assert response.json()["feedback"][0]["count"] is None
    assert "Private comment" not in response.text


def test_canvas_changed_page_is_withdrawn(pilot, monkeypatch):
    client, db, session = pilot
    doc = upload(client)
    db.execute(
        text(
            "UPDATE portal_materials SET kind='canvas_page', source_ref='page' WHERE document_id=:doc"
        ),
        {"doc": doc},
    )
    db.commit()
    monkeypatch.setattr(
        portal.canvas_client,
        "get_page",
        lambda *a: {"published": False, "body": "changed"},
    )
    student(client, session)
    assert client.get(f"/portal/materials/{doc}").status_code == 404
    assert client.get("/portal/materials").json() == []


def test_docx_extracts_text_instead_of_zip_bytes(pilot):
    client, _, _ = pilot
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Actual document text</w:t></w:r></w:p></w:body></w:document>',
        )
    response = client.post(
        "/portal/materials", files={"file": ("sample.docx", output.getvalue())}
    )
    assert response.status_code == 200, response.text
    source = client.get(
        "/portal/materials/" + str(response.json()["document_id"])
    ).json()
    assert source["chunks"][0]["text"] == "Actual document text"


def test_full_signed_launch_and_replay_rejected(pilot, monkeypatch):
    client, _db, _ = pilot
    config = {
        "PUBLIC_BASE_URL": "https://assistant.test",
        "CANVAS_URL": "https://canvas.test",
        "LTI_ISSUER": "https://canvas.test",
        "LTI_CLIENT_ID": "123",
        "LTI_DEPLOYMENT_ID": "deploy",
        "LTI_AUTH_URL": "https://canvas.test/authorize",
        "LTI_JWKS_URL": "https://canvas.test/jwks",
        "LTI_ALLOWED_COURSE_IDS": "123",
    }
    for k, v in config.items():
        monkeypatch.setenv(k, v)
    response = client.get(
        "/lti/login",
        params={
            "iss": config["LTI_ISSUER"],
            "login_hint": "hint",
            "target_link_uri": "https://assistant.test/lti/launch",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        sec,
        "jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key())
        ),
    )
    claims = {
        "iss": config["LTI_ISSUER"],
        "aud": "123",
        "sub": "test-user",
        "iat": int(time.time()),
        "exp": int(time.time()) + 60,
        "nonce": query["nonce"][0],
        sec.CLAIM + "deployment_id": "deploy",
        sec.CLAIM + "version": "1.3.0",
        sec.CLAIM + "message_type": "LtiResourceLinkRequest",
        sec.CLAIM + "target_link_uri": "https://assistant.test/lti/launch",
        sec.CLAIM + "context": {"id": uuid.uuid4().hex},
        sec.CLAIM + "custom": {"canvas_course_id": "123"},
        sec.CLAIM + "roles": [sec.LEARNER_ROLE],
        sec.CLAIM + "resource_link": {"id": "link"},
    }
    data = {
        "id_token": jwt.encode(claims, private, algorithm="RS256"),
        "state": query["state"][0],
    }
    response = client.post("/lti/launch", data=data)
    assert response.status_code == 200, response.text
    assert "sessionStorage.setItem" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert client.post("/lti/launch", data=data).status_code == 401
