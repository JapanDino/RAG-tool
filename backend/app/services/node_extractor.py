from __future__ import annotations

import json
import os
import re
import warnings
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Sequence

from ..utils.node_extract import extract_nodes_from_text as heuristic_extract

try:
    from razdel import sentenize as _razdel_sentenize  # type: ignore
    _HAS_RAZDEL = True
except ImportError:
    _HAS_RAZDEL = False

# Known Russian/Latin abbreviation roots that end with a dot but are NOT sentence ends.
_ABBREV_ROOT_RE = re.compile(
    r"\b(?:рис|табл|стр|проф|доц|акад|ул|пр|кв|гл|разд|см|ср|напр|д-р|mr|dr|no|vs)$",
    re.IGNORECASE,
)
# Matches the word (sequence of word chars) immediately before a punctuation position.
_TRAILING_WORD_RE = re.compile(r"(\w+)$")
# Sentence-ending punctuation (excl. lone dot — handled with boundary logic below).
_HARD_PUNCT_RE = re.compile(r"[!?]+|\.{3,}")
# Single dot or dot-runs as a potential sentence boundary.
_DOT_RE = re.compile(r"\.+")
# A blank line is always a paragraph/sentence boundary.
_BLANK_LINE_RE = re.compile(r"\n{2,}")


def _is_sentence_boundary_dot(text: str, dot_start: int) -> bool:
    """Heuristic: is the dot at *dot_start* a sentence-ending dot (not an abbreviation)?"""
    before = text[:dot_start]
    word_m = _TRAILING_WORD_RE.search(before)
    if not word_m:
        return True  # dot after non-word char → treat as boundary
    word = word_m.group(1)
    # Single letter: initial (А.) or abbreviation (т., д.)
    if len(word) == 1 and word.isalpha():
        return False
    # Known abbreviation roots
    if _ABBREV_ROOT_RE.search(word):
        return False
    # Digit followed by dot before lowercase is a list item, not sentence end
    if word.isdigit():
        after = text[dot_start + 1:]
        if re.match(r"\s+[а-яёa-z]", after):
            return False
    return True


def split_sentences_with_offsets(text: str) -> list[dict[str, Any]]:
    """Returns sentences with [start,end) character offsets (best-effort, Russian-aware)."""
    if _HAS_RAZDEL:
        out = []
        for sent in _razdel_sentenize(text):
            s = sent.text.strip()
            if s:
                out.append({"text": s, "start": sent.start, "end": sent.stop})
        return out

    # Fallback: collect split positions from hard punctuation + context-aware dots + blank lines.
    splits: list[int] = [0]  # start positions of each sentence
    n = len(text)

    for m in _HARD_PUNCT_RE.finditer(text):
        splits.append(m.end())
    for m in _DOT_RE.finditer(text):
        if _is_sentence_boundary_dot(text, m.start()):
            splits.append(m.end())
    for m in _BLANK_LINE_RE.finditer(text):
        splits.append(m.end())

    splits = sorted(set(splits))
    splits.append(n)

    out: list[dict[str, Any]] = []
    for i in range(len(splits) - 1):
        seg = text[splits[i]:splits[i + 1]].strip()
        if seg:
            # find actual start/end in original string
            start = text.index(seg, splits[i]) if seg in text[splits[i]:splits[i + 1]] else splits[i]
            out.append({"text": seg, "start": start, "end": start + len(seg)})
    return out


def locate_sentence(sentences: list[dict[str, Any]], char_pos: int) -> tuple[int, str]:
    for i, s in enumerate(sentences):
        if s["start"] <= char_pos < s["end"]:
            return i, s["text"]
    if sentences:
        return 0, sentences[0]["text"]
    return 0, ""


