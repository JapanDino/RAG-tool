from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path


LEVEL_ORDER = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z]+(?:-[А-Яа-яЁёA-Za-z]+)?")


@lru_cache(maxsize=1)
def _get_morph():
    """Return pymorphy3 analyser, or None if not installed."""
    try:
        import pymorphy3  # type: ignore
        return pymorphy3.MorphAnalyzer()
    except Exception:
        return None


def _normalize_text(text: str) -> str:
    """Tokenise text, lemmatise each word with pymorphy3 (if available)."""
    morph = _get_morph()
    if morph is None:
        return text.lower()
    tokens = _WORD_RE.findall(text)
    lemmas = []
    for tok in tokens:
        try:
            lemmas.append(morph.parse(tok)[0].normal_form)
        except Exception:
            lemmas.append(tok.lower())
    return " ".join(lemmas)


def annotate_bloom(chunk: str, level: str, rubric: str | None = None):
    """
    Keyword-based annotator. Uses classify_bloom_multilabel to get a real
    probability score for the requested Bloom level instead of a fake length heuristic.
    """
    _LABELS = {
        "remember":   "Факты",
        "understand": "Понимание",
        "apply":      "Применение",
        "analyze":    "Анализ",
        "evaluate":   "Оценивание",
        "create":     "Создание",
    }
    result = classify_bloom_multilabel(chunk)
    idx = LEVEL_ORDER.index(level) if level in LEVEL_ORDER else -1
    score = result["prob_vector"][idx] if idx >= 0 else round(1.0 / 6.0, 3)
    triggers = result.get("triggers", {}).get(level, [])
    if triggers:
        rationale = f"{level}: {', '.join(sorted(set(triggers))[:5])}"
    else:
        rationale = f"keyword-baseline: явных триггеров для «{level}» не найдено"
    return dict(
        level=level,
        label=_LABELS.get(level, "N/A"),
        rationale=rationale,
        score=round(score, 3),
    )


def _default_verbs_path() -> Path:
    # /app/backend/app/utils/bloom.py -> /app/data/bloom_verbs_ru.json
    return Path(__file__).resolve().parents[3] / "data" / "bloom_verbs_ru.json"


@lru_cache(maxsize=1)
def _load_keywords() -> dict[str, list[str]]:
    path = Path(os.getenv("BLOOM_VERBS_PATH", str(_default_verbs_path())))
    if not path.exists():
        # Safe fallback: minimal built-in keywords.
        return {
            "remember": ["назовите", "перечислите", "определите"],
            "understand": ["объясните", "почему", "сравните"],
            "apply": ["примените", "используйте", "решите"],
            "analyze": ["проанализируйте", "выделите", "сопоставьте"],
            "evaluate": ["оцените", "аргументируйте", "обоснуйте"],
            "create": ["создайте", "разработайте", "спроектируйте"],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for lvl in LEVEL_ORDER:
        out[lvl] = [str(x).lower() for x in data.get(lvl, []) if str(x).strip()]
    return out

@lru_cache(maxsize=1)
def _load_normalized_keywords() -> dict[str, list[str]]:
    """Load keywords pre-lemmatised so matching is morphology-aware."""
    morph = _get_morph()
    raw = _load_keywords()
    if morph is None:
        return raw
    out: dict[str, list[str]] = {}
    for lvl, kws in raw.items():
        normalized = []
        for kw in kws:
            tokens = _WORD_RE.findall(kw)
            try:
                lemmas = [morph.parse(t)[0].normal_form for t in tokens]
                normalized.append(" ".join(lemmas))
            except Exception:
                normalized.append(kw.lower())
        out[lvl] = normalized
    return out


def classify_bloom_multilabel(
    text: str,
    min_prob: float = 0.2,
    max_levels: int = 2,
):
    normalized = _normalize_text(text)
    counts = []
    triggers: dict[str, list[str]] = {lvl: [] for lvl in LEVEL_ORDER}
    norm_keywords = _load_normalized_keywords()
    raw_keywords = _load_keywords()
    for level in LEVEL_ORDER:
        hits = 0
        for norm_kw, raw_kw in zip(norm_keywords.get(level, []), raw_keywords.get(level, [])):
            if norm_kw in normalized:
                hits += 1
                triggers[level].append(raw_kw)
        counts.append(hits)

    total = sum(counts)
    if total == 0:
        raw = [1.0 / 6.0] * 6
    else:
        raw = [(c + 1) / (total + 6) for c in counts]

    probs = [round(p, 3) for p in raw]
    drift = round(1.0 - sum(probs), 3)
    if drift != 0:
        probs[-1] = round(probs[-1] + drift, 3)

    sorted_levels = sorted(zip(LEVEL_ORDER, probs), key=lambda x: x[1], reverse=True)
    top_levels = [lvl for lvl, p in sorted_levels if p >= min_prob][:max_levels]
    if not top_levels:
        top_levels = [sorted_levels[0][0]]

    rationale_parts = []
    for lvl in top_levels:
        kws = triggers.get(lvl) or []
        if kws:
            rationale_parts.append(f"{lvl}: {', '.join(sorted(set(kws))[:6])}")
    rationale = "; ".join(rationale_parts) if rationale_parts else "keyword-baseline"

    return {
        "prob_vector": probs,
        "top_levels": top_levels,
        "rationale": rationale,
        "triggers": triggers,
    }
