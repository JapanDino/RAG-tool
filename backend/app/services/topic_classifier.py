"""
Topic classifier: assigns subject/topic/subtopic hierarchy to a text fragment.

Two modes:
  auto   — LLM freely infers the topic hierarchy from the text
  guided — LLM classifies against a user-supplied topic tree
"""
import os
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_AUTO_PROMPT = """\
Ты — ассистент по анализу образовательного контента.
Определи, к какому разделу учебной дисциплины относится следующий текст.

Верни ТОЛЬКО JSON-объект (без пояснений):
{{
  "subject": "название дисциплины или предмета (1-3 слова)",
  "topic": "раздел/тема внутри дисциплины (1-5 слов)",
  "subtopic": "конкретная подтема или null если не применимо (1-5 слов)"
}}

ТЕКСТ:
{text}
"""

_GUIDED_PROMPT = """\
Ты — ассистент по анализу образовательного контента.
Определи, к какому разделу из приведённого дерева тем относится следующий текст.
Выбирай ТОЛЬКО из предложенного дерева. Если текст не подходит ни к одной теме, укажи ближайшую.

ДЕРЕВО ТЕМ:
{tree}

Верни ТОЛЬКО JSON-объект (без пояснений):
{{
  "subject": "верхний уровень из дерева",
  "topic": "второй уровень из дерева или null",
  "subtopic": "третий уровень из дерева или null"
}}

ТЕКСТ:
{text}
"""


def _call_llm(prompt: str) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    if not api_key:
        return None
    try:
        from .openai_client import chat_completion_json
        js = chat_completion_json(model, prompt, max_tokens=200)
        data = json.loads(js)
        if not isinstance(data, dict):
            return None
        return {
            "subject": str(data.get("subject") or "").strip() or None,
            "topic": str(data.get("topic") or "").strip() or None,
            "subtopic": str(data.get("subtopic") or "").strip() or None,
        }
    except Exception as exc:
        logger.warning("topic_classifier failed: %s", exc)
        return None


def classify_topic_auto(text: str) -> dict[str, Any] | None:
    """Freely infer subject/topic/subtopic from text."""
    prompt = _AUTO_PROMPT.format(text=text[:2000])
    return _call_llm(prompt)


def classify_topic_guided(text: str, topic_tree: str) -> dict[str, Any] | None:
    """Classify text against a user-supplied topic tree (plain indented text)."""
    prompt = _GUIDED_PROMPT.format(tree=topic_tree[:3000], text=text[:2000])
    return _call_llm(prompt)


def classify_topic(
    text: str,
    mode: str,
    topic_tree: str | None = None,
) -> dict[str, Any] | None:
    """
    mode: 'auto' | 'guided' | 'none'
    topic_tree: indented text tree, required when mode='guided'
    """
    if mode == "auto":
        return classify_topic_auto(text)
    if mode == "guided" and topic_tree:
        return classify_topic_guided(text, topic_tree)
    return None
