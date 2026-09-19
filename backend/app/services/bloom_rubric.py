"""Conservative operationalization of revised Bloom; not a validated classifier.

Scope: explicit RU/EN learner instructions, not the sophistication of prose.
See docs/BLOOM_METHODOLOGY.md for sources, decisions and validation limits.
Rules return traceable proposals or abstain; they never invent probabilities.
"""

from __future__ import annotations

import re
from functools import lru_cache

from ..utils.bloom import LEVEL_ORDER

RUBRIC_VERSION = "rbt-context-1.0"
REFERENCES = [
    {
        "id": "krathwohl2002",
        "title": "Krathwohl (2002): пересмотренная таксономия",
        "url": "https://doi.org/10.1207/s15430421tip4104_2",
    },
    {
        "id": "stanny2016",
        "title": "Stanny (2016): ограничения списков глаголов",
        "url": "https://doi.org/10.3390/educsci6040037",
    },
    {
        "id": "larsen2022",
        "title": "Larsen et al. (2022): контекст и два измерения",
        "url": "https://doi.org/10.1187/cbe.20-08-0170",
    },
]

KNOWLEDGE = {
    "factual": r"\b(?:термин\w*|дат[ауые]\w*|названи\w*|столиц\w*|факт\w*|определени\w*|имена|названия|terms?|dates?|names?|facts?|definitions?)\b",
    "conceptual": r"\b(?:принцип\w*|теори\w*|категори\w*|классификац\w*|взаимосвяз\w*|причин\w*|модел\w*|фаз\w*|роль|principles?|theor\w*|categories|relationships?|models?)\b",
    "procedural": r"\b(?:алгоритм\w*|процедур\w*|метод\w*|формул\w*|уравнени\w*|инструкци\w*|при[её]м\w*|algorithms?|procedures?|methods?|formulas?|equations?|instructions?)\b",
    "metacognitive": r"(?:собственн\w*|сво\w*)\s+(?:стратег\w*|понимани\w*|ошиб\w*|способ\w*\s+уч[её]б\w*)|\bсамооцен\w*|\bсамоконтрол\w*|own\s+(?:learning|understanding|strateg\w*)",
}
PREFIX = re.compile(
    r"^(?:(?:[-•]|\d+[.)])\s*)?(?:пожалуйста[, ]+|please\s+)?"
    r"(?:(?:задание|цель(?:\s+урока)?|учебная\s+цель|learning\s+objective|task)\s*\d*\s*:\s*|"
    r"(?:ученик\w*|студент\w*|обучающ\w*)\s+(?:долж\w*|смог\w*|смож\w*|науч\w*)\s+|"
    r"(?:students?|learners?)\s+(?:will\s+be\s+able\s+to|should|will|can)\s+)?",
    re.IGNORECASE,
)
VERBS = {
    "recall": {
        "назвать",
        "перечислить",
        "вспомнить",
        "воспроизвести",
        "list",
        "name",
        "recall",
        "recite",
    },
    "explain": {
        "объяснить",
        "пересказать",
        "резюмировать",
        "обобщить",
        "интерпретировать",
        "explain",
        "summarize",
        "interpret",
        "paraphrase",
    },
    "compare": {"сравнить", "сопоставить", "compare", "contrast"},
    "apply": {
        "решить",
        "вычислить",
        "рассчитать",
        "применить",
        "использовать",
        "выполнить",
        "solve",
        "calculate",
        "apply",
        "execute",
        "use",
    },
    "analyze": {
        "проанализировать",
        "разделить",
        "выделить",
        "отделить",
        "установить",
        "analyze",
        "analyse",
        "differentiate",
        "distinguish",
    },
    "evaluate": {
        "оценить",
        "проверить",
        "обосновать",
        "выбрать",
        "evaluate",
        "assess",
        "justify",
        "critique",
        "check",
        "select",
    },
    "create": {
        "создать",
        "разработать",
        "спроектировать",
        "предложить",
        "составить",
        "построить",
        "create",
        "design",
        "develop",
        "propose",
        "construct",
    },
}
ENGLISH_VERBS = {v for group in VERBS.values() for v in group if v.isascii()}


