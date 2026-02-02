from __future__ import annotations

from collections import defaultdict


LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]

KEYWORDS: dict[str, list[str]] = {
    "remember": ["назовите", "перечислите", "опишите", "вспомните", "определите"],
    "understand": ["объясните", "сравните", "перефразируйте", "классифицируйте", "интерпретируйте"],
    "apply": ["примените", "используйте", "решите", "покажите", "продемонстрируйте"],
    "analyze": ["проанализируйте", "разделите", "выделите", "сопоставьте", "обоснуйте"],
    "evaluate": ["оцените", "критически", "проверьте", "аргументируйте", "сделайте вывод"],
    "create": ["создайте", "предложите", "спроектируйте", "сформулируйте", "разработайте"],
}


def bloom_probabilities(text: str) -> dict[str, float]:
    lowered = text.lower()
    scores = defaultdict(float)
    for level, words in KEYWORDS.items():
        for word in words:
            if word in lowered:
                scores[level] += 1.0
    if not scores:
        base = 1.0 / len(LEVELS)
        return {level: base for level in LEVELS}
    total = sum(scores.values())
    return {level: round(scores.get(level, 0.0) / total, 4) for level in LEVELS}
