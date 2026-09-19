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
from material_image_fixtures import docx as illustrated_docx
from material_image_fixtures import pdf as illustrated_pdf
from material_image_fixtures import png
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.routers import portal
from backend.app.services import canvas_images
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


@pytest.mark.parametrize(
    "filename,data,count",
    [
        ("illustrated.docx", illustrated_docx(), 1),
        ("illustrated.pdf", illustrated_pdf(), 2),
    ],
    ids=["docx", "pdf"],
)
def test_illustration_lifecycle_and_original_permissions(pilot, filename, data, count):
    client, db, session = pilot
    teacher_headers = dict(client.headers)
    response = client.post("/portal/materials", files={"file": (filename, data)})
    assert response.status_code == 200, response.text
    assert response.json()["images_imported"] == count
    doc = response.json()["document_id"]
    source = client.get(f"/portal/materials/{doc}").json()
    assert len(source["images"]) == count and source["original_available"]
    picture = source["images"][0]
    path = f"/portal/materials/{doc}/images/{picture['id']}"
    original = f"/portal/materials/{doc}/original"
    response = client.get(path)
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert response.headers["cache-control"] == "no-store"
    assert client.get(original).content == data
    assert client.get(path, headers={"Authorization": ""}).status_code == 401
    student(client, session)
    assert client.get(path).status_code == client.get(original).status_code == 404
    client.headers.update(teacher_headers)
    client.patch(f"/portal/materials/{doc}", json={"published": True})
    # Image-context chunks must not inflate the Bloom distribution or material reader.
    analysis = client.get("/portal/analysis").json()
    assert analysis["chunks_analyzed"] == len(source["chunks"])
    student(client, session)
    assert client.get(path).status_code == client.get(original).status_code == 200
    student(client, {**session, "course_id": -1})
    assert client.get(path).status_code == client.get(original).status_code == 404
    client.headers.update(teacher_headers)
    client.patch(f"/portal/materials/{doc}", json={"published": False})
    student(client, session)
    assert client.get(path).status_code == client.get(original).status_code == 404
    client.headers.update(teacher_headers)
    client.delete(f"/portal/materials/{doc}")
    assert (
        db.execute(
            text("SELECT count(*) FROM portal_images WHERE document_id=:doc"),
            {"doc": doc},
        ).scalar()
        == 0
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM portal_files WHERE document_id=:doc"),
            {"doc": doc},
        ).scalar()
        == 0
    )


def test_chat_images_must_be_retrieved_selected_and_cited(pilot, monkeypatch):
    client, _db, session = pilot
    doc = client.post(
        "/portal/materials", files={"file": ("lesson.docx", illustrated_docx())}
    ).json()["document_id"]
    source = client.get(f"/portal/materials/{doc}").json()
    picture = source["images"][0]
    client.patch(f"/portal/materials/{doc}", json={"published": True})
    student(client, session)

    def answer(_model, prompt, **kwargs):
        assert '"images": [' in prompt and picture["caption"] in prompt
        return json.dumps(
            {
                "answer": "АТФ связывает две фазы.",
                "citations": [picture["chunk_id"]],
                "image_ids": [picture["id"], 999999, True],
            }
        )

    monkeypatch.setattr(portal, "chat_completion_json", answer)
    response = client.post("/portal/chat", json={"message": "Покажи схему фотосинтеза"})
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["images"]] == [picture["id"]]
    monkeypatch.setattr(
        portal,
        "chat_completion_json",
        lambda *a, **k: json.dumps(
            {
                "answer": "Текст без подтверждения иллюстрации",
                "citations": [source["chunks"][0]["id"]],
                "image_ids": [picture["id"]],
            }
        ),
    )
    assert (
        client.post("/portal/chat", json={"message": "Вопрос"}).json()["images"] == []
    )


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
        body = json.loads(prompt.rsplit("\n", 1)[1])
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


