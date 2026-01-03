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
