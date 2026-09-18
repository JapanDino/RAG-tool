from __future__ import annotations

import math
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models.models import Chunk, Course, CourseModule, Document
from .embedding import embed_texts
from .embedding_provider import EmbeddingProvider, current_embedding_model

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
STOPWORDS = {
    "после",
    "модуля",
    "курса",
    "студент",
    "ученик",
    "слушатель",
    "должен",
    "должна",
    "сможет",
    "будет",
    "этот",
    "эта",
    "эти",
    "того",
    "чтобы",
    "который",
    "которая",
    "для",
    "или",
    "при",
    "как",
    "что",
    "это",
    "все",
    "его",
    "она",
    "они",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "course",
    "student",
}
RETRIEVAL_PIPELINE_VERSION = "hybrid_bm25_embedding_module-v2"

RU_SUFFIXES = (
    "иями",
    "ями",
    "ами",
    "иями",
    "ого",
    "ему",
    "ому",
    "ыми",
    "ими",
    "ение",
    "ания",
    "ений",
    "аний",
    "ость",
    "остью",
    "ировать",
    "ровать",
    "ывать",
    "ивать",
    "ать",
    "ять",
    "ить",
    "еть",
    "ая",
    "яя",
    "ое",
    "ее",
    "ые",
    "ие",
    "ой",
    "ей",
    "ам",
    "ям",
    "ах",
    "ях",
    "ов",
    "ев",
    "ом",
    "ем",
    "ы",
    "и",
    "а",
    "я",
    "у",
    "ю",
    "е",
    "о",
)


def normalize_token(token: str) -> str:
    token = token.lower().replace("ё", "е")
    if re.fullmatch(r"[а-я]+", token):
        for suffix in RU_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= 4:
                return token[: -len(suffix)]
    return token


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: int
    document_id: int
    document_title: str
    module_id: int | None
    module_title: str | None
    quote: str
    source_url: str | None
    document_type: str
    score: float
    semantic_score: float
    lexical_score: float
    module_bonus: float


@dataclass(frozen=True)
class RankedTextCandidate:
    index: int
    score: float
    semantic_score: float
    lexical_score: float
    module_bonus: float


def tokenize(text: str) -> list[str]:
    result = []
    for token in TOKEN_RE.findall(text or ""):
        if len(token) < 3 or token.lower() in STOPWORDS:
            continue
        normalized = normalize_token(token)
        result.append(normalized)
        # A short character stem makes the offline retriever robust to common
        # Russian inflections without pulling in a heavyweight morphology model.
        if len(normalized) >= 6:
            result.append(f"~{normalized[:5]}")
    return result


class RetrievalDeadlineExceeded(TimeoutError):
    """Raised when cooperative local retrieval exhausts its caller deadline."""


def _check_deadline(deadline_monotonic: float | None) -> None:
    if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
        raise RetrievalDeadlineExceeded("retrieval deadline exceeded")


