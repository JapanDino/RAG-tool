from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Sequence

from ..utils.node_extract import extract_nodes_from_text as heuristic_extract


SENT_SPLIT_RE = re.compile(r"[.!?\\n]+")


def split_sentences_with_offsets(text: str) -> list[dict[str, Any]]:
    """
    Returns sentences with [start,end) offsets (best-effort).
    """
    out = []
    idx = 0
    for m in SENT_SPLIT_RE.finditer(text):
        end = m.start()
        sent = text[idx:end].strip()
        if sent:
            out.append({"text": sent, "start": idx, "end": end})
        idx = m.end()
    tail = text[idx:].strip()
    if tail:
        out.append({"text": tail, "start": idx, "end": len(text)})
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

        if len(items) < max_nodes:
            # Fill remaining slots with heuristic keywords (concepts, skills, etc.)
            extra = HeuristicExtractor().extract(
                text,
                max_nodes=max_nodes,
                min_freq=min_freq,
            )
            seen = {str(x["title"]).lower() for x in items}
            for e in extra:
                key = str(e.get("title", "")).lower()
                if not key or key in seen:
                    continue
                items.append(e)
                seen.add(key)
                if len(items) >= max_nodes:
                    break

        return items


@lru_cache(maxsize=1)
def get_node_extractor() -> NodeExtractor:
    name = os.getenv("NODE_EXTRACTOR", "local_ner").strip().lower()
    if name == "local_ner":
        return NatashaNerExtractor()
    if name == "heuristic":
        return HeuristicExtractor()
    # LLM extractor is optional; not enabled by default.
    if name == "llm":  # pragma: no cover
        raise RuntimeError("NODE_EXTRACTOR=llm is not implemented yet")
    raise RuntimeError(f"Unknown NODE_EXTRACTOR: {name}")


def extract_nodes(text: str, max_nodes: int = 30, min_freq: int = 1) -> list[dict[str, Any]]:
    return get_node_extractor().extract(text, max_nodes=max_nodes, min_freq=min_freq)
