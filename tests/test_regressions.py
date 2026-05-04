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
from backend.app.models.models import Dataset, KnowledgeNode, NodeLabel, NodeLabelRevision
from backend.app.routers import canvas as canvas_router
from backend.app.services import embedding_provider
from backend.app.services.bloom_multilabel import classify_bloom_multilabel as classify_bloom_service
from backend.app.services.chunking import split_into_chunks
from backend.app.routers import nodes as nodes_router
from backend.app.routers import search as search_router
from backend.app.utils.bloom import classify_bloom_multilabel as classify_bloom_keywords


def _setup_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return engine, Session


def test_export_labels_does_not_hide_non_current_embedding_model():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-export")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Fractions",
        context_text="Compare simple fractions",
        prob_vector=[0.1, 0.1, 0.6, 0.1, 0.05, 0.05],
        top_levels=["apply"],
        embedding_model="local:intfloat/multilingual-e5-small:padded1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    label = NodeLabel(node_id=node.id, labels=["apply"], annotator="teacher", source="human")
    db.add(label)
    db.commit()
    dataset_id = dataset.id
    db.close()

    resp = client.get(f"/datasets/{dataset_id}/labeling/export?annotator=teacher")
    assert resp.status_code == 200
    assert "Fractions" in resp.text
    assert "local:intfloat/multilingual-e5-small:padded1536" in resp.text

    app.dependency_overrides.clear()
    engine.dispose()


