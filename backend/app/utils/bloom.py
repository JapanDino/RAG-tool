def annotate_bloom(chunk: str, level: str, rubric: str|None=None):
    # Placeholder deterministic annotator (без LLM): простая эвристика
    score = min(1.0, 0.5 + len(chunk.strip())/2000.0)
    label = {
        "remember":"Факты",
        "understand":"Понимание",
        "apply":"Применение",
        "analyze":"Анализ",
        "evaluate":"Оценивание",
        "create":"Создание"
    }.get(level, "N/A")
    rationale = f"Эвристика: длина текста={len(chunk)}; уровень={level}"
    return dict(level=level, label=label, rationale=rationale, score=round(score,3))

_BLOOM_KEYWORDS = {
    "remember": ["назов", "перечис", "вспомн", "определ", "когда", "кто", "что такое"],
    "understand": ["объясн", "почему", "сравн", "опишите", "перескаж", "классифиц"],
    "apply": ["примен", "использ", "реши", "вычисл", "выполн", "покажи"],
    "analyze": ["проанализ", "раздели", "выдели", "структур", "причин", "сравни"],
    "evaluate": ["оцени", "крит", "аргумент", "обоснуй", "докажи", "вывод"],
    "create": ["создай", "придум", "спроект", "разработ", "сформулируй", "составь"],
}

def classify_bloom_multilabel(text: str):
    lowered = text.lower()
    counts = []
    for level in ("remember","understand","apply","analyze","evaluate","create"):
        hits = 0
        for kw in _BLOOM_KEYWORDS[level]:
            if kw in lowered:
                hits += 1
        counts.append(hits)

    total = sum(counts)
    if total == 0:
        probs = [round(1.0 / 6.0, 3)] * 6
    else:
        probs = [round((c + 1) / (total + 6), 3) for c in counts]

    level_order = ["remember","understand","apply","analyze","evaluate","create"]
    sorted_levels = sorted(zip(level_order, probs), key=lambda x: x[1], reverse=True)
    top_levels = [lvl for lvl, p in sorted_levels if p >= 0.2][:2]
    if not top_levels:
        top_levels = [sorted_levels[0][0]]

    return {"prob_vector": probs, "top_levels": top_levels}