@lru_cache(maxsize=1)
def _morph():
    import pymorphy3
    import pymorphy3_dicts_ru

    # Explicit dictionary path avoids legacy pkg_resources entry-point discovery.
    return pymorphy3.MorphAnalyzer(path=pymorphy3_dicts_ru.get_path())


def _has(pattern: str, value: str) -> bool:
    return bool(re.search(pattern, value, re.IGNORECASE))


def _instruction(sentence: str) -> tuple[str, str] | None:
    match = PREFIX.match(sentence)
    prefix = match.group() if match else ""
    rest = sentence[len(prefix) :].strip()
    word = re.match(r"[a-zа-яё]+\b", rest, re.IGNORECASE)
    if not word:
        return None
    token = word.group().lower()
    # A negated action is not an intended positive learning outcome.
    if token in {"не", "not", "don't"}:
        return None
    if token in ENGLISH_VERBS:
        return token, rest[len(word.group()) :].strip(" ,:;.!?")
    for parsed in _morph().parse(token):
        if parsed.is_known and (
            "impr" in parsed.tag or (prefix.strip() and "INFN" in parsed.tag)
        ):
            return parsed.normal_form, rest[len(word.group()) :].strip(" ,:;.!?")
    return None


def _decision(verb: str, obj: str) -> tuple[str | None, str, str]:
    """Rule IDs are our engineering choices, not quotations from the papers."""
    if _has(r"\b(?:не|not|without)\b", obj):
        return (
            None,
            "negated_condition",
            "В условии есть отрицание: нужно проверить, какое требование оно отменяет. Автоматический уровень не назначен.",
        )
    if len(re.findall(r"\w+", obj)) < 2:
        return (
            None,
            "insufficient_object",
            "Недостаточно описаны объект и ожидаемый результат задания.",
        )
    template = _has(
        r"по\s+(?:готов\w*\s+)?(?:образц\w*|шаблон\w*|инструкци\w*)|точн\w*\s+копи\w*|given\s+(?:template|procedure)|following\s+instructions",
        obj,
    )
    procedure = _has(KNOWLEDGE["procedural"], obj) or template
    recall_only = _has(
        r"(?:дословн\w*|из\s+памяти|выученн\w*|наизусть|verbatim|from\s+memory)", obj
    )
    if verb in VERBS["recall"] or (verb in VERBS["explain"] and recall_only):
        return (
            "remember",
            "recall",
            "Запрошено воспроизведение сведений; это предложение о требовании задания, не оценка памяти ученика.",
        )
    if verb in VERBS["create"] and template:
        return (
            "apply",
            "execute_template",
            "Продукт создаётся по заданному образцу: нового самостоятельного замысла в условии нет.",
        )
    if verb in VERBS["apply"] and procedure:
        return (
            "apply",
            "use_procedure",
            "Есть действие с указанной процедурой, формулой или алгоритмом.",
        )
    if (
        verb in VERBS["evaluate"]
        and procedure
        and not _has(r"критер|стандарт|criteria|standards", obj)
    ):
        # 'Estimate using the formula' is not a standards-based judgement.
        return (
            None,
            "ambiguous_procedure",
            "Упоминание процедуры не уточняет: нужно выполнить её или оценить её пригодность.",
        )
    if verb in VERBS["analyze"] | VERBS["compare"] and _has(
        r"(?:част\w*|элемент\w*|аргумент\w*|данн\w*).*(?:связ\w*|роль|структур\w*|цел\w*)|"
        r"(?:существенн\w*|релевантн\w*).*(?:несущественн\w*|нерелевантн\w*)|"
        r"parts?.*(?:relationships?|structure|purpose)|relevant.*irrelevant",
        obj,
    ):
        return (
            "analyze",
            "parts_and_relations",
            "Требуется различить части и их отношения, роль или значимость; простого сравнения для этого уровня недостаточно.",
        )
    if verb in VERBS["evaluate"] and _has(
        r"критери\w*|стандарт\w*|criteria|standards", obj
    ):
        return (
            "evaluate",
            "criteria_based_judgement",
            "В условии есть суждение или проверка с опорой на критерии/стандарты. Сами критерии нужно проверить в источнике.",
        )
    output = _has(
        r"модел\w*|проект\w*|эксперимент\w*|план\w*|гипотез\w*|алгоритм\w*|рассказ\w*|продукт\w*|design|model|experiment|plan|hypothes\w*|algorithm|story",
        obj,
    )
    novelty = _has(
        r"нов\w*|собственн\w*|оригинальн\w*|самостоятельн\w*|original|novel|own", obj
    )
    if verb in VERBS["create"] and output and novelty:
        return (
            "create",
            "original_product",
            "Указаны самостоятельный/новый замысел и создаваемый продукт; если он уже разбирался по образцу, уровень нужно пересмотреть.",
        )
    if verb in VERBS["compare"]:
        return (
            "understand",
            "compare_meaning",
            "Сопоставление само по себе относится к пониманию; разбор структуры или суждение по критериям должны быть указаны отдельно.",
        )
    if verb in VERBS["explain"]:
        return (
            "understand",
            "construct_meaning",
            "Запрошено объяснение или преобразование смысла; воспроизведение заученного ответа этим правилом не подтверждается.",
        )
    return (
        None,
        "insufficient_context",
        "По глаголу нельзя определить уровень: уточните действие, результат, критерии и знакомство ученика с задачей.",
    )


