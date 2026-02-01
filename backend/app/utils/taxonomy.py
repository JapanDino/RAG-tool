LEVELS = [
    {"level": "remember", "label": "Знать", "color": "#3b82f6"},
    {"level": "understand", "label": "Понимать", "color": "#06b6d4"},
    {"level": "apply", "label": "Применять", "color": "#10b981"},
    {"level": "analyze", "label": "Анализировать", "color": "#f59e0b"},
    {"level": "evaluate", "label": "Оценивать", "color": "#f97316"},
    {"level": "create", "label": "Создавать", "color": "#ef4444"},
]


def get_taxonomy_levels() -> list[dict[str, str]]:
    return LEVELS
