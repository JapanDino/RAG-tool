BLOOM_RUBRICS = {
    "remember": "Определите/назовите/воспроизведите ключевые факты.",
    "understand": "Переформулируйте и объясните идею своими словами.",
    "apply": "Примените метод к типовой задаче.",
    "analyze": "Разбейте на части, выделите зависимости/причины.",
    "evaluate": "Сравните подходы, сформулируйте критерии и вывод.",
    "create": "Синтезируйте новое решение/план/вариант."
}


def get_active_rubric(level: str, db):
    from sqlalchemy.orm import Session
    from ..models.models import Rubric

    if not isinstance(db, Session):
        return None
    return (
        db.query(Rubric)
        .filter(Rubric.level == level, Rubric.is_active == True)  # noqa: E712
        .order_by(Rubric.id.desc())
        .first()
    )
