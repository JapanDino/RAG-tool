import os
import time
from typing import Any, Dict

from ..utils.bloom import annotate_bloom
from .llm_provider import HeuristicProvider, get_provider

ENABLE_LLM = os.getenv("ENABLE_LLM", "0") not in ("0", "false", "False")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "heuristic")  # noop|heuristic|openai
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

def llm_annotate(
    chunk: str, level: str, rubric: str | None = None, retries: int = 2, backoff: float = 0.8
) -> Dict[str, Any]:
    """
    Возвращает dict, совместимый с LLMAnnotation (level/label/rationale/score).
    Поведение зависит от LLM_PROVIDER; всегда валидируем LLM ответом pydantic'ом.
    """
    provider = get_provider(LLM_PROVIDER, LLM_MODEL, bool(OPENAI_API_KEY))
    if not ENABLE_LLM:
        provider = HeuristicProvider()

    if isinstance(provider, HeuristicProvider):
        return provider.annotate(chunk, level, rubric)

    for i in range(retries + 1):
        try:
            return provider.annotate(chunk, level, rubric)
        except Exception:
            time.sleep(backoff * (i + 1))
    return annotate_bloom(chunk, level, rubric)
