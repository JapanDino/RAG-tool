from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from ..schemas.schemas import BloomLevel
from ..services.openai_client import chat_completion_json
from ..utils.bloom import LEVEL_ORDER, classify_bloom_multilabel as keyword_classify
from ..utils.prompt import build_bloom_multilabel_prompt


class LLMClassifyOut(BaseModel):
    prob_vector: list[float] = Field(min_length=6, max_length=6)
    top_levels: list[BloomLevel] = Field(min_length=1)
    rationale: str = Field(min_length=1)


def _safe_float_list(v: Any) -> list[float]:
    return [float(x) for x in v]


def _normalize_probs(probs: list[float]) -> list[float]:
    s = sum(probs)
    if s <= 0:
        return [1.0 / 6.0] * 6
    return [p / s for p in probs]


def classify_bloom_multilabel(text: str, min_prob: float = 0.2, max_levels: int = 2) -> dict[str, Any]:
    """
    Hybrid bloom multi-label classifier.
    - keyword (default): offline baseline using `data/bloom_verbs_ru.json`
    - llm: OpenAI chat completion (falls back to keyword on any error)
    """
    mode = os.getenv("BLOOM_CLASSIFIER", "keyword").strip().lower()
    if mode != "llm":
        return keyword_classify(text, min_prob=min_prob, max_levels=max_levels)

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return keyword_classify(text, min_prob=min_prob, max_levels=max_levels)

    prompt = build_bloom_multilabel_prompt(text)
    js = chat_completion_json(model, prompt, max_tokens=450)
    try:
        data = json.loads(js)
        obj = LLMClassifyOut(**data)
    except (json.JSONDecodeError, ValidationError):
        return keyword_classify(text, min_prob=min_prob, max_levels=max_levels)

    probs = _normalize_probs(_safe_float_list(obj.prob_vector))
    probs = [round(p, 3) for p in probs]
    drift = round(1.0 - sum(probs), 3)
    if drift != 0:
        probs[-1] = round(probs[-1] + drift, 3)

    sorted_levels = sorted(zip(LEVEL_ORDER, probs), key=lambda x: x[1], reverse=True)
    top_levels = [lvl for lvl, p in sorted_levels if p >= min_prob][:max_levels]
    if not top_levels:
        top_levels = [sorted_levels[0][0]]

    return {
        "prob_vector": probs,
        "top_levels": top_levels,
        "rationale": obj.rationale,
        "triggers": {},
    }

