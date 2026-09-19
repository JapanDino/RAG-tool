"""Author-created regression cases, NOT an independently annotated benchmark."""

import json
from pathlib import Path

import pytest

from backend.app.services.bloom_rubric import classify_learning_demands
from backend.app.services.chunking import split_into_chunks
from backend.app.services.course_text import extract_course_html

CASES = [
    json.loads(line)
    for line in (Path(__file__).parents[1] / "data/bloom_rubric_cases.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_contextual_rubric_cases(case):
    result = classify_learning_demands(case["text"])
    assert result["levels"] == case["levels"]
    assert result["status"] == case["status"]
    assert set(case.get("knowledge", [])) <= set(result["knowledge"])
    assert "prob_vector" not in result
    for evidence in result["evidence"]:
        assert evidence["quote"] in case["text"]
        assert evidence["rule_id"] and evidence["rationale"]
        for quote in evidence["knowledge_evidence"].values():
            assert quote in evidence["quote"]


def test_exposition_does_not_change_the_task_demand():
    task = "Назовите столицу Франции."
    prose = "Модель создаёт прогноз. Исследователь оценивает структуру. "
    assert classify_learning_demands(prose + task)["levels"] == ["remember"]


def test_no_dependency_on_llm_or_fabricated_probabilities(monkeypatch):
    monkeypatch.setenv("BLOOM_CLASSIFIER", "llm")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = classify_learning_demands("Создайте оригинальную модель круговорота воды.")
    assert result["levels"] == ["create"]
    assert result["version"] == "rbt-context-1.0"


def test_ingestion_keeps_heading_separate_and_does_not_drop_short_tasks():
    source = "Учебные задания\n\nНазовите столицу Франции.\nОцените."
    chunks = split_into_chunks(source, preserve_paragraphs=True)
    assert len(chunks) == 1
    assert "задания\nНазовите" in chunks[0]
    assert chunks[0].endswith("Оцените.")
    result = classify_learning_demands(chunks[0])
    assert result["levels"] == ["remember"]
    assert result["status"] == "partial"


def test_canvas_blocks_preserve_tasks_but_inline_emphasis_does_not_split_them():
    html = "<h2>Задания</h2><p>Объясните <strong>роль хлорофилла</strong> в фотосинтезе.</p><p>Оцените.</p><script>Создайте новую модель клетки.</script>"
    extracted = extract_course_html(html)
    assert "Задания\nОбъясните роль хлорофилла в фотосинтезе." in extracted
    assert "Создайте" not in extracted
    chunk = split_into_chunks(extracted, preserve_paragraphs=True)[0]
    result = classify_learning_demands(chunk)
    assert result["levels"] == ["understand"]
    assert result["status"] == "partial"
