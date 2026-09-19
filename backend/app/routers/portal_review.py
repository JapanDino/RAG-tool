"""Teacher-only course preparation and expert Bloom annotations."""

import json
from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from ..services import course_review
from ..services.bloom_rubric import classify_learning_demands
from ..services.lti_security import require_teacher
from . import portal, portal_imports

router = APIRouter(prefix="/portal", tags=["Course preparation"])
Level = Literal["remember", "understand", "apply", "analyze", "evaluate", "create"]
Knowledge = Literal["factual", "conceptual", "procedural", "metacognitive"]


class BloomReview(portal.StrictInput):
    text_hash: str = portal.Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = portal.Field(default=0, ge=0)
    decision: Literal["confirmed", "corrected", "needs_context"]
    levels: list[Level] = portal.Field(default_factory=list, max_length=6)
    knowledge: list[Knowledge] = portal.Field(default_factory=list, max_length=4)
    comment: str = portal.Field(default="", max_length=2000)


@router.put("/analysis/{chunk_id}/review")
def review(
    chunk_id: int,
    payload: BloomReview,
    session: portal.SessionUser,
    db: portal.Database,
):
    require_teacher(session)
    row = (
        db.execute(
            text("""SELECT c.text,c.document_id FROM chunks c JOIN portal_materials m ON m.document_id=c.document_id
        JOIN documents d ON d.id=c.document_id WHERE c.id=:chunk AND m.course_id=:course AND d.dataset_id=:dataset
        AND (c.meta->>'image_context') IS DISTINCT FROM 'true'"""),
            {
                "chunk": chunk_id,
                "course": session["course_id"],
                "dataset": session["dataset_id"],
            },
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(404, "Фрагмент недоступен")
    if course_review.text_hash(row["text"]) != payload.text_hash:
        raise HTTPException(409, "Текст изменился. Обновите анализ перед сохранением.")
    automatic = classify_learning_demands(row["text"])
    levels, knowledge = sorted(set(payload.levels)), sorted(set(payload.knowledge))
    if payload.decision == "confirmed" and (
        set(levels) != set(automatic["levels"])
        or set(knowledge) != set(automatic["knowledge"])
    ):
        raise HTTPException(422, "Для изменённой разметки выберите «Исправить».")
    if payload.decision == "needs_context":
        levels, knowledge = [], []
    result = (
        db.execute(
            text("""INSERT INTO portal_bloom_reviews(course_id,document_id,text_hash,decision,levels,knowledge,comment,automatic)
        SELECT :course,:doc,CAST(:hash AS varchar),:decision,CAST(:levels AS jsonb),CAST(:knowledge AS jsonb),:comment,CAST(:automatic AS jsonb)
        WHERE :revision=0 OR EXISTS(SELECT 1 FROM portal_bloom_reviews WHERE course_id=:course AND document_id=:doc AND text_hash=:hash)
        ON CONFLICT(course_id,document_id,text_hash) DO UPDATE SET decision=EXCLUDED.decision,levels=EXCLUDED.levels,
        knowledge=EXCLUDED.knowledge,comment=EXCLUDED.comment,automatic=EXCLUDED.automatic,
        revision=portal_bloom_reviews.revision+1,updated_at=NOW() WHERE portal_bloom_reviews.revision=:revision RETURNING *"""),
            {
                "course": session["course_id"],
                "doc": row["document_id"],
                "hash": payload.text_hash,
                "decision": payload.decision,
                "levels": json.dumps(levels),
                "knowledge": json.dumps(knowledge),
                "comment": payload.comment.strip(),
                "automatic": json.dumps(automatic),
                "revision": payload.revision,
            },
        )
        .mappings()
        .first()
    )
    if not result:
        db.rollback()
        raise HTTPException(
            409, "Разметка уже изменена другим преподавателем. Обновите анализ."
        )
    db.commit()
    return dict(result)


@router.get("/readiness")
def readiness(session: portal.SessionUser, db: portal.Database):
    require_teacher(session)
    model = portal.current_embedding_model()
    rows = (
        db.execute(
            text("""SELECT m.document_id,m.published,m.kind,m.imported_at,m.unavailable_reason,d.title,d.status,
        (SELECT COUNT(*) FROM chunks c WHERE c.document_id=d.id AND (c.meta->>'image_context') IS DISTINCT FROM 'true') AS chunks,
        (SELECT COUNT(DISTINCT c.id) FROM chunks c JOIN embeddings e ON e.chunk_id=c.id
         WHERE c.document_id=d.id AND (c.meta->>'image_context') IS DISTINCT FROM 'true' AND e.model=:model AND e.vec IS NOT NULL) AS indexed,
        p.content_hash,p.checked_at
        FROM portal_materials m JOIN documents d ON d.id=m.document_id
        LEFT JOIN portal_preview_checks p ON p.course_id=m.course_id AND p.document_id=d.id
        WHERE m.course_id=:course AND d.dataset_id=:dataset ORDER BY d.id"""),
            {
                "course": session["course_id"],
                "dataset": session["dataset_id"],
                "model": model,
            },
        )
        .mappings()
        .all()
    )
    items = []
    for row in rows:
        item = dict(row)
        problems = []
        if not row["chunks"]:
            problems.append("Не извлечён учебный текст")
        elif row["indexed"] < row["chunks"]:
            problems.append("Поисковый индекс неполный или устарел")
        if row["status"] != "ready":
            problems.append("Обработка материала не завершена")
        if row["unavailable_reason"]:
            problems.append(row["unavailable_reason"])
        tested = bool(
            row["content_hash"]
            and row["content_hash"]
            == course_review.document_hash(db, row["document_id"])
        )
        item.update(problems=problems, preview_checked=tested)
        item.pop("content_hash")
        items.append(item)
    return {
        "materials": items,
        "last_import": portal_imports.latest(session, db),
        "counts": {
            "total": len(items),
            "published": sum(i["published"] for i in items),
            "drafts": sum(not i["published"] for i in items),
            "problems": sum(bool(i["problems"]) for i in items),
            "preview_checked": sum(i["preview_checked"] for i in items),
        },
        "note": "Сводка локальной подготовки, а не сертификат готовности интеграции. Доступность Canvas повторно проверяется при открытии источника и ответе. Проверка чата означает получение ответа со ссылками, но не подтверждает его правильность.",
    }
