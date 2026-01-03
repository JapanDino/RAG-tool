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
