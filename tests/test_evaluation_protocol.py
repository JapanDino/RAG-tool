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
    AuditRun,
    Chunk,
    Course,
    CourseQuestionAnswer,
    Dataset,
    Document,
)
from backend.app.services.course_qa import retrieve_student_tutor_context
from backend.app.services.evaluation_protocol import (
    evaluation_protocol_markdown,
    run_evaluation_protocol,
)


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session, Session()


def _seed(db):
    dataset = Dataset(name="evaluation-protocol")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Algorithms")
    db.add(course)
    db.flush()
    document = Document(
        dataset_id=dataset.id,
        title="Sorting",
        source="test://sorting",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "student_visible": True,
        },
    )
    db.add(document)
    db.flush()
    text = "Quicksort has average time complexity O(n log n)."
    chunk = Chunk(document_id=document.id, idx=0, text=text, meta={})
    db.add(chunk)
    db.flush()
    db.add(AuditRun(course_id=course.id, status="done"))
    answer = CourseQuestionAnswer(
        course_id=course.id,
        question="What is quicksort complexity?",
        answer="O(n log n).",
        citations=[
            {
                "source_id": "S1",
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_title": document.title,
                "quote": text,
                "source_url": document.source,
                "score": 0.9,
            }
        ],
        confidence=0.8,
        retrieval_method="hybrid:test",
        generation_provider="litellm",
    )
    db.add(answer)
    db.commit()
    return course, answer


def test_evaluation_protocol_is_reproducible_and_fails_on_tampered_citation():
    engine, _, db = _db()
    course, answer = _seed(db)
    first = run_evaluation_protocol(db, course)
    assert first.status == "passed"
    assert first.dataset_hash and len(first.dataset_hash) == 64
    assert first.metrics["retrieval"]["recall_at_k"] == 1.0
    assert first.metrics["retrieval"]["mrr"] == 1.0
    assert first.metrics["retrieval"]["abstention_accuracy"] == 1.0
    assert first.metrics["student_tutor"]["guard"]["accuracy"] == 1.0
    assert first.metrics["student_tutor"]["course_index"]["ready"] is True
    assert first.metrics["student_tutor"]["min_score"] == 0.12
    assert (
        first.metrics["student_tutor"]["retrieval_pipeline_version"]
        == "hybrid_bm25_embedding_module-v2"
    )
    assert first.metrics["student_tutor"]["citation_support"]["rate"] == 1.0
    assert (
        first.metrics["student_tutor"]["citation_support"]["semantic_entailment_proven"]
        is False
    )
    assert first.metrics["student_tutor"]["latency"]["p95_ms"] <= 250.0
    assert first.protocol_version == "course-quality-evaluation-v2"
    assert first.metrics["citations"]["integrity_rate"] == 1.0
    assert first.metrics["operations"]["audit_success_rate"] == 1.0
    assert all(item["passed"] is not False for item in first.checks)
    markdown = evaluation_protocol_markdown(first, course)
    assert "Программа и методика испытаний" in markdown
    assert "Tutor retrieval Recall@K" in markdown
    assert "Assessment guard accuracy" in markdown
    assert "лексический proxy" in markdown
    assert "synthetic regression" in markdown

    answer.citations = [{**answer.citations[0], "quote": "Invented quote"}]
    db.commit()
    second = run_evaluation_protocol(db, course)
    assert second.status == "failed"
    citation_check = next(
        item for item in second.checks if item["check_id"] == "citation_integrity"
    )
    assert citation_check["passed"] is False
    db.close()
    engine.dispose()


