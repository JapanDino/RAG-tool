import json
import os
import time
from typing import Any, Dict

from ..schemas.llm import LLMAnnotation
from ..utils.prompt import build_bloom_prompt
from ..utils.bloom import annotate_bloom
from .openai_client import chat_completion_json

ENABLE_LLM = os.getenv("ENABLE_LLM", "0") not in ("0", "false", "False")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "heuristic")  # noop|heuristic|openai
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def _parse_json(s: str) -> Dict[str, Any]:
    # вырезаем возможный ```json ... ```
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    return json.loads(s)

def llm_annotate(
    chunk: str, level: str, rubric: str | None = None, retries: int = 2, backoff: float = 0.8
) -> Dict[str, Any]:
    """
    Возвращает dict, совместимый с LLMAnnotation (level/label/rationale/score).
    Поведение зависит от LLM_PROVIDER; всегда валидируем LLM ответом pydantic'ом.
    """
    if not ENABLE_LLM or LLM_PROVIDER in ("noop", "heuristic"):
        return annotate_bloom(chunk, level, rubric)

    if LLM_PROVIDER == "openai":
        if not OPENAI_API_KEY:
            return annotate_bloom(chunk, level, rubric)
        prompt = build_bloom_prompt(chunk, level, rubric)
        for i in range(retries + 1):
            try:
                js = chat_completion_json(LLM_MODEL, prompt, max_tokens=400)
                data = _parse_json(js)
                obj = LLMAnnotation(**data)
                return obj.model_dump()
            except Exception:
                time.sleep(backoff * (i + 1))
        return annotate_bloom(chunk, level, rubric)

    return annotate_bloom(chunk, level, rubric)
