from __future__ import annotations

from statistics import mean, median, pstdev
from typing import Iterable

from sqlalchemy.orm import Session

from ..models.models import BloomAnnotation, BloomLevel, Chunk, Document


def calculate_score_distribution(annotations: Iterable[BloomAnnotation]) -> dict:
    scores = [a.score for a in annotations]
    if not scores:
        return {"count": 0, "min": None, "max": None, "mean": None, "median": None, "stdev": None}
    return {
        "count": len(scores),
        "min": min(scores),
        "max": max(scores),
        "mean": mean(scores),
        "median": median(scores),
        "stdev": pstdev(scores) if len(scores) > 1 else 0.0,
    }


def calculate_level_distribution(annotations: Iterable[BloomAnnotation]) -> dict:
    dist = {level.value: 0 for level in BloomLevel}
    for ann in annotations:
        level = ann.level.value if hasattr(ann.level, "value") else str(ann.level)
        dist.setdefault(level, 0)
        dist[level] += 1
    return dist


def calculate_consistency_metrics(chunk_id: int, db: Session) -> dict:
    annotations = db.query(BloomAnnotation).filter(BloomAnnotation.chunk_id == chunk_id).all()
    scores = [a.score for a in annotations]
    levels_present = len({a.level for a in annotations})
    levels_total = len(BloomLevel)
    return {
        "annotations": len(annotations),
        "levels_present": levels_present,
        "levels_total": levels_total,
        "coverage": (levels_present / levels_total) if levels_total else 0.0,
        "score_stdev": pstdev(scores) if len(scores) > 1 else 0.0,
    }


def calculate_coverage_metrics(dataset_id: int, db: Session) -> dict:
    total_chunks = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.dataset_id == dataset_id)
        .count()
    )
    annotated_chunks = (
        db.query(BloomAnnotation.chunk_id)
        .join(Chunk, BloomAnnotation.chunk_id == Chunk.id)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Document.dataset_id == dataset_id)
        .distinct()
        .count()
    )
    coverage = (annotated_chunks / total_chunks) if total_chunks else 0.0
    return {
        "chunks_total": total_chunks,
        "chunks_annotated": annotated_chunks,
        "coverage": coverage,
    }


__all__ = [
    "calculate_score_distribution",
    "calculate_level_distribution",
    "calculate_consistency_metrics",
    "calculate_coverage_metrics",
]

