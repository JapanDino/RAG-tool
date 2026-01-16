from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict

from ..schemas.llm import LLMAnnotation
from ..utils.bloom import annotate_bloom
from ..utils.prompt import build_bloom_prompt
from .openai_client import chat_completion_json


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def annotate(self, chunk: str, level: str, rubric: str | None = None) -> Dict[str, Any]:
        raise NotImplementedError

    def supports_streaming(self) -> bool:
        return False


class HeuristicProvider(LLMProvider):
    name = "heuristic"

    def annotate(self, chunk: str, level: str, rubric: str | None = None) -> Dict[str, Any]:
        return annotate_bloom(chunk, level, rubric)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, model: str):
        self.model = model

    def annotate(self, chunk: str, level: str, rubric: str | None = None) -> Dict[str, Any]:
        prompt = build_bloom_prompt(chunk, level, rubric)
        js = chat_completion_json(self.model, prompt, max_tokens=400)
        data = _parse_json(js)
        obj = LLMAnnotation(**data)
        return obj.model_dump()


def _parse_json(s: str) -> Dict[str, Any]:
    s = s.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
    return json.loads(s)


def get_provider(name: str, model: str, has_openai_key: bool) -> LLMProvider:
    if name in ("noop", "heuristic"):
        return HeuristicProvider()
    if name == "openai" and has_openai_key:
        return OpenAIProvider(model)
    return HeuristicProvider()


__all__ = ["LLMProvider", "HeuristicProvider", "OpenAIProvider", "get_provider"]