class NodeExtractor(ABC):
    name = "base"

    @abstractmethod
    def extract(self, text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
        raise NotImplementedError


class HeuristicExtractor(NodeExtractor):
    name = "heuristic"

    def extract(self, text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
        nodes = heuristic_extract(text, max_nodes=max_nodes, min_freq=min_freq)
        sentences = split_sentences_with_offsets(text)
        enriched = []
        for n in nodes:
            title = n.get("title", "")
            # Best-effort offsets: first match.
            m = re.search(re.escape(title), text, flags=re.IGNORECASE)
            if m:
                sent_idx, sent_text = locate_sentence(sentences, m.start())
                src = {"sentence_idx": sent_idx, "char_start": m.start(), "char_end": m.end()}
                context = sent_text[:240]
            else:
                src = {"sentence_idx": 0, "char_start": None, "char_end": None}
                context = (n.get("context_snippet") or "")[:240]
            enriched.append(
                {
                    "title": title,
                    "context_snippet": context,
                    "frequency": int(n.get("frequency") or 1),
                    "node_type": n.get("node_type") or "keyword",
                    "source": src,
                }
            )
        return enriched


class NatashaNerExtractor(NodeExtractor):
    name = "local_ner"

    def __init__(self):
        try:
            from natasha import (  # type: ignore
                Doc,
                Segmenter,
                MorphVocab,
                NewsEmbedding,
                NewsNERTagger,
            )
        except Exception as e:  # pragma: no cover
            raise RuntimeError("natasha is required for NODE_EXTRACTOR=local_ner") from e

        self._Doc = Doc
        self._segmenter = Segmenter()
        self._morph = MorphVocab()
        self._emb = NewsEmbedding()
        self._tagger = NewsNERTagger(self._emb)

    def extract(self, text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
        sentences = split_sentences_with_offsets(text)

        doc = self._Doc(text)
        doc.segment(self._segmenter)
        doc.tag_ner(self._tagger)

        ner_spans = getattr(doc, "spans", None)
        if ner_spans is None:
            ner = getattr(doc, "ner", None)
            ner_spans = getattr(ner, "spans", []) if ner is not None else []

        spans = []
        for s in ner_spans:
            try:
                s.normalize(self._morph)
                title = s.normal or s.text
            except Exception:
                title = s.text
            if not title or len(title.strip()) < 3:
                continue
            spans.append((title.strip(), s.start, s.stop, getattr(s, "type", None)))

        # If NER found too little, fall back to heuristics to meet UX expectations.
        if not spans:
            return HeuristicExtractor().extract(text, max_nodes=max_nodes, min_freq=min_freq)

        # Dedup and rank by frequency (simple count by substring).
        uniq: dict[str, dict[str, Any]] = {}
        lowered = text.lower()
        for title, start, end, ent_type in spans:
            key = title.lower()
            if key in uniq:
                continue
            freq = lowered.count(key)
            if freq < min_freq:
                continue
            sent_idx, sent_text = locate_sentence(sentences, start)
            node_type = "proper_noun" if ent_type in ("PER", "LOC", "ORG") else "concept"
            uniq[key] = {
                "title": title,
                "context_snippet": sent_text[:240],
                "frequency": max(freq, 1),
                "node_type": node_type,
                "source": {"sentence_idx": sent_idx, "char_start": start, "char_end": end},
            }

        items = list(uniq.values())
        items.sort(key=lambda x: int(x.get("frequency") or 1), reverse=True)
        items = items[:max_nodes]

        # Only fill remaining slots with proper nouns from heuristics, not generic keywords
        if len(items) < max_nodes:
            extra = HeuristicExtractor().extract(
                text,
                max_nodes=max_nodes,
                min_freq=min_freq,
            )
            seen = {str(x["title"]).lower() for x in items}
            for e in extra:
                if e.get("node_type") != "proper_noun":
                    continue
                key = str(e.get("title", "")).lower()
                if not key or key in seen:
                    continue
                items.append(e)
                seen.add(key)
                if len(items) >= max_nodes:
                    break

        return items


_LLM_NODE_PROMPT = """\
Ты — ассистент по анализу образовательного контента.
Прочитай текст ниже и выдели из него ключевые смысловые единицы:
концепты, термины, научные законы, формулы, навыки и имена собственные.

Верни результат строго в виде JSON-массива объектов:
[
  {{"title": "краткое название концепта", "context": "предложение или фраза из текста, где встречается концепт"}},
  ...
]

Правила:
- Не более {max_nodes} элементов.
- Каждый title — краткое существительное или именная группа (1–5 слов).
- context — дословная цитата из текста (не перефразировать).
- Без пояснений, только JSON.

ТЕКСТ:
{text}
"""


class LLMNodeExtractor(NodeExtractor):
    """Extracts knowledge nodes via LLM with fallback to NatashaNerExtractor."""

    name = "llm"

    def extract(self, text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        if not api_key:
            warnings.warn("NODE_EXTRACTOR=llm but OPENAI_API_KEY is not set; falling back to local_ner", RuntimeWarning)
            return _ner_fallback(text, max_nodes, min_freq)

        from ..services.openai_client import chat_completion_json  # avoid circular import at module level

        prompt = _LLM_NODE_PROMPT.format(text=text[:4000], max_nodes=max_nodes)
        try:
            js = chat_completion_json(model, prompt, max_tokens=800)
            raw: list[dict[str, Any]] = json.loads(js)
            if not isinstance(raw, list):
                raise ValueError("Expected JSON array")
        except Exception as exc:
            warnings.warn(f"LLMNodeExtractor failed ({exc}); falling back to local_ner", RuntimeWarning)
            return _ner_fallback(text, max_nodes, min_freq)

        sentences = split_sentences_with_offsets(text)
        enriched: list[dict[str, Any]] = []
        seen: set[str] = set()
        lowered = text.lower()

        for item in raw:
            title = str(item.get("title") or "").strip()
            if not title or len(title) < 2:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)

            context_hint = str(item.get("context") or "").strip()
            m = re.search(re.escape(title), text, flags=re.IGNORECASE)
            if m:
                sent_idx, sent_text = locate_sentence(sentences, m.start())
                src = {"sentence_idx": sent_idx, "char_start": m.start(), "char_end": m.end()}
                context = sent_text[:240] or context_hint[:240]
            else:
                src = {"sentence_idx": 0, "char_start": None, "char_end": None}
                context = context_hint[:240]

            freq = max(lowered.count(key), 1)
            enriched.append({
                "title": title,
                "context_snippet": context,
                "frequency": freq,
                "node_type": "concept",
                "source": src,
            })
            if len(enriched) >= max_nodes:
                break

        return enriched if enriched else _ner_fallback(text, max_nodes, min_freq)


def _ner_fallback(text: str, max_nodes: int, min_freq: int) -> list[dict[str, Any]]:
    try:
        return NatashaNerExtractor().extract(text, max_nodes=max_nodes, min_freq=min_freq)
    except Exception:
        return HeuristicExtractor().extract(text, max_nodes=max_nodes, min_freq=min_freq)


@lru_cache(maxsize=1)
def get_node_extractor() -> NodeExtractor:
    name = os.getenv("NODE_EXTRACTOR", "local_ner").strip().lower()
    if name == "local_ner":
        try:
            return NatashaNerExtractor()
        except Exception as exc:
            warnings.warn(
                f"Falling back to heuristic extraction because local NER is unavailable: {exc}",
                RuntimeWarning,
                stacklevel=2,
            )
            return HeuristicExtractor()
    if name == "heuristic":
        return HeuristicExtractor()
    if name == "llm":
        return LLMNodeExtractor()
    raise RuntimeError(f"Unknown NODE_EXTRACTOR: {name}")


def extract_nodes(text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
    return get_node_extractor().extract(text, max_nodes=max_nodes, min_freq=min_freq)
