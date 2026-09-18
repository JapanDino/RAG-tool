import json

from backend.app.services.course_extraction import extract_entities_with_provider


def test_structured_llm_entity_extraction_requires_exact_quotes(monkeypatch):
    text = "После модуля студент сможет анализировать временную сложность. Сравните два алгоритма."
    monkeypatch.setenv("COURSE_ENTITY_EXTRACTOR", "llm")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(
        "backend.app.services.course_extraction.chat_completion_json",
        lambda *args, **kwargs: json.dumps(
            {
                "objectives": [
                    {
                        "text": "После модуля студент сможет анализировать временную сложность",
                        "confidence": 0.94,
                    }
                ],
                "assessments": [{"text": "Сравните два алгоритма", "confidence": 0.88}],
            },
            ensure_ascii=False,
        ),
    )
    objectives, assessments, provider = extract_entities_with_provider(text, "unknown")
    assert provider == "llm"
    assert objectives[0].method == "objective-llm-structured-v1"
    assert assessments[0].method == "assessment-llm-structured-v1"
    assert text[objectives[0].start : objectives[0].end] == objectives[0].text


def test_invalid_llm_output_falls_back_to_deterministic_baseline(monkeypatch):
    text = "После модуля студент сможет анализировать временную сложность."
    monkeypatch.setenv("COURSE_ENTITY_EXTRACTOR", "llm")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only")
    monkeypatch.setattr(
        "backend.app.services.course_extraction.chat_completion_json",
        lambda *args, **kwargs: '{"objectives":[{"text":"invented quote","confidence":0.9}]}',
    )
    objectives, assessments, provider = extract_entities_with_provider(
        text, "learning_objectives"
    )
    assert provider == "baseline-fallback"
    assert objectives
    assert objectives[0].method == "objective-rule-v1"
