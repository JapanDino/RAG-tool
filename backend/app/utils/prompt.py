from textwrap import dedent

BLOOM_INSTRUCTIONS = {
    "remember": "Определите/перечислите ключевые факты из фрагмента.",
    "understand": "Кратко объясните основную идею своими словами.",
    "apply": "Опишите, как применить знания к типовой задаче.",
    "analyze": "Выделите части, связи и причины.",
    "evaluate": "Оцените подходы и сформулируйте аргументированный вывод.",
    "create": "Предложите новый план/решение на основе текста.",
}

def build_bloom_prompt(chunk: str, level: str, rubric: str | None = None) -> str:
    guidance = BLOOM_INSTRUCTIONS.get(
        level, "Сформулируйте краткую аннотацию по таксономии Блума."
    )
    rubric_part = f"Критерии оценки: {rubric}\n" if rubric else ""
    return (
        dedent(
            f"""
            Вы — эксперт-методист. Проаннотируйте фрагмент по таксономии Блума для уровня: {level}.
            {rubric_part}
            Инструкция: {guidance}

            Требуемый формат JSON (без пояснений вне JSON):
            {{
              "level": "{level}",
              "label": "<краткое название>",
              "rationale": "<почему выбран этот уровень>",
              "score": <число от 0 до 1>
            }}

            Фрагмент:
            ---
            {chunk}
            ---
            """
        )
        .strip()
    )


def build_bloom_multilabel_prompt(text: str) -> str:
    return (
        dedent(
            f"""
            Вы — эксперт-методист. Определите уровни таксономии Блума для фрагмента.
            Нужно вернуть вероятности по 6 уровням пересмотренной таксономии (Remember..Create).

            Требуемый формат JSON (без пояснений вне JSON):
            {{
              "prob_vector": [p_remember, p_understand, p_apply, p_analyze, p_evaluate, p_create],
              "top_levels": ["remember", "analyze"],
              "rationale": "<кратко почему>"
            }}

            Ограничения:
            - prob_vector ровно 6 чисел, каждое в [0,1]
            - сумма prob_vector должна быть 1.0 (или очень близко)
            - top_levels: 1+ уровней из: remember/understand/apply/analyze/evaluate/create

            Фрагмент:
            ---
            {text}
            ---
            """
        )
        .strip()
    )
