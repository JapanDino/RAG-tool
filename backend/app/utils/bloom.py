from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
import re


LEVEL_ORDER = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

# Structural regex patterns — fired on raw lowercase text (no lemmatisation needed).
# Complements the verb dictionary for content pages that lack explicit task verbs.
HEURISTIC_PATTERNS = {
    "remember": [r"\bформул", r"\bопределен", r"\bтермин", r"\bсвойств", r"\bтаблиц"],
    "understand": [r"\bобъясн", r"\bпонят", r"\bтеор", r"\bпринцип", r"\bзакон"],
    "apply": [r"\bсеминар", r"\bлаборатор", r"\bпрактичес", r"\bзадач", r"\bупражнен", r"\bрасчет", r"\bвычисл"],
    "analyze": [r"\bанализ", r"\bразбор", r"\bсравнен", r"\bструктур", r"\bпричин", r"\bследств"],
    "evaluate": [r"\bоцен", r"\bкритич", r"\bаргумент", r"\bдоказ", r"\bвывод"],
    "create": [r"\bпроект", r"\bсозда", r"\bразработ", r"\bмодел", r"\bсформулир"],
}
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
    """Tokenise + lemmatise with pymorphy3 (if available), else lowercase."""
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
    result = classify_bloom_multilabel(chunk)
    level_index = LEVEL_ORDER.index(level) if level in LEVEL_ORDER else 0
    score = float(result["prob_vector"][level_index])
    label = {
        "remember": "Факты",
        "understand": "Понимание",
        "apply": "Применение",
        "analyze": "Анализ",
        "evaluate": "Оценивание",
        "create": "Создание",
    }.get(level, "N/A")
    # Build a rationale specific to the requested level (not the global top level).
    level_triggers = result.get("triggers", {}).get(level, [])
    if level_triggers:
        rationale = f"{level}: {', '.join(sorted(set(level_triggers))[:6])}"
    else:
        rationale = f"{level}: keyword-baseline (score={score:.3f})"
    return dict(level=level, label=label, rationale=rationale, score=round(score, 3))


def _default_verbs_path() -> Path:
    # /app/backend/app/utils/bloom.py -> /app/data/bloom_verbs_ru.json
    return Path(__file__).resolve().parents[3] / "data" / "bloom_verbs_ru.json"


@lru_cache(maxsize=1)
def _load_keywords() -> dict[str, list[str]]:
    path = Path(os.getenv("BLOOM_VERBS_PATH", str(_default_verbs_path())))
    if not path.exists():
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
    """Return keywords pre-lemmatised via pymorphy3 for morphology-aware matching."""
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


@lru_cache(maxsize=1)
def _compiled_heuristics() -> dict[str, list[re.Pattern[str]]]:
    return {
        lvl: [re.compile(pat, re.IGNORECASE) for pat in patterns]
        for lvl, patterns in HEURISTIC_PATTERNS.items()
    }


def _heuristic_counts(text: str) -> tuple[list[int], dict[str, list[str]]]:
    compiled = _compiled_heuristics()
    counts: list[int] = []
    triggers: dict[str, list[str]] = {lvl: [] for lvl in LEVEL_ORDER}
    for lvl in LEVEL_ORDER:
        hits = 0
        for pat in compiled.get(lvl, []):
            if pat.search(text):
                hits += 1
                triggers[lvl].append(pat.pattern)
        counts.append(hits)
    return counts, triggers


def classify_bloom_multilabel(
    text: str,
    min_prob: float = 0.2,
    max_levels: int = 2,
):
    normalized = _normalize_text(text)   # lemmatised — for keyword matching
    lowered = text.lower()               # raw lowercase — for heuristic regex
    keyword_counts = []
    triggers: dict[str, list[str]] = {lvl: [] for lvl in LEVEL_ORDER}
    norm_keywords = _load_normalized_keywords()
    raw_keywords = _load_keywords()
    for level in LEVEL_ORDER:
        hits = 0
        for norm_kw, raw_kw in zip(norm_keywords.get(level, []), raw_keywords.get(level, [])):
            if norm_kw in normalized:
                hits += 1
                triggers[level].append(raw_kw)
        keyword_counts.append(hits)

    heuristic_counts, heuristic_triggers = _heuristic_counts(lowered)
    counts = []
    for i, level in enumerate(LEVEL_ORDER):
        # Structural cues ("семинар", "лабораторная", "формулы") add signal for
        # content pages that do not contain explicit task verbs.
        counts.append(keyword_counts[i] + heuristic_counts[i])
        if heuristic_triggers[level]:
            triggers[level].extend(heuristic_triggers[level])

    total = sum(counts)
    if total == 0:
        raw = [1.0 / len(LEVEL_ORDER)] * len(LEVEL_ORDER)
    else:
        raw = [(c + 1) / (total + 6) for c in counts]

    probs = [round(p, 3) for p in raw]
    drift = round(1.0 - sum(probs), 3)
    if drift != 0:
        max_idx = probs.index(max(probs))
        probs[max_idx] = round(probs[max_idx] + drift, 3)

    sorted_levels = sorted(zip(LEVEL_ORDER, probs), key=lambda x: x[1], reverse=True)
    top_levels = [] if total == 0 else [lvl for lvl, p in sorted_levels if p >= min_prob][:max_levels]

    rationale_parts = []
    for lvl in top_levels:
        kws = triggers.get(lvl) or []
        if kws:
            rationale_parts.append(f"{lvl}: {', '.join(sorted(set(kws))[:6])}")
    if total == 0:
        rationale = "insufficient-signal"
    elif rationale_parts:
        rationale = "; ".join(rationale_parts)
    else:
        rationale = "low-confidence"

    return {
        "prob_vector": probs,
        "top_levels": top_levels,
        "rationale": rationale,
        "triggers": triggers,
    }