def test_evaluation_protocol_fails_for_empty_student_tutor_index():
    engine, _, db = _db()
    dataset = Dataset(name="empty-tutor-index")
    db.add(dataset)
    db.flush()
    course = Course(dataset_id=dataset.id, title="Empty course")
    db.add(course)
    db.commit()

    protocol = run_evaluation_protocol(db, course)
    assert protocol.status == "failed"
    readiness = next(
        item
        for item in protocol.checks
        if item["check_id"] == "course_tutor_index_ready"
    )
    assert readiness["required"] is True
    assert readiness["passed"] is False
    assert protocol.metrics["student_tutor"]["course_index"] == {
        "ready": False,
        "student_visible_documents": 0,
        "indexed_chunks": 0,
        "smoke_hit": False,
        "retrieval_method": None,
        "seed_chunk_id": None,
        "effective_min_score": 0.12,
        "effective_max_candidates": 500,
    }

    hidden = Document(
        dataset_id=dataset.id,
        title="Hidden lecture",
        source="test://hidden",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "student_visible": False,
        },
    )
    db.add(hidden)
    db.flush()
    db.add(
        Chunk(
            document_id=hidden.id,
            idx=0,
            text="This hidden material has meaningful retrieval terms.",
            meta={},
        )
    )
    db.commit()
    hidden_only = run_evaluation_protocol(db, course)
    assert hidden_only.status == "failed"
    assert (
        hidden_only.metrics["student_tutor"]["course_index"][
            "student_visible_documents"
        ]
        == 0
    )

    non_queryable = Document(
        dataset_id=dataset.id,
        title="Punctuation only",
        source="test://punctuation",
        status="ready",
        source_metadata={
            "document_type": "lecture_material",
            "student_visible": True,
        },
    )
    db.add(non_queryable)
    db.flush()
    db.add(Chunk(document_id=non_queryable.id, idx=0, text="!!!", meta={}))
    db.commit()
    non_retrievable = run_evaluation_protocol(db, course)
    assert non_retrievable.status == "failed"
    assert non_retrievable.metrics["student_tutor"]["course_index"] == {
        "ready": False,
        "student_visible_documents": 1,
        "indexed_chunks": 1,
        "smoke_hit": False,
        "retrieval_method": None,
        "seed_chunk_id": None,
        "effective_min_score": 0.12,
        "effective_max_candidates": 500,
    }
    db.close()
    engine.dispose()


def test_evaluation_protocol_uses_effective_runtime_retrieval_limits(monkeypatch):
    engine, _, db = _db()
    course, _ = _seed(db)
    monkeypatch.setenv("COURSE_COPILOT_MIN_SCORE", "0.99")
    monkeypatch.setenv("COURSE_COPILOT_MAX_CANDIDATES", "17")

    runtime_hits, _ = retrieve_student_tutor_context(
        db,
        course,
        "quicksort average time complexity",
    )
    assert runtime_hits == []

    protocol = run_evaluation_protocol(db, course)
    course_index = protocol.metrics["student_tutor"]["course_index"]
    assert protocol.status == "failed"
    assert course_index["ready"] is False
    assert course_index["effective_min_score"] == 0.99
    assert course_index["effective_max_candidates"] == 17
    readiness = next(
        item
        for item in protocol.checks
        if item["check_id"] == "course_tutor_index_ready"
    )
    assert readiness["passed"] is False
    db.close()
    engine.dispose()


def test_evaluation_protocol_redacts_invalid_dataset_error(monkeypatch, tmp_path):
    engine, _, db = _db()
    course, _ = _seed(db)
    invalid = tmp_path / "invalid-tutor-dataset.jsonl"
    invalid.write_text(
        '{"id":"secret-case","kind":"guard","query":"private input"}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STUDENT_TUTOR_EVAL_DATASET", str(invalid))

    protocol = run_evaluation_protocol(db, course)
    assert protocol.status == "error"
    assert protocol.metrics == {}
    assert "private input" not in protocol.error
    assert "secret-case" not in protocol.error
    assert "inspect server logs" in protocol.error
    db.close()
    engine.dispose()


def test_evaluation_protocol_api_persists_history_and_downloads():
    engine, Session, db = _db()
    course, _ = _seed(db)

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    created = client.post(f"/courses/{course.id}/evaluation-protocols")
    assert created.status_code == 201
    protocol_id = created.json()["id"]
    assert created.json()["status"] == "passed"
    history = client.get(f"/courses/{course.id}/evaluation-protocols")
    assert history.status_code == 200
    assert [item["id"] for item in history.json()] == [protocol_id]
    markdown = client.get(
        f"/evaluation-protocols/{protocol_id}/download?format=markdown"
    )
    assert markdown.status_code == 200
    assert (
        markdown.headers["content-disposition"]
        == f'attachment; filename="evaluation-protocol-{protocol_id}.md"'
    )
    payload = client.get(f"/evaluation-protocols/{protocol_id}/download?format=json")
    assert payload.status_code == 200
    assert payload.json()["dataset_hash"] == created.json()["dataset_hash"]
    app.dependency_overrides.clear()
    db.close()
    engine.dispose()