def test_evaluate_auto_prefers_stored_top_levels(monkeypatch):
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-eval")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Photosynthesis",
        context_text="Explain the role of chlorophyll",
        prob_vector=[0.05, 0.8, 0.05, 0.05, 0.03, 0.02],
        top_levels=["understand"],
        embedding_model="hash:v1:1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    label = NodeLabel(node_id=node.id, labels=["understand"], annotator="teacher", source="human")
    db.add(label)
    db.commit()
    dataset_id = dataset.id
    db.close()

    def should_not_be_used(*args, **kwargs):
        return {"top_levels": ["create"]}

    monkeypatch.setattr("backend.app.routers.evaluate.classify_bloom_multilabel", should_not_be_used)

    resp = client.get(
        f"/evaluate/metrics?dataset_id={dataset_id}&annotator=teacher&prediction_source=auto"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_source_requested"] == "auto"
    assert body["prediction_source"] == "stored_top_levels"
    assert body["stored_predictions"] == 1
    assert body["recomputed_predictions"] == 0
    assert body["f1_micro"] == 1.0

    app.dependency_overrides.clear()
    engine.dispose()


def test_evaluate_recompute_uses_current_classifier(monkeypatch):
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-eval-recompute")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Photosynthesis",
        context_text="Explain the role of chlorophyll",
        prob_vector=[0.05, 0.8, 0.05, 0.05, 0.03, 0.02],
        top_levels=["understand"],
        embedding_model="hash:v1:1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)

    label = NodeLabel(node_id=node.id, labels=["create"], annotator="teacher", source="human")
    db.add(label)
    db.commit()
    dataset_id = dataset.id
    db.close()

    def should_be_used(*args, **kwargs):
        return {"top_levels": ["create"]}

    monkeypatch.setattr("backend.app.routers.evaluate.classify_bloom_multilabel", should_be_used)

    resp = client.get(f"/evaluate/metrics?dataset_id={dataset_id}&annotator=teacher")
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_source_requested"] == "recompute"
    assert body["prediction_source"] == "current_classifier"
    assert body["stored_predictions"] == 0
    assert body["recomputed_predictions"] == 1
    assert body["f1_micro"] == 1.0

    app.dependency_overrides.clear()
    engine.dispose()


def test_local_embedding_provider_fails_closed_without_explicit_fallback(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.delenv("EMBEDDING_ALLOW_HASH_FALLBACK", raising=False)
    embedding_provider.get_embedding_provider.cache_clear()

    def fail_local_provider(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(embedding_provider, "LocalProvider", fail_local_provider)

    with pytest.raises(RuntimeError, match="hash fallback is disabled"):
        embedding_provider.get_embedding_provider()

    embedding_provider.get_embedding_provider.cache_clear()


def test_local_embedding_provider_can_explicitly_fallback_to_hash(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("EMBEDDING_ALLOW_HASH_FALLBACK", "1")
    embedding_provider.get_embedding_provider.cache_clear()

    def fail_local_provider(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(embedding_provider, "LocalProvider", fail_local_provider)

    provider = embedding_provider.get_embedding_provider()
    assert provider.embedding_model == "hash:v1:1536"

    embedding_provider.get_embedding_provider.cache_clear()


class _DummyMappingsResult:
    def mappings(self):
        return self

    def all(self):
        return []


class _DummyDB:
    def execute(self, *args, **kwargs):
        return _DummyMappingsResult()


def test_chunk_search_accepts_non_current_embedding_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "random")
    embedding_provider.get_embedding_provider.cache_clear()

    result = search_router.search(
        q="fractions",
        dataset_id=None,
        embedding_model="hash:v1:1536",
        top_k=5,
        dim=1536,
        db=_DummyDB(),
    )

    assert result == []
    embedding_provider.get_embedding_provider.cache_clear()


def test_node_search_accepts_non_current_embedding_model(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "random")
    embedding_provider.get_embedding_provider.cache_clear()

    result = nodes_router.search_nodes(
        q="fractions",
        dataset_id=None,
        embedding_model="hash:v1:1536",
        top_k=5,
        dim=1536,
        db=_DummyDB(),
    )

    assert result == []
    embedding_provider.get_embedding_provider.cache_clear()


def test_label_updates_create_auditable_history():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-label-history")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Fractions",
        context_text="Compare simple fractions",
        prob_vector=[0.1, 0.1, 0.6, 0.1, 0.05, 0.05],
        top_levels=["apply"],
        embedding_model="hash:v1:1536",
        model_info={},
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    node_id = node.id
    db.close()

    resp = client.post(
        f"/nodes/{node_id}/labels",
        json={"labels": ["apply"], "annotator": "teacher"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1

    resp = client.put(
        f"/nodes/{node_id}/labels",
        json={"labels": ["apply"], "annotator": "teacher"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 1

    resp = client.put(
        f"/nodes/{node_id}/labels",
        json={"labels": ["analyze"], "annotator": "teacher"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == 2
    assert resp.json()["updated_at"] is not None

    history_resp = client.get(f"/nodes/{node_id}/labels/history?annotator=teacher")
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert [row["version"] for row in history] == [1, 2]
    assert history[0]["labels"] == ["apply"]
    assert history[1]["labels"] == ["analyze"]

    db = Session()
    current = db.query(NodeLabel).filter(NodeLabel.node_id == node_id, NodeLabel.annotator == "teacher").one()
    revisions = (
        db.query(NodeLabelRevision)
        .filter(NodeLabelRevision.node_id == node_id, NodeLabelRevision.annotator == "teacher")
        .order_by(NodeLabelRevision.version.asc())
        .all()
    )
    assert current.version == 2
    assert len(revisions) == 2
    db.close()

    app.dependency_overrides.clear()
    engine.dispose()


def test_keyword_bloom_returns_no_top_levels_without_signal():
    # Text contains no Bloom verbs and no heuristic pattern triggers.
    # Deliberately avoids "описание" (understand keyword) and structural cue words.
    result = classify_bloom_keywords("Тема первого раздела рассматривается в контексте общего подхода.")
    assert result["top_levels"] == []
    assert result["rationale"] == "insufficient-signal"
    assert len(result["prob_vector"]) == 6
    assert round(sum(result["prob_vector"]), 3) == 1.0


def test_evaluate_scorable_only_excludes_review_needed_predictions():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-eval-scorable-only")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    good_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Debate",
        context_text="Compare two arguments and justify your choice",
        prob_vector=[0.05, 0.05, 0.1, 0.6, 0.1, 0.1],
        top_levels=["analyze"],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "verb-match"},
    )
    weak_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Course Overview",
        context_text="General orientation text",
        prob_vector=[1 / 6] * 6,
        top_levels=[],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "insufficient-signal"},
    )
    db.add_all([good_node, weak_node])
    db.commit()
    db.refresh(good_node)
    db.refresh(weak_node)

    db.add_all(
        [
            NodeLabel(node_id=good_node.id, labels=["analyze"], annotator="teacher", source="human"),
            NodeLabel(node_id=weak_node.id, labels=["understand"], annotator="teacher", source="human"),
        ]
    )
    db.commit()
    dataset_id = dataset.id
    db.close()

    resp = client.get(
        f"/evaluate/metrics?dataset_id={dataset_id}&annotator=teacher&prediction_source=stored&evaluation_scope=scorable_only"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["prediction_source_requested"] == "stored"
    assert body["evaluation_scope"] == "scorable_only"
    assert body["samples_considered"] == 2
    assert body["samples"] == 1
    assert body["review_needed_predictions"] == 1
    assert body["scorable_predictions"] == 1
    assert body["skipped_predictions"] == 1
    assert body["f1_micro"] == 1.0

    app.dependency_overrides.clear()
    engine.dispose()


def test_labeling_queue_surfaces_needs_review_and_supports_filtering():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-label-queue-review")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    needs_review_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Overview",
        context_text="General course overview",
        prob_vector=[1 / 6] * 6,
        top_levels=[],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "insufficient-signal"},
    )
    scorable_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Argument Essay",
        context_text="Compare two positions and justify your answer",
        prob_vector=[0.05, 0.05, 0.1, 0.6, 0.1, 0.1],
        top_levels=["analyze"],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "verb-match"},
    )
    db.add_all([needs_review_node, scorable_node])
    db.commit()
    dataset_id = dataset.id
    db.close()

    resp = client.get(f"/datasets/{dataset_id}/labeling/queue?annotator=teacher")
    assert resp.status_code == 200
    body = resp.json()
    assert body["needs_review"] == 1
    assert body["scorable"] == 1
    assert body["items"][0]["review_status"] == "needs_review"
    assert "insufficient-signal" in body["items"][0]["review_reasons"]

    filtered = client.get(
        f"/datasets/{dataset_id}/labeling/queue?annotator=teacher&review_status=needs_review"
    )
    assert filtered.status_code == 200
    filtered_body = filtered.json()
    assert len(filtered_body["items"]) == 1
    assert filtered_body["items"][0]["title"] == "Overview"

    app.dependency_overrides.clear()
    engine.dispose()


def test_label_export_supports_review_status_filter():
    engine, Session = _setup_db()

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    db = Session()
    dataset = Dataset(name="dataset-export-review-filter")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    weak_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Overview",
        context_text="General course overview",
        prob_vector=[1 / 6] * 6,
        top_levels=[],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "insufficient-signal"},
    )
    strong_node = KnowledgeNode(
        dataset_id=dataset.id,
        title="Essay",
        context_text="Compare two positions and justify your answer",
        prob_vector=[0.05, 0.05, 0.1, 0.6, 0.1, 0.1],
        top_levels=["analyze"],
        embedding_model="hash:v1:1536",
        model_info={"rationale": "verb-match"},
    )
    db.add_all([weak_node, strong_node])
    db.commit()
    db.refresh(weak_node)
    db.refresh(strong_node)

    db.add_all(
        [
            NodeLabel(node_id=weak_node.id, labels=["understand"], annotator="teacher", source="human"),
            NodeLabel(node_id=strong_node.id, labels=["analyze"], annotator="teacher", source="human"),
        ]
    )
    db.commit()
    dataset_id = dataset.id
    db.close()

    resp = client.get(
        f"/datasets/{dataset_id}/labeling/export?annotator=teacher&review_status=needs_review"
    )
    assert resp.status_code == 200
    assert "Overview" in resp.text
    assert "Essay" not in resp.text
    assert '"prediction_review_status": "needs_review"' in resp.text

    app.dependency_overrides.clear()
    engine.dispose()


def test_chunking_preserves_structured_canvas_markers():
    text = (
        "# Assignment: Essay\n\n"
        "## Description\n"
        "Write a short essay about climate policy.\n"
        "Use at least two sources.\n\n"
        "## Criteria\n"
        "- Compare two positions\n"
        "- Cite evidence"
    )

    chunks = split_into_chunks(text, min_len=10, max_chars=120, overlap_chars=0)

    assert chunks
    assert any("# Assignment: Essay" in chunk for chunk in chunks)
    assert any("## Description" in chunk for chunk in chunks)
    assert any("- Compare two positions" in chunk for chunk in chunks)
    assert any("\n\n## Criteria" in chunk or chunk.startswith("## Criteria") for chunk in chunks)


def test_canvas_quiz_text_includes_sections_and_answers():
    quiz = {
        "id": 7,
        "title": "Week 1 Quiz",
        "description": "<p>Select the best answer.</p>",
        "quiz_type": "assignment",
        "points_possible": 10,
    }
    questions = [
        {
            "question_name": "Addition",
            "question_text": "<p>What is 2 + 2?</p>",
            "answers": [{"text": "4"}, {"html": "<strong>5</strong>"}],
        }
    ]

    rendered = canvas_router._build_quiz_text(quiz, questions)

    assert "# Quiz: Week 1 Quiz" in rendered
    assert "## Description" in rendered
    assert "## Quiz Type" in rendered
    assert "## Question 1" in rendered
    assert "### Prompt" in rendered
    assert "### Answers" in rendered
    assert "- 4" in rendered
    assert "- 5" in rendered


def test_canvas_module_text_lists_items_with_types():
    module = {
        "id": 3,
        "name": "Week 1",
        "state": "active",
        "items": [
            {"title": "Intro Page", "type": "Page"},
            {"title": "Quiz 1", "type": "Quiz", "completion_requirement": {"type": "must_submit"}},
        ],
    }

    rendered = canvas_router._build_module_text(module)

    assert "# Module: Week 1" in rendered
    assert "## State" in rendered
    assert "## Items" in rendered
    assert "1. [Page] Intro Page" in rendered
    assert "2. [Quiz] Quiz 1 (completion: must_submit)" in rendered


def test_canvas_chunks_store_source_metadata():
    engine, Session = _setup_db()
    db = Session()

    dataset = Dataset(name="dataset-canvas-meta")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    doc, chunks = canvas_router._ensure_canvas_document_and_chunks(
        raw_text="# Announcement: Welcome\n\n## Message\nCourse starts Monday.",
        course_id=42,
        source_label="announcement:Welcome",
        source_meta={
            "canvas_type": "announcement",
            "source_title": "Welcome",
            "canvas_id": 99,
            "posted_at": "2026-05-04T10:00:00Z",
        },
        dataset_id=dataset.id,
        db=db,
    )

    assert doc.title == "Welcome"
    assert chunks
    assert chunks[0].meta["canvas_type"] == "announcement"
    assert chunks[0].meta["source_title"] == "Welcome"
    assert chunks[0].meta["canvas_id"] == 99
    assert chunks[0].meta["course_id"] == 42

    db.close()
    engine.dispose()


def test_canvas_process_document_classifies_with_structured_chunk(monkeypatch):
    engine, Session = _setup_db()
    db = Session()

    dataset = Dataset(name="dataset-canvas-bloom-input")
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    class DummyExtractor:
        name = "dummy"

        def extract(self, text: str, max_nodes: int = 30, min_freq: int = 1):
            return [{"title": "Climate Essay", "context_snippet": "Compare two positions"}]

    captured: dict[str, str] = {}

    def fake_classifier(text: str, min_prob: float, max_levels: int):
        captured["text"] = text
        return {
            "prob_vector": [0.1, 0.2, 0.2, 0.3, 0.1, 0.1],
            "top_levels": ["analyze"],
            "rationale": "structured-test",
        }

    def fail_embeddings(*args, **kwargs):
        raise RuntimeError("skip embeddings in sqlite test")

    monkeypatch.setattr(canvas_router, "classify_bloom_multilabel", fake_classifier)
    monkeypatch.setattr(canvas_router, "embed_texts", fail_embeddings)

    imported = canvas_router._process_document(
        raw_text=(
            "# Assignment: Climate Essay\n\n"
            "## Description\n"
            "Compare two positions on climate policy and cite evidence."
        ),
        course_id=42,
        source_label="assignment:Climate Essay",
        source_meta={"canvas_type": "assignment", "source_title": "Climate Essay"},
        dataset_id=dataset.id,
        max_nodes=10,
        min_prob=0.2,
        extractor=DummyExtractor(),
        embedding_model="hash:v1:1536",
        db=db,
        skipped=[],
    )

    assert imported is not None
    assert "Source" in captured["text"]
    assert "assignment / Climate Essay" in captured["text"]
    assert "Structured Context" in captured["text"]
    assert "# Assignment: Climate Essay" in captured["text"]
    assert "## Description" in captured["text"]

    db.close()
    engine.dispose()


def test_service_bloom_preserves_empty_top_levels_without_signal(monkeypatch):
    monkeypatch.setenv("BLOOM_CLASSIFIER", "keyword")
    result = classify_bloom_service("Тема первого раздела рассматривается в контексте общего подхода.")
    assert result["top_levels"] == []
    assert result["rationale"] == "insufficient-signal"
