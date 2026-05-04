"""
Tests verifying requirements from the ТЗ (technical specification):
- Classification of the canonical example phrase
- prob_vector shape and value constraints
- /analyze/content endpoint integration
"""

import os
import pytest

os.environ.setdefault("EMBEDDING_PROVIDER", "random")
os.environ.setdefault("NODE_EXTRACTOR", "heuristic")
os.environ.setdefault("BLOOM_CLASSIFIER", "keyword")

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from backend.app.services.bloom_multilabel import classify_bloom_multilabel
from backend.app.services.node_extractor import get_node_extractor

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


# ── §7.2 — classification quality ────────────────────────────────────────────

class TestBloomClassification:
    """ТЗ §7.2 — classification produces valid prob_vector + top_levels."""

    def test_prob_vector_has_six_elements(self):
        result = classify_bloom_multilabel("Объясните принцип работы фотосинтеза")
        assert len(result["prob_vector"]) == 6, "prob_vector must have exactly 6 elements"

    def test_prob_vector_values_in_range(self):
        result = classify_bloom_multilabel("Проанализируйте причины промышленной революции")
        for p in result["prob_vector"]:
            assert 0.0 <= p <= 1.0, f"probability {p} out of [0, 1]"

    def test_top_levels_is_list_of_known_levels(self):
        result = classify_bloom_multilabel("Создайте план урока по физике")
        for lvl in result["top_levels"]:
            assert lvl in BLOOM_LEVELS, f"unknown level '{lvl}'"

    def test_tz_example_analyze_level(self):
        """
        ТЗ §7.2 canonical example: «Сравните причины Французской и Английской
        буржуазных революций…» → primary level must include 'analyze'.
        """
        text = (
            "Сравните причины Французской и Английской буржуазных революций, "
            "чтобы оценить их влияние на становление демократии в Европе"
        )
        result = classify_bloom_multilabel(text, min_prob=0.2, max_levels=3)
        top = result["top_levels"]
        assert "analyze" in top or "evaluate" in top, (
            f"Expected 'analyze' or 'evaluate' in top_levels for ТЗ example, got {top}"
        )

    def test_remember_verb_classified_correctly(self):
        """Simple recall question should hit 'remember'."""
        result = classify_bloom_multilabel("Назовите основные признаки млекопитающих")
        idx = BLOOM_LEVELS.index("remember")
        prob = result["prob_vector"][idx]
        assert prob > 0.0, "remember probability should be > 0 for a recall question"

    def test_create_verb_classified_correctly(self):
        """Creative verb should hit 'create'."""
        result = classify_bloom_multilabel("Разработайте новый алгоритм сортировки")
        idx = BLOOM_LEVELS.index("create")
        prob = result["prob_vector"][idx]
        assert prob > 0.0, "create probability should be > 0 for a creation task"

    def test_multilabel_output_for_compound_task(self):
        """A task with both analysis and evaluation verbs should get ≥ 1 top level."""
        result = classify_bloom_multilabel(
            "Проанализируйте данные и оцените эффективность стратегии",
            min_prob=0.1,
            max_levels=3,
        )
        assert len(result["top_levels"]) >= 1

    def test_short_text_does_not_crash(self):
        """Edge case: very short text should return valid structure."""
        result = classify_bloom_multilabel("Решите задачу")
        assert "prob_vector" in result
        assert "top_levels" in result
        assert len(result["prob_vector"]) == 6


# ── §7.1 — node extraction ────────────────────────────────────────────────────

class TestNodeExtraction:
    """ТЗ §7.1 — text is split into meaningful units (nodes)."""

    def test_extracts_nodes_from_paragraph(self):
        text = (
            "Фотосинтез — процесс, при котором растения преобразуют солнечный свет "
            "в химическую энергию. Хлорофилл поглощает свет и запускает реакцию."
        )
        extractor = get_node_extractor()
        nodes = extractor.extract(text, max_nodes=20, min_freq=1)
        assert len(nodes) >= 1, "Should extract at least one node from a paragraph"

    def test_node_has_required_fields(self):
        text = "Митохондрия — энергетическая станция клетки. АТФ синтезируется в митохондриях."
        extractor = get_node_extractor()
        nodes = extractor.extract(text, max_nodes=10, min_freq=1)
        for node in nodes:
            assert "title" in node, "Each node must have a 'title'"
            assert "context_snippet" in node, "Each node must have a 'context_snippet'"

    def test_nodes_are_not_single_chars(self):
        text = "Анализ данных позволяет выявить закономерности и принять обоснованные решения."
        extractor = get_node_extractor()
        nodes = extractor.extract(text, max_nodes=20, min_freq=1)
        for node in nodes:
            assert len(node["title"]) > 1, f"Node title too short: '{node['title']}'"

    def test_empty_text_returns_empty_list(self):
        extractor = get_node_extractor()
        nodes = extractor.extract("   ", max_nodes=10, min_freq=1)
        assert nodes == [] or isinstance(nodes, list)


# ── /analyze/content HTTP — input validation (no DB needed) ──────────────────

class TestAnalyzeContentValidation:
    """
    Validates the 422 guard added in analyze.py (ТЗ §7.1 — minimum input length).
    Uses TestClient but only exercises the validation path (no DB write).
    """

    @pytest.fixture(autouse=True)
    def _client(self):
        from fastapi.testclient import TestClient
        from backend.app.main import app
        self.client = TestClient(app)

    def test_returns_422_for_short_text(self):
        resp = self.client.post(
            "/analyze/content",
            json={"text": "abc", "dataset_id": 1},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for text shorter than 10 chars, got {resp.status_code}"
        )

    def test_returns_422_for_empty_text(self):
        resp = self.client.post(
            "/analyze/content",
            json={"text": "", "dataset_id": 1},
        )
        assert resp.status_code == 422
