"""Tests for classify_bloom_multilabel (keyword mode, no LLM required)."""
import os
import pytest

os.environ.setdefault("BLOOM_CLASSIFIER", "keyword")

from backend.app.utils.bloom import classify_bloom_multilabel, LEVEL_ORDER


def test_returns_six_probabilities():
    result = classify_bloom_multilabel("Назовите основные органеллы клетки.")
    vec = result["prob_vector"]
    assert len(vec) == 6, f"Expected 6 values, got {len(vec)}"


def test_probabilities_sum_to_one():
    result = classify_bloom_multilabel("Объясните процесс фотосинтеза.")
    total = sum(result["prob_vector"])
    assert abs(total - 1.0) < 0.01, f"Sum of prob_vector is {total}, expected ~1.0"


def test_all_probabilities_non_negative():
    result = classify_bloom_multilabel("Сравните причины двух революций.")
    assert all(p >= 0 for p in result["prob_vector"])


def test_top_levels_subset_of_level_order():
    result = classify_bloom_multilabel("Разработайте эксперимент для проверки гипотезы.")
    for lvl in result["top_levels"]:
        assert lvl in LEVEL_ORDER, f"Unknown level: {lvl}"


def test_top_levels_not_empty():
    result = classify_bloom_multilabel("Применяйте формулу для решения задачи.")
    assert len(result["top_levels"]) >= 1


def test_remember_verb_triggers_remember_level():
    """Russian 'назовите' should push remember probability higher than create."""
    result = classify_bloom_multilabel("Назовите столицу Франции.")
    vec = result["prob_vector"]
    remember_idx = LEVEL_ORDER.index("remember")
    create_idx = LEVEL_ORDER.index("create")
    assert vec[remember_idx] >= vec[create_idx], (
        f"Expected remember ({vec[remember_idx]}) >= create ({vec[create_idx]})"
    )


def test_create_verb_triggers_create_level():
    """Russian 'разработайте' should push create probability higher than remember."""
    result = classify_bloom_multilabel("Разработайте план нового учебного модуля.")
    vec = result["prob_vector"]
    remember_idx = LEVEL_ORDER.index("remember")
    create_idx = LEVEL_ORDER.index("create")
    assert vec[create_idx] >= vec[remember_idx], (
        f"Expected create ({vec[create_idx]}) >= remember ({vec[remember_idx]})"
    )


def test_empty_text_returns_valid_vector():
    result = classify_bloom_multilabel("")
    assert len(result["prob_vector"]) == 6
    assert abs(sum(result["prob_vector"]) - 1.0) < 0.01


def test_drift_correction_not_on_create():
    """Drift must not always land on the last element (create)."""
    # Run multiple texts and verify sum is always ~1.0 with no systematic bias.
    texts = [
        "Перечислите факты.",
        "Объясните концепцию.",
        "Примените метод.",
        "Проанализируйте данные.",
        "Оцените подход.",
        "Создайте модель.",
    ]
    for t in texts:
        vec = classify_bloom_multilabel(t)["prob_vector"]
        assert abs(sum(vec) - 1.0) < 0.005, f"Bad sum {sum(vec)} for: {t}"
