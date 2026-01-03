from backend.app.schemas.llm import LLMAnnotation
import pytest

def test_llm_annotation_schema_ok():
    obj = LLMAnnotation(level="apply", label="Применение", rationale="ok", score=0.9)
    assert obj.level == "apply"

def test_llm_annotation_schema_bad_score():
    with pytest.raises(Exception):
        LLMAnnotation(level="apply", label="X", rationale="Y", score=1.5)