@pytest.mark.parametrize("extension", ["txt", "md"])
def test_text_material_lifecycle_and_analysis(pilot, extension):
    client, db, session = pilot
    response = client.post(
        "/portal/materials",
        files={
            "file": (
                f"lesson.{extension}",
                "Объясните фотосинтез. Сравните этапы.".encode(),
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    doc = response.json()["document_id"]
    assert client.get("/portal/analysis").json()["chunks_analyzed"] == 1
    assert (
        client.patch(f"/portal/materials/{doc}", json={"published": True}).status_code
        == 200
    )
    teacher_auth = client.headers["Authorization"]
    student(client, session)
    assert len(client.get("/portal/materials").json()) == 1
    assert (
        client.post(
            f"/portal/materials/{doc}/feedback", json={"rating": "clear"}
        ).status_code
        == 200
    )
    client.headers["Authorization"] = teacher_auth
    assert (
        client.patch(f"/portal/materials/{doc}", json={"published": False}).status_code
        == 200
    )
    assert client.delete(f"/portal/materials/{doc}").status_code == 200
    assert client.get(f"/portal/materials/{doc}").status_code == 404
    assert (
        db.execute(
            text("SELECT count(*) FROM portal_feedback WHERE document_id=:doc"),
            {"doc": doc},
        ).scalar()
        == 0
    )
    assert (
        db.execute(
            text("SELECT count(*) FROM chunks WHERE document_id=:doc"), {"doc": doc}
        ).scalar()
        == 0
    )


@pytest.mark.parametrize(
    "filename,content,status",
    [
        ("empty.txt", b"   ", 422),
        ("bad.exe", b"text", 415),
        ("long.txt", b"a" * 60001, 413),
        ("large.txt", b"a" * (10 * 1024 * 1024 + 1), 413),
    ],
    ids=["empty", "unsupported", "text-too-long", "file-too-large"],
)
def test_upload_limits_leave_no_material(pilot, filename, content, status):
    client, _, _ = pilot
    response = client.post("/portal/materials", files={"file": (filename, content)})
    assert response.status_code == status
    assert client.get("/portal/materials").json() == []


def test_canvas_import_update_and_unavailable_upstream(pilot, monkeypatch):
    client, _, session = pilot
    state = {"body": "<p>Объясните фотосинтез.</p>"}
    monkeypatch.setattr(
        portal.canvas_client,
        "list_pages",
        lambda *a: [{"url": "lesson"}, {"url": "draft"}],
    )
    monkeypatch.setattr(
        portal.canvas_client,
        "get_page",
        lambda course, slug: {
            "published": slug != "draft",
            "body": state["body"],
            "title": "Урок",
        },
    )
    assert client.post("/portal/import-canvas").json() == {
        "imported": 1,
        "skipped": 1,
        "remaining": 0,
        "images_imported": 0,
        "images_skipped": 0,
    }
    doc = client.get("/portal/materials").json()[0]["document_id"]
    client.patch(f"/portal/materials/{doc}", json={"published": True})
    state["body"] = "<p>Сравните этапы фотосинтеза.</p>"
    assert client.post("/portal/import-canvas").json()["imported"] == 1
    rows = client.get("/portal/materials").json()
    assert len(rows) == 1 and rows[0]["document_id"] == doc and not rows[0]["published"]
    client.patch(f"/portal/materials/{doc}", json={"published": True})

    def unavailable(*a):
        raise RuntimeError("synthetic outage")

    monkeypatch.setattr(portal.canvas_client, "list_pages", unavailable)
    assert client.post("/portal/import-canvas").status_code == 502
    assert client.get("/portal/materials").json()[0]["published"] is False
    student(client, session)
    assert client.get("/portal/materials").json() == []


@pytest.mark.parametrize("change", ["hidden", "updated", "html"])
def test_canvas_images_reimport_and_revoke_on_upstream_change(
    pilot, monkeypatch, change
):
    client, _db, session = pilot
    teacher_headers = dict(client.headers)
    state = {
        "body": '<p>Световая фаза передаёт АТФ циклу Кальвина.</p><img src="/courses/123/files/7/preview" alt="Связь фаз"/>'
    }
    info = {
        "id": 7,
        "content-type": "image/png",
        "size": 1000,
        "url": "https://canvas.test/files/7/download",
        "updated_at": "2026-01-01T00:00:00Z",
        "locked": False,
        "hidden": False,
    }
    monkeypatch.setattr(
        portal.canvas_client, "list_pages", lambda _: [{"url": "lesson"}]
    )
    monkeypatch.setattr(
        portal.canvas_client,
        "get_page",
        lambda *args: {"title": "Урок", "published": True, **state},
    )
    monkeypatch.setattr(portal.canvas_client, "get_file", lambda course, file_id: info)
    monkeypatch.setattr(canvas_images, "download_image", lambda _: png())
    assert client.post("/portal/import-canvas").json()["images_imported"] == 1
    doc = client.get("/portal/materials").json()[0]["document_id"]
    assert client.post("/portal/import-canvas").json()["images_imported"] == 1
    source = client.get(f"/portal/materials/{doc}").json()
    assert (
        len(source["images"]) == 1
    )  # Reimport replaces old images, including gallery-only rows.
    picture = source["images"][0]
    assert (
        client.patch(f"/portal/materials/{doc}", json={"published": True}).status_code
        == 200
    )
    student(client, session)
    path = f"/portal/materials/{doc}/images/{picture['id']}"
    assert client.get(path).status_code == 200
    if change == "hidden":
        info["hidden"] = True
    elif change == "updated":
        info["updated_at"] = "2026-02-01T00:00:00Z"
    else:
        state["body"] = state["body"].replace('alt="Связь фаз"', 'alt="Другая схема"')
    assert client.get(path).status_code == 404
    assert client.get(f"/portal/materials/{doc}").status_code == 404
    client.headers.update(teacher_headers)
    assert client.get("/portal/materials").json()[0]["published"] is False


def test_chat_structured_explanation_is_grounded_and_falls_back(pilot, monkeypatch):
    client, db, _ = pilot
    doc = upload(client)
    chunk = db.execute(
        text("SELECT id FROM chunks WHERE document_id=:doc"), {"doc": doc}
    ).scalar_one()
    result = {
        "answer": "Краткое объяснение",
        "citations": [chunk],
        "sections": [
            {
                "heading": "Связь",
                "body": "Объяснение по материалу",
                "citations": [chunk],
            }
        ],
        "diagram": {
            "title": "Схема",
            "nodes": [{"id": "a", "label": "Свет"}, {"id": "b", "label": "АТФ"}],
            "edges": [{"source": "a", "target": "b", "label": "образование"}],
            "citations": [chunk],
        },
    }
    monkeypatch.setattr(
        portal, "chat_completion_json", lambda *a, **k: json.dumps(result)
    )
    response = client.post("/portal/chat", json={"message": "Покажи схему"}).json()
    assert (
        response["sections"][0]["heading"] == "Связь"
        and response["diagram"] == result["diagram"]
    )
    result["sections"][0]["citations"] = [-1]
    check = client.post(
        "/portal/chat", json={"message": "Проверь понимание", "response_style": "check"}
    ).json()
    assert (
        check["sections"] == [] and check["diagram"] is None and check["images"] == []
    )
    result["diagram"]["edges"][0]["source"] = "unknown"
    response = client.post("/portal/chat", json={"message": "Покажи схему"}).json()
    assert (
        response["answer"] == result["answer"]
        and response["sections"] == []
        and response["diagram"] is None
    )


def test_empty_llm_answer_is_refused(pilot, monkeypatch):
    client, db, _ = pilot
    doc = upload(client)
    chunk = db.execute(
        text("SELECT id FROM chunks WHERE document_id=:doc"), {"doc": doc}
    ).scalar_one()
    monkeypatch.setattr(
        portal,
        "chat_completion_json",
        lambda *a, **k: json.dumps({"answer": " ", "citations": [chunk]}),
    )
    assert client.post("/portal/chat", json={"message": "Объясни тему"}).json() == {
        "answer": portal.NO_ANSWER,
        "citations": [],
    }


def test_search_outage_counted_and_chat_rate_limited(pilot, monkeypatch):
    client, _, session = pilot
    monkeypatch.setattr(portal, "current_embedding_model", lambda: "hash:v1:1536")
    assert (
        client.post("/portal/chat", json={"message": "Объясни тему"}).status_code == 503
    )
    assert client.get("/portal/summary").json()["metrics"] == {
        "questions": 1,
        "errors": 1,
    }
    identity = f"{session['course_id']}:{session['subject']}:chat"
    sec.redis_client().setex(sec.key("limit", identity), 120, "60")
    assert (
        client.post("/portal/chat", json={"message": "Объясни тему"}).status_code == 429
    )


def test_llm_outage_and_source_withdrawal_fail_closed(pilot, monkeypatch):
    client, db, _ = pilot
    doc = upload(client)
    chunk = db.execute(
        text("SELECT id FROM chunks WHERE document_id=:doc"), {"doc": doc}
    ).scalar_one()
    monkeypatch.setattr(portal, "chat_completion_json", lambda *a, **k: "not JSON")
    assert (
        client.post("/portal/chat", json={"message": "Объясни тему"}).status_code == 502
    )

    def withdraw(*a, **k):
        db.execute(
            text("UPDATE portal_materials SET published=FALSE WHERE document_id=:doc"),
            {"doc": doc},
        )
        db.commit()
        return json.dumps({"answer": "Must not be returned", "citations": [chunk]})

    monkeypatch.setattr(portal, "chat_completion_json", withdraw)
    result = client.post("/portal/chat", json={"message": "Объясни тему"})
    assert result.status_code == 404
    assert "Must not be returned" not in result.text


def test_selected_context_is_owned_and_quote_is_real(pilot, monkeypatch):
    client, db, session = pilot
    doc = upload(client)
    chunk = client.get(f"/portal/materials/{doc}").json()["chunks"][0]
    monkeypatch.setattr(
        portal,
        "chat_completion_json",
        lambda *a, **k: json.dumps(
            {"answer": "Объяснение", "citations": [chunk["id"]]}
        ),
    )
    good = {
        "message": "Объясни",
        "context": {
            "document_id": doc,
            "chunk_id": chunk["id"],
            "quote": chunk["text"][:30],
        },
    }
    assert client.post("/portal/chat", json=good).status_code == 200
    assert (
        client.post(
            "/portal/chat",
            json={
                **good,
                "context": {**good["context"], "quote": "Несуществующий текст"},
            },
        ).status_code
        == 422
    )
    second = upload(client)
    assert (
        client.post(
            "/portal/chat",
            json={**good, "context": {**good["context"], "document_id": second}},
        ).status_code
        == 404
    )
    client.patch(f"/portal/materials/{doc}", json={"published": False})
    assert client.post("/portal/chat", json=good).status_code == 404


def test_quality_optin_redaction_feedback_and_isolation(pilot, monkeypatch):
    from backend.app.services import course_quality

    client, db, session = pilot
    doc = upload(client)
    chunk = client.get(f"/portal/materials/{doc}").json()["chunks"][0]["id"]
    teacher_auth = client.headers["Authorization"]
    assert (
        client.put(
            "/portal/preferences",
            json={
                "quality_enabled": True,
                "allow_solutions": False,
                "solution_after_attempts": 2,
            },
        ).status_code
        == 200
    )
    monkeypatch.setattr(
        portal,
        "chat_completion_json",
        lambda *a, **k: json.dumps(
            {"answer": "Свяжитесь по teacher@example.org", "citations": [chunk]}
        ),
    )
    student(client, session)
    assert client.get("/portal/quality").status_code == 403
    assert (
        client.put(
            "/portal/preferences",
            json={
                "quality_enabled": True,
                "allow_solutions": True,
                "solution_after_attempts": 1,
            },
        ).status_code
        == 403
    )
    question = {
        "message": "Меня зовут Иван Петров, ivan@example.org. Что такое фотосинтез?"
    }
    assert "review_id" not in client.post("/portal/chat", json=question).json()
    result = client.post(
        "/portal/chat", json={**question, "share_for_review": True}
    ).json()
    assert result["review_id"]
    feedback = f"/portal/quality/{result['review_id']}/feedback"
    assert (
        client.post(
            feedback, json={"feedback": "unclear", "feedback_key": "x" * 32}
        ).status_code
        == 404
    )
    assert (
        client.post(
            feedback,
            json={"feedback": "unclear", "feedback_key": result["feedback_key"]},
        ).status_code
        == 200
    )
    client.headers["Authorization"] = teacher_auth
    review = client.get("/portal/quality").json()["entries"][0]
    assert review["feedback"] == "unclear"
    assert all(
        secret not in json.dumps(review, ensure_ascii=False)
        for secret in [
            "Иван",
            "Петров",
            "example.org",
            session["subject"],
            "feedback_key",
        ]
    )
    assert (
        client.patch(
            f"/portal/quality/{review['id']}", json={"status": "resolved"}
        ).status_code
        == 200
    )
    assert client.get("/portal/quality").json()["entries"] == []
    client.headers["Authorization"] = "Bearer " + sec.put_token(
        "session", {**session, "course_id": session["course_id"] + 100000}, 120
    )
    assert client.get("/portal/quality?status=all").json()["entries"] == []
    client.headers["Authorization"] = teacher_auth
    db.execute(
        text("UPDATE portal_quality SET day=CURRENT_DATE-31 WHERE id=:id"),
        {"id": result["review_id"]},
    )
    db.commit()
    assert client.get("/portal/quality?status=all").json()["entries"] == []
    monkeypatch.setattr(
        course_quality,
        "redact",
        lambda _: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    student(client, session)
    assert (
        "review_id"
        not in client.post(
            "/portal/chat", json={**question, "share_for_review": True}
        ).json()
    )
    assert (
        db.execute(
            text("SELECT COUNT(*) FROM portal_quality WHERE course_id=:id"),
            {"id": session["course_id"]},
        ).scalar()
        == 0
    )


def test_study_answer_hidden_policy_and_owner(pilot, monkeypatch):
    client, db, session = pilot
    doc = upload(client)
    chunk = client.get(f"/portal/materials/{doc}").json()["chunks"][0]["id"]
    teacher_auth = client.headers["Authorization"]
    exercise = {
        "question": "Как растения получают энергию?",
        "expected_answer": "Энергия света",
        "hints": ["Подумайте о хлорофилле", "Какую энергию он поглощает?"],
        "explanation": "Хлорофилл поглощает свет.",
        "citations": [chunk],
    }
    monkeypatch.setattr(
        portal, "chat_completion_json", lambda *a, **k: json.dumps(exercise)
    )
    student(client, session)
    response = client.post("/portal/study", json={"message": "Фотосинтез"})
    assert response.status_code == 200, response.text
    state = response.json()
    path = f"/portal/study/{state['id']}"
    assert (
        "expected_answer" not in response.text and "Энергия света" not in response.text
    )
    assert client.post(path + "/solution").status_code == 403
    monkeypatch.setattr(
        portal, "chat_completion_json", lambda *a, **k: '{"correct":false}'
    )
    result = client.post(path + "/attempt", json={"answer": "От воды"}).json()
    assert (
        result["attempts"] == 1
        and result["hint"] == exercise["hints"][0]
        and not result["can_reveal"]
    )
    client.headers["Authorization"] = "Bearer " + sec.put_token(
        "session", {**session, "subject": "other-student", "role": "student"}, 120
    )
    assert client.post(path + "/attempt", json={"answer": "Свет"}).status_code == 404
    client.headers["Authorization"] = teacher_auth
    client.put(
        "/portal/preferences",
        json={
            "quality_enabled": False,
            "allow_solutions": True,
            "solution_after_attempts": 2,
        },
    )
    student(client, session)
    assert client.post(path + "/solution").status_code == 403
    assert client.post(path + "/attempt", json={"answer": "Свет"}).json()["can_reveal"]
    assert (
        client.post(path + "/solution").json()["answer"] == exercise["expected_answer"]
    )
    client.headers["Authorization"] = teacher_auth
    client.patch(f"/portal/materials/{doc}", json={"published": False})
    student(client, session)
    assert client.post(path + "/solution").status_code == 404


def test_stream_final_validation_and_failure(pilot, monkeypatch):
    from backend.app.routers import portal_workspace

    client, db, session = pilot
    doc = upload(client)
    chunk = client.get(f"/portal/materials/{doc}").json()["chunks"][0]["id"]

    async def provider(_):
        yield '{"citations":[' + str(chunk) + '],"answer":"Ответ '
        yield 'по источнику"}'

    monkeypatch.setattr(portal_workspace, "stream_completion", provider)
    response = client.post("/portal/chat/stream", json={"message": "Фотосинтез"})
    events = [json.loads(line) for line in response.text.splitlines()]
    assert any(e["event"] == "draft" for e in events)
    assert events[-1]["event"] == "result"
    assert events[-1]["result"]["citations"][0]["chunk_id"] == chunk

    async def broken(_):
        yield '{"citations":[' + str(chunk) + '],"answer":"Черновик'
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(portal_workspace, "stream_completion", broken)
    events = [
        json.loads(line)
        for line in client.post(
            "/portal/chat/stream", json={"message": "Фотосинтез"}
        ).text.splitlines()
    ]
    assert events[-1]["event"] == "error"
    assert not any(e["event"] == "result" for e in events)


def test_import_modules_files_and_revocation(pilot, monkeypatch, database):
    from backend.app.routers import portal_imports

    client, db, session = pilot
    monkeypatch.setattr(portal_imports, "SessionLocal", database)
    module = {"id": 1, "published": True, "name": "Глава 1", "position": 1}

    def listing(path, params=None):
        if path.endswith("/modules"):
            return [module]
        if path.endswith("/items"):
            return [
                {"id": 11, "type": "Page", "page_url": "intro", "position": 1},
                {"id": 12, "type": "File", "content_id": 8, "position": 2},
            ]
        if path.endswith("/files"):
            return [
                {"id": 8, "filename": "reading.txt"},
                {"id": 9, "filename": "hidden.pdf"},
            ]
        raise AssertionError(path)

    monkeypatch.setattr(portal.canvas_client, "get_all", listing)
    monkeypatch.setattr(
        portal.canvas_client,
        "list_pages",
        lambda _: [{"url": "intro", "title": "Введение"}],
    )
    monkeypatch.setattr(
        portal.canvas_client,
        "get_page",
        lambda *a: {
            "published": True,
            "body": "<p>Фотосинтез преобразует энергию света в химическую энергию органических веществ.</p>",
        },
    )
    monkeypatch.setattr(
        portal.canvas_client,
        "get_file",
        lambda course, fid: {
            "id": fid,
            "filename": "reading.txt",
            "updated_at": "2026-09-19",
            "size": 40,
            "hidden": fid == 9,
            "url": "https://canvas.test/file",
        },
    )
    monkeypatch.setattr(
        portal_imports,
        "download_image",
        lambda *a, **k: (
            "Фотосинтез использует энергию света для образования органических веществ.".encode()
        ),
    )
    monkeypatch.setattr(
        portal.canvas_client,
        "get_one",
        lambda path: (
            module if path.endswith("/1") else {"page_url": "intro", "content_id": 8}
        ),
    )
    assert client.post("/portal/imports").status_code == 200
    report = client.get("/portal/imports/latest").json()
    assert report["status"] == "complete" and report["progress"] == 3
    assert [r["status"] for r in report["details"]] == [
        "imported",
        "imported",
        "skipped",
    ]
    docs = client.get("/portal/materials").json()
    assert len(docs) == 2 and all(
        d["module_name"] == "Глава 1" and not d["published"] for d in docs
    )
    for d in docs:
        assert (
            client.patch(
                f"/portal/materials/{d['document_id']}", json={"published": True}
            ).status_code
            == 200
        )
    assert client.post("/portal/imports").status_code == 200
    assert len(client.get("/portal/materials").json()) == 2
    for d in docs:
        client.patch(f"/portal/materials/{d['document_id']}", json={"published": True})
    module["require_sequential_progress"] = True
    student(client, session)
    assert client.get("/portal/materials").json() == []
    assert client.get("/portal/imports/latest").status_code == 403