def _bm25_scores(
    query: str,
    texts: list[str],
    *,
    deadline_monotonic: float | None = None,
) -> list[float]:
    if not texts:
        return []
    _check_deadline(deadline_monotonic)
    query_tokens = tokenize(query)
    documents = []
    for text_value in texts:
        _check_deadline(deadline_monotonic)
        documents.append(tokenize(text_value))
    if not query_tokens or not any(documents):
        return [0.0] * len(texts)
    document_frequency = Counter()
    for document in documents:
        _check_deadline(deadline_monotonic)
        document_frequency.update(set(document))
    average_length = sum(len(document) for document in documents) / max(
        len(documents), 1
    )
    k1, b = 1.5, 0.75
    raw_scores = []
    for document in documents:
        _check_deadline(deadline_monotonic)
        frequencies = Counter(document)
        score = 0.0
        for token in set(query_tokens):
            frequency = frequencies.get(token, 0)
            if not frequency:
                continue
            df = document_frequency.get(token, 0)
            inverse_frequency = math.log(1.0 + (len(documents) - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (
                1.0 - b + b * len(document) / max(average_length, 1.0)
            )
            score += inverse_frequency * frequency * (k1 + 1.0) / denominator
        raw_scores.append(score)
    maximum = max(raw_scores, default=0.0)
    return [score / maximum if maximum else 0.0 for score in raw_scores]


def _semantic_scores(
    query: str,
    texts: list[str],
    *,
    deadline_monotonic: float | None = None,
) -> tuple[list[float], str]:
    if not texts:
        return [], current_embedding_model()
    try:
        _check_deadline(deadline_monotonic)
        remaining = (
            deadline_monotonic - time.monotonic()
            if deadline_monotonic is not None
            else None
        )
        vectors = embed_texts(
            [query, *texts],
            timeout_seconds=remaining,
        )
        _check_deadline(deadline_monotonic)
        query_vector = vectors[0]
        scores = []
        for vector in vectors[1:]:
            similarity = sum(left * right for left, right in zip(query_vector, vector))
            scores.append(max(0.0, min(1.0, float(similarity))))
        return scores, current_embedding_model()
    except Exception:
        return [0.0] * len(texts), "unavailable"


def hybrid_text_scores(
    query: str,
    texts: list[str],
    *,
    lexical_scores: list[float] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[list[float], list[float], list[float], str]:
    """Score text candidates with the same weights used by course retrieval.

    The optional provider makes offline evaluation deterministic without changing
    the provider selected for production retrieval.
    """

    lexical = (
        lexical_scores
        if lexical_scores is not None
        else _bm25_scores(
            query,
            texts,
            deadline_monotonic=deadline_monotonic,
        )
    )
    if len(lexical) != len(texts):
        raise ValueError("lexical score count must match text count")
    _check_deadline(deadline_monotonic)
    if embedding_provider is None:
        semantic, embedding_model = _semantic_scores(
            query,
            texts,
            deadline_monotonic=deadline_monotonic,
        )
    else:
        vectors = embedding_provider.embed([query, *texts])
        _check_deadline(deadline_monotonic)
        if len(vectors) != len(texts) + 1:
            raise ValueError("embedding provider returned an unexpected vector count")
        query_vector = vectors[0]
        semantic = [
            max(
                0.0,
                min(
                    1.0,
                    float(
                        sum(left * right for left, right in zip(query_vector, vector))
                    ),
                ),
            )
            for vector in vectors[1:]
        ]
        embedding_model = embedding_provider.embedding_model
    combined = [
        semantic_score * 0.35 + lexical_score * 0.55
        for lexical_score, semantic_score in zip(lexical, semantic)
    ]
    return combined, lexical, semantic, embedding_model


def rank_text_candidates(
    query: str,
    texts: list[str],
    *,
    document_keys: list[object],
    chunk_orders: list[int] | None = None,
    module_keys: list[object | None] | None = None,
    module_key: object | None = None,
    top_k: int = 5,
    max_candidates: int = 500,
    min_score: float = 0.12,
    embedding_provider: EmbeddingProvider | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[list[RankedTextCandidate], str]:
    """Run the shared candidate cap, hybrid ranking, and diversity selection."""

    count = len(texts)
    chunk_orders = chunk_orders or list(range(count))
    module_keys = module_keys or [None] * count
    if not (len(document_keys) == len(chunk_orders) == len(module_keys) == count):
        raise ValueError("candidate metadata count must match text count")

    lexical_scores = _bm25_scores(
        query,
        texts,
        deadline_monotonic=deadline_monotonic,
    )
    candidate_indices = list(range(count))
    if count > max_candidates:
        candidate_indices = sorted(
            candidate_indices,
            key=lambda index: (
                -lexical_scores[index],
                str(document_keys[index]),
                chunk_orders[index],
            ),
        )[:max_candidates]

    candidate_texts = [texts[index] for index in candidate_indices]
    candidate_lexical = [lexical_scores[index] for index in candidate_indices]
    combined, candidate_lexical, semantic, embedding_model = hybrid_text_scores(
        query,
        candidate_texts,
        lexical_scores=candidate_lexical,
        embedding_provider=embedding_provider,
        deadline_monotonic=deadline_monotonic,
    )
    ranked: list[RankedTextCandidate] = []
    for position, original_index in enumerate(candidate_indices):
        _check_deadline(deadline_monotonic)
        bonus = (
            1.0
            if module_key is not None and module_keys[original_index] == module_key
            else 0.0
        )
        score = combined[position] + bonus * 0.10
        if score < min_score:
            continue
        ranked.append(
            RankedTextCandidate(
                index=original_index,
                score=round(min(1.0, score), 4),
                semantic_score=round(semantic[position], 4),
                lexical_score=round(candidate_lexical[position], 4),
                module_bonus=bonus,
            )
        )

    per_document: Counter[object] = Counter()
    selected: list[RankedTextCandidate] = []
    for candidate in sorted(
        ranked,
        key=lambda item: (
            -item.score,
            str(document_keys[item.index]),
            chunk_orders[item.index],
        ),
    ):
        _check_deadline(deadline_monotonic)
        document_key = document_keys[candidate.index]
        if per_document[document_key] >= 2:
            continue
        selected.append(candidate)
        per_document[document_key] += 1
        if len(selected) >= top_k:
            break
    return selected, f"{RETRIEVAL_PIPELINE_VERSION}:{embedding_model}"


def _canvas_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def document_is_student_visible(
    document: Document,
    course: Course,
    *,
    now: datetime | None = None,
) -> bool:
    metadata = document.source_metadata or {}
    if course.source_type == "canvas" and metadata.get("student_visible") is not True:
        return False
    if course.source_type != "canvas" and metadata.get("student_visible") is False:
        return False
    if metadata.get("canvas_published") is False:
        return False
    if metadata.get("locked_for_user") is True or metadata.get("hidden") is True:
        return False
    if str(metadata.get("module_state") or "").strip().lower() in {
        "locked",
        "unpublished",
    }:
        return False
    if metadata.get("module_prerequisite_ids"):
        return False
    if metadata.get("module_require_sequential_progress") is True:
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    unlock_at = _canvas_timestamp(metadata.get("unlock_at"))
    lock_at = _canvas_timestamp(metadata.get("lock_at"))
    if metadata.get("unlock_at") and unlock_at is None:
        return False
    if metadata.get("lock_at") and lock_at is None:
        return False
    if unlock_at is not None and current < unlock_at:
        return False
    if lock_at is not None and current >= lock_at:
        return False
    return True


def resolve_retrieval_limits(
    *,
    max_candidates: int | None = None,
    min_score: float | None = None,
) -> tuple[int, float]:
    resolved_max = (
        max_candidates
        if max_candidates is not None
        else int(os.getenv("COURSE_COPILOT_MAX_CANDIDATES", "500"))
    )
    resolved_min = (
        min_score
        if min_score is not None
        else float(os.getenv("COURSE_COPILOT_MIN_SCORE", "0.12"))
    )
    if resolved_max < 1:
        raise ValueError("max_candidates must be at least 1")
    if not 0.0 <= resolved_min <= 1.0:
        raise ValueError("min_score must be between 0 and 1")
    return resolved_max, resolved_min


def retrieve_course_context(
    db: Session,
    course: Course,
    query: str,
    *,
    module_id: int | None = None,
    document_types: set[str] | None = None,
    student_visible_only: bool = False,
    top_k: int = 5,
    max_candidates: int | None = None,
    min_score: float | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    deadline_monotonic: float | None = None,
) -> tuple[list[RetrievalHit], str]:
    max_candidates, min_score = resolve_retrieval_limits(
        max_candidates=max_candidates,
        min_score=min_score,
    )
    _check_deadline(deadline_monotonic)
    rows = (
        db.query(Chunk, Document, CourseModule)
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(CourseModule, CourseModule.id == Document.course_module_id)
        .filter(
            Document.dataset_id == course.dataset_id,
            Document.status == "ready",
        )
        .order_by(Document.id, Chunk.idx)
        .all()
    )
    _check_deadline(deadline_monotonic)
    if document_types:
        rows = [
            row
            for row in rows
            if str((row[1].source_metadata or {}).get("document_type", "unknown"))
            in document_types
        ]
    if student_visible_only:
        rows = [row for row in rows if document_is_student_visible(row[1], course)]
    if module_id is not None:
        rows = [row for row in rows if row[1].course_module_id == module_id]
    candidates, method = rank_text_candidates(
        query,
        [chunk.text for chunk, _, _ in rows],
        document_keys=[document.id for _, document, _ in rows],
        chunk_orders=[chunk.idx for chunk, _, _ in rows],
        module_keys=[document.course_module_id for _, document, _ in rows],
        module_key=module_id,
        top_k=top_k,
        max_candidates=max_candidates,
        min_score=min_score,
        embedding_provider=embedding_provider,
        deadline_monotonic=deadline_monotonic,
    )
    selected = []
    for candidate in candidates:
        _check_deadline(deadline_monotonic)
        chunk, document, module = rows[candidate.index]
        quote = re.sub(r"\s+", " ", chunk.text).strip()[:900]
        selected.append(
            RetrievalHit(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                module_id=document.course_module_id,
                module_title=module.title if module else None,
                quote=quote,
                source_url=document.source or None,
                document_type=str(
                    (document.source_metadata or {}).get("document_type", "unknown")
                ),
                score=candidate.score,
                semantic_score=candidate.semantic_score,
                lexical_score=candidate.lexical_score,
                module_bonus=candidate.module_bonus,
            )
        )
    return selected, method
