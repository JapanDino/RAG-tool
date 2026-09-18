from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.models import (
    AssessmentItem,
    AuditRun,
    Chunk,
    Course,
    Document,
    LearningMaterial,
    LearningObjective,
)
from ..services.bloom_multilabel import classify_bloom_multilabel
from ..services.node_extractor import split_sentences_with_offsets
from ..services.openai_client import chat_completion_json

OBJECTIVE_RE = re.compile(
    r"(?:студент|ученик|слушатель|обучающ\w*)\b.{0,100}"
    r"(?:сможет|должен|должна|научится|умеет|будет\s+способ\w*)|"
    r"(?:по\s+окончании|результат\w*\s+обучения|цель\w*\s+(?:курса|модуля))",
    re.IGNORECASE | re.DOTALL,
)
FALSE_OBJECTIVE_RE = re.compile(
    r"\b(?:в этом тексте|в этой статье|мы рассмотрим|мы сравним)\b", re.IGNORECASE
)
ASSESSMENT_RE = re.compile(
    r"^\s*(?:[-*•]\s*|\d+[.)]\s*)?"
    r"(?:назов\w*|перечисл\w*|определ\w*|объясн\w*|сравн\w*|примен\w*|"
    r"реш\w*|проанализ\w*|оцен\w*|обосну\w*|созда\w*|разработ\w*|"
    r"спроектир\w*|рассчита\w*|выбер\w*|укаж\w*|напиш\w*)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedEntity:
    text: str
    start: int
    end: int
    confidence: float
    method: str


class _LLMEntity(BaseModel):
    text: str = Field(min_length=3)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class _LLMExtraction(BaseModel):
    objectives: list[_LLMEntity] = Field(default_factory=list)
    assessments: list[_LLMEntity] = Field(default_factory=list)


def normalize_text(value: str) -> str:
    return " ".join(value.lower().strip().split())


def classify_document(document: Document) -> tuple[str, float, list[str]]:
    metadata = document.source_metadata or {}
    declared = str(metadata.get("document_type") or "").strip().lower()
    allowed = {
        "course_description",
        "module_description",
        "learning_objectives",
        "lecture_material",
        "reading",
        "assignment",
        "quiz",
        "exam",
        "rubric",
        "unknown",
    }
    if declared in allowed and declared != "unknown":
        return declared, 1.0, ["declared metadata"]

    title = normalize_text(document.title)
    rules = [
        (
            "learning_objectives",
            ("цели", "результаты обучения", "learning objectives", "outcomes"),
        ),
        ("quiz", ("тест", "quiz", "вопросы")),
        ("exam", ("экзамен", "exam", "контрольная")),
        ("assignment", ("задание", "assignment", "домашняя", "практическая")),
        ("rubric", ("рубрика", "rubric", "критерии оценивания")),
        ("reading", ("литература", "reading", "статья")),
        ("lecture_material", ("лекция", "lecture", "презентация", "конспект")),
        ("module_description", ("описание модуля", "module description")),
        (
            "course_description",
            ("описание курса", "course description", "syllabus", "силлабус"),
        ),
    ]
    for kind, cues in rules:
        hits = [cue for cue in cues if cue in title]
        if hits:
            return kind, 0.85, hits
    return "unknown", 0.35, ["no reliable metadata or title cue"]


def extract_learning_objectives(text: str) -> list[ExtractedEntity]:
    entities = []
    for sentence in split_sentences_with_offsets(text):
        value = sentence["text"].strip(" \t-*•")
        if not value or FALSE_OBJECTIVE_RE.search(value):
            continue
        match = OBJECTIVE_RE.search(value)
        if not match:
            continue
        confidence = (
            0.92
            if re.search(r"(?:студент|ученик|слушатель|обучающ\w*)", value, re.I)
            else 0.78
        )
        local_shift = sentence["text"].find(value)
        start = sentence["start"] + max(local_shift, 0)
        entities.append(
            ExtractedEntity(
                value, start, start + len(value), confidence, "objective-rule-v1"
            )
        )
    return _deduplicate_entities(entities)


def extract_assessment_items(text: str) -> list[ExtractedEntity]:
    entities = []
    for sentence in split_sentences_with_offsets(text):
        value = sentence["text"].strip(" \t-*•")
        if not value or OBJECTIVE_RE.search(value):
            continue
        is_imperative = bool(ASSESSMENT_RE.search(value))
        is_question = value.endswith("?") and len(value.split()) >= 3
        if not is_imperative and not is_question:
            continue
        confidence = 0.9 if is_imperative else 0.7
        local_shift = sentence["text"].find(value)
        start = sentence["start"] + max(local_shift, 0)
        entities.append(
            ExtractedEntity(
                value, start, start + len(value), confidence, "assessment-rule-v1"
            )
        )
    return _deduplicate_entities(entities)


def extract_entities_with_provider(
    text: str, document_kind: str
) -> tuple[list[ExtractedEntity], list[ExtractedEntity], str]:
    mode = os.getenv("COURSE_ENTITY_EXTRACTOR", "baseline").strip().lower()
    baseline_objectives = (
        extract_learning_objectives(text)
        if document_kind
        in {
            "learning_objectives",
            "course_description",
            "module_description",
            "unknown",
        }
        else []
    )
    baseline_assessments = (
        extract_assessment_items(text)
        if document_kind in {"assignment", "quiz", "exam", "unknown"}
        else []
    )
    if mode != "llm" or not os.getenv("OPENAI_API_KEY", "").strip():
        return baseline_objectives, baseline_assessments, "baseline"

    prompt = (
        "Extract learning objectives and individual assessment items from the educational text. "
        "Do not treat narrative intentions, examples, solutions, or rubric-wide instructions as entities. "
        "Return JSON only with this schema: "
        '{"objectives":[{"text":"exact source quote","confidence":0.0}],'
        '"assessments":[{"text":"exact source quote","confidence":0.0}]}. '
        "Every text value must be an exact contiguous quote from the source.\n\nSOURCE:\n"
        + text[:12000]
    )
    try:
        raw = chat_completion_json(
            os.getenv("LLM_MODEL", "gpt-4o-mini"), prompt, max_tokens=1400
        )
        parsed = _LLMExtraction.model_validate(json.loads(raw))
        objectives = _locate_llm_entities(
            text, parsed.objectives, "objective-llm-structured-v1"
        )
        assessments = _locate_llm_entities(
            text, parsed.assessments, "assessment-llm-structured-v1"
        )
        if document_kind == "learning_objectives" and not objectives:
            raise ValueError("LLM returned no valid objective quotes")
        if document_kind in {"assignment", "quiz", "exam"} and not assessments:
            raise ValueError("LLM returned no valid assessment quotes")
        return (
            objectives or baseline_objectives,
            assessments or baseline_assessments,
            "llm",
        )
    except Exception:
        return baseline_objectives, baseline_assessments, "baseline-fallback"


def _locate_llm_entities(
    text: str, values: list[_LLMEntity], method: str
) -> list[ExtractedEntity]:
    lowered = text.lower()
    entities = []
    for value in values:
        quote = value.text.strip()
        start = lowered.find(quote.lower())
        if start < 0:
            continue
        entities.append(
            ExtractedEntity(
                text[start : start + len(quote)],
                start,
                start + len(quote),
                value.confidence,
                method,
            )
        )
    return _deduplicate_entities(entities)


def _deduplicate_entities(items: list[ExtractedEntity]) -> list[ExtractedEntity]:
    seen = set()
    result = []
    for item in items:
        key = normalize_text(item.text)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def assessment_type_for(document_kind: str, text: str) -> str:
    lowered = normalize_text(text)
    if document_kind == "quiz":
        return "quiz_question"
    if document_kind == "exam":
        return "exam_question"
    if any(cue in lowered for cue in ("код", "программ", "функци", "алгоритм на")):
        return "coding_task"
    if any(cue in lowered for cue in ("эссе", "сочинение")):
        return "essay"
    if any(cue in lowered for cue in ("проект", "разработайте")):
        return "project"
    return "homework" if document_kind == "assignment" else "open_question"


def extract_course_entities(
    db: Session, course: Course, run: AuditRun
) -> dict[str, int]:
    documents = (
        db.query(Document)
        .filter(Document.dataset_id == course.dataset_id)
        .order_by(Document.id)
        .all()
    )
    counters = {
        "documents": len(documents),
        "objectives": 0,
        "materials": 0,
        "assessments": 0,
    }

    for document in documents:
        kind, doc_confidence, cues = classify_document(document)
        document.source_metadata = {
            **(document.source_metadata or {}),
            "document_type": kind,
            "classification_confidence": doc_confidence,
            "classification_cues": cues,
        }
        chunks = (
            db.query(Chunk)
            .filter(Chunk.document_id == document.id)
            .order_by(Chunk.idx)
            .all()
        )
        if not chunks:
            continue

        full_text = "\n".join(chunk.text for chunk in chunks).strip()
        if kind not in {"assignment", "quiz", "exam", "rubric", "learning_objectives"}:
            material_type = {
                "lecture_material": "lecture",
                "reading": "reading",
                "course_description": "article",
                "module_description": "article",
            }.get(kind, "other")
            db.add(
                LearningMaterial(
                    course_id=course.id,
                    module_id=document.course_module_id,
                    document_id=document.id,
                    audit_run_id=run.id,
                    material_type=material_type,
                    title=document.title,
                    source_url=document.source,
                    source_text=full_text,
                    meta={
                        "document_type": kind,
                        "classification_confidence": doc_confidence,
                    },
                )
            )
            counters["materials"] += 1

        for chunk in chunks:
            source_base = int((chunk.meta or {}).get("source_start") or 0)
            extracted_objectives, extracted_assessments, provider = (
                extract_entities_with_provider(chunk.text, kind)
            )
            if extracted_objectives:
                for entity in extracted_objectives:
                    bloom = classify_bloom_multilabel(
                        entity.text, min_prob=0.2, max_levels=2
                    )
                    db.add(
                        LearningObjective(
                            course_id=course.id,
                            module_id=document.course_module_id,
                            document_id=document.id,
                            audit_run_id=run.id,
                            text=entity.text,
                            normalized_text=normalize_text(entity.text),
                            bloom_vector=bloom["prob_vector"],
                            top_bloom_levels=bloom["top_levels"],
                            source_start=source_base + entity.start,
                            source_end=source_base + entity.end,
                            extraction_method=entity.method,
                            confidence=entity.confidence,
                            model_info={
                                "classifier": run.classifier_version,
                                "rationale": bloom.get("rationale"),
                                "extractor_provider": provider,
                            },
                        )
                    )
                    counters["objectives"] += 1

            if extracted_assessments:
                for entity in extracted_assessments:
                    bloom = classify_bloom_multilabel(
                        entity.text, min_prob=0.2, max_levels=2
                    )
                    db.add(
                        AssessmentItem(
                            course_id=course.id,
                            module_id=document.course_module_id,
                            document_id=document.id,
                            audit_run_id=run.id,
                            assessment_type=assessment_type_for(kind, entity.text),
                            title=entity.text[:120],
                            text=entity.text,
                            bloom_vector=bloom["prob_vector"],
                            top_bloom_levels=bloom["top_levels"],
                            source_start=source_base + entity.start,
                            source_end=source_base + entity.end,
                            extraction_method=entity.method,
                            confidence=entity.confidence,
                            model_info={
                                "classifier": run.classifier_version,
                                "rationale": bloom.get("rationale"),
                                "extractor_provider": provider,
                            },
                        )
                    )
                    counters["assessments"] += 1
    db.flush()
    return counters
