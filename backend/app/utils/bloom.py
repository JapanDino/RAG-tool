from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

LEVEL_ORDER = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


def annotate_bloom(chunk: str, level: str, rubric: str | None = None):
    # Placeholder deterministic annotator (без LLM): простая эвристика
    score = min(1.0, 0.5 + len(chunk.strip()) / 2000.0)
    label = {
        "remember": "Факты",
        "understand": "Понимание",
        "apply": "Применение",
        "analyze": "Анализ",
        "evaluate": "Оценивание",
        "create": "Создание",
    }.get(level, "N/A")
    rationale = f"Эвристика: длина текста={len(chunk)}; уровень={level}"
    return dict(level=level, label=label, rationale=rationale, score=round(score, 3))


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
    # Learning objectives commonly use infinitives while assignments use imperatives.
    # Prefixes below intentionally rely on the classifier's trailing ``\w*`` match.
    objective_stems = {
        "remember": ["запомина", "воспроизвод", "называ", "перечисля", "определя"],
        "understand": ["понима", "объясня", "описыва", "интерпретир", "сравнива"],
        "apply": ["применя", "использова", "реша", "вычисля", "выполня"],
        "analyze": ["анализир", "сопоставля", "структурир", "выделя"],
        "evaluate": ["оценива", "обосновыва", "аргументир", "доказыва"],
        "create": ["создава", "разрабатыва", "проектир", "формулирова", "составля"],
    }
    for level, stems in objective_stems.items():
        out[level].extend(stem for stem in stems if stem not in out[level])
    return out


def classify_bloom_multilabel(
    text: str,
    min_prob: float = 0.2,
    max_levels: int = 2,
):
    lowered = text.lower()
    counts = []
    triggers: dict[str, list[str]] = {lvl: [] for lvl in LEVEL_ORDER}
    keywords = _load_keywords()
    for level in LEVEL_ORDER:
        hits = 0
        occupied_spans: list[tuple[int, int]] = []
        for kw in keywords.get(level, []):
            match = re.search(rf"\b{re.escape(kw)}\w*\b", lowered)
            if not match:
                match = re.search(re.escape(kw), lowered)
            if match and not any(
                match.start() >= start and match.end() <= end
                for start, end in occupied_spans
            ):
                hits += 1
                triggers[level].append(kw)
                occupied_spans.append((match.start(), match.end()))
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

    priority = {lvl: 0 for lvl in LEVEL_ORDER}
    if triggers["analyze"] and triggers["evaluate"]:
        # In task prompts such as "compare causes ... to evaluate ...", the
        # assessment and analysis intent is more specific than generic compare.
        priority["analyze"] = 2
        priority["evaluate"] = 2
        priority["understand"] = -1

    sorted_levels = sorted(
        zip(LEVEL_ORDER, probs),
        key=lambda x: (x[1], priority.get(x[0], 0)),
        reverse=True,
    )
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