def classify_learning_demands(text: str) -> dict:
    evidence = []
    # Keep evidence verbatim. Neither titles nor nearby exposition supply a task.
    for sentence in re.split(r"(?<=[.!?;])\s+|\n+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        instruction = _instruction(sentence)
        if not instruction:
            if sentence.endswith("?"):
                evidence.append(
                    {
                        "quote": sentence,
                        "action": None,
                        "object": None,
                        "level": None,
                        "rule_id": "question_context",
                        "knowledge": [],
                        "knowledge_evidence": {},
                        "rationale": "Вопрос найден, но вопросительное слово не определяет когнитивный процесс.",
                    }
                )
            continue
        # Do not attribute words from a second instruction to the first action.
        clauses = re.split(
            r"\s+(?:и\s+затем|а\s+затем|затем|и|and\s+then|then|and)\s+", sentence
        )
        tasks = [sentence]
        if len(clauses) > 1 and all(_instruction(c) for c in clauses):
            tasks = clauses
        for task in tasks:
            verb, obj = _instruction(task)
            level, rule, rationale = _decision(verb, obj)
            knowledge_evidence = {}
            for name, pattern in KNOWLEDGE.items():
                hit = re.search(pattern, obj, re.IGNORECASE)
                if hit:
                    knowledge_evidence[name] = hit.group()
            evidence.append(
                {
                    "quote": task,
                    "action": verb,
                    "object": obj,
                    "level": level,
                    "rule_id": rule,
                    "knowledge": list(knowledge_evidence),
                    "knowledge_evidence": knowledge_evidence,
                    "rationale": rationale,
                }
            )
    levels = [
        level for level in LEVEL_ORDER if any(e["level"] == level for e in evidence)
    ]
    pending = sum(e["level"] is None for e in evidence)
    return {
        "version": RUBRIC_VERSION,
        "status": ("partial" if pending else "proposed")
        if levels
        else ("needs_review" if evidence else "no_task"),
        "levels": levels,
        "knowledge": [
            k for k in KNOWLEDGE if any(k in e["knowledge"] for e in evidence)
        ],
        "evidence": evidence,
        "rationale": "Предложение по явному учебному действию; требуется проверка преподавателя."
        if evidence
        else "Явное задание или учебная цель не распознаны. Из описания темы нельзя вывести требуемое действие ученика.",
    }
