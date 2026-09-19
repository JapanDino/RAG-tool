"""Bounded, source-linked answer blocks. No model-generated HTML or executable SVG."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, ValidationError

ShortText = Annotated[str, Field(min_length=1, max_length=300)]
SourceIds = Annotated[list[int], Field(min_length=1, max_length=6)]


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Section(Block):
    heading: str = Field(min_length=1, max_length=100)
    body: str = Field(default="", max_length=1500)
    bullets: list[ShortText] = Field(default_factory=list, max_length=6)
    citations: SourceIds


class Node(Block):
    id: str = Field(min_length=1, max_length=30)
    label: str = Field(min_length=1, max_length=120)


class Edge(Block):
    source: str = Field(min_length=1, max_length=30)
    target: str = Field(min_length=1, max_length=30)
    label: str = Field(default="", max_length=120)


class Diagram(Block):
    title: str = Field(min_length=1, max_length=120)
    nodes: list[Node] = Field(min_length=2, max_length=6)
    edges: list[Edge] = Field(min_length=1, max_length=8)
    citations: SourceIds


def validated_layout(answer: dict, cited_ids: list[int]) -> dict:
    result = {"sections": [], "diagram": None}
    try:
        raw = answer.get("sections", [])
        if not isinstance(raw, list) or len(raw) > 4:
            raise ValueError("Too many sections")
        sections = [Section.model_validate(item) for item in raw]
        if all(
            set(item.citations) <= set(cited_ids)
            and (item.body.strip() or item.bullets)
            for item in sections
        ):
            result["sections"] = [item.model_dump() for item in sections]
    except (ValidationError, ValueError, TypeError):
        pass
    try:
        diagram = Diagram.model_validate(answer.get("diagram"))
        nodes = {node.id for node in diagram.nodes}
        if (
            len(nodes) == len(diagram.nodes)
            and set(diagram.citations) <= set(cited_ids)
            and all(
                edge.source in nodes
                and edge.target in nodes
                and edge.source != edge.target
                for edge in diagram.edges
            )
        ):
            result["diagram"] = diagram.model_dump()
    except (ValidationError, ValueError, TypeError):
        pass
    return result


LAYOUT_PROMPT = """
Оформляй ответ как понятное объяснение, а не копию текста источника.
answer — краткий прямой ответ, 1–3 предложения. Для развёрнутого объяснения добавь до 4 sections:
{"heading":"заголовок","body":"объяснение своими словами","bullets":["пункт"],"citations":[id]}.
Не повторяй answer в sections; выбирай нужную форму: смысловые части, шаги, сравнение или пример.
На просьбу объяснить проще используй простые слова; на просьбу проверить понимание задай вопрос по теме,
не сообщая сразу ответ. Уточнения в истории помогают понять тему, но подтверждения бери из sources.
Даже для проверочного вопроса заполни общий citations числовыми id фрагментов из sources,
по которым можно проверить правильный ответ ученика. Сам правильный ответ не раскрывай.
Когда вопрос касается связей или процесса либо ученик просит схему, добавь diagram:
{"title":"название","nodes":[{"id":"a","label":"понятие"},{"id":"b","label":"понятие"}],
"edges":[{"source":"a","target":"b","label":"связь"}],"citations":[id]}.
Это составленная тобой схема по тексту, не изображение из учебника. Не выдумывай связи.
Используй 2–6 узлов и 1–8 связей, подписи до 120 символов. Если схема не помогает, diagram=null.
Все citations разделов и схемы должны входить в общий citations и подтверждать соответствующий блок.
Выводи обычный текст без Markdown/HTML внутри полей. sections=[] допустимо для короткого ответа.
"""
