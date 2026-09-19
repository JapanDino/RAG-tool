"""Learning workspace and opt-in course quality review."""

import hashlib
import json
import secrets
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from ..services import course_quality
from ..services.answer_stream import draft_answer, stream_completion
from ..services.lti_security import rate_limit, require_teacher
from ..services.openai_client import extract_json_block
from . import portal

router = APIRouter(prefix="/portal", tags=["Learning workspace"])


class Settings(portal.StrictInput):
    quality_enabled: bool
    allow_solutions: bool
    solution_after_attempts: int = portal.Field(ge=1, le=5)


@router.get("/preferences")
def preferences(session: portal.SessionUser, db: portal.Database):
    return course_quality.settings(db, session["course_id"])


@router.put("/preferences")
def update_preferences(
    payload: Settings, session: portal.SessionUser, db: portal.Database
):
    require_teacher(session)
    db.execute(
        text("""INSERT INTO portal_settings(course_id,quality_enabled,allow_solutions,solution_after_attempts)
        VALUES (:course,:quality_enabled,:allow_solutions,:solution_after_attempts)
        ON CONFLICT(course_id) DO UPDATE SET quality_enabled=EXCLUDED.quality_enabled,
        allow_solutions=EXCLUDED.allow_solutions,solution_after_attempts=EXCLUDED.solution_after_attempts"""),
        {"course": session["course_id"], **payload.model_dump()},
    )
    db.commit()
    return payload.model_dump()


@router.get("/quality")
def quality(
    session: portal.SessionUser,
    db: portal.Database,
    status: Literal["all", "open", "resolved"] = "open",
    offset: int = 0,
):
    require_teacher(session)
    if offset < 0 or offset > 10000:
        raise HTTPException(422, "Некорректная страница")
    course_quality.purge(db, session["course_id"])
    rows = (
        db.execute(
            text("""SELECT id,day,question,answer,document_ids,feedback,status FROM portal_quality
        WHERE course_id=:course AND (:status='all' OR status=:status) ORDER BY day DESC,id LIMIT 51 OFFSET :offset"""),
            {"course": session["course_id"], "status": status, "offset": offset},
        )
        .mappings()
        .all()
    )
    db.commit()
    return {
        "entries": [dict(row) for row in rows[:50]],
        "has_more": len(rows) > 50,
        "retention_days": 30,
    }


class ReviewStatus(portal.StrictInput):
    status: Literal["open", "resolved"]


@router.patch("/quality/{entry_id}")
def review(
    entry_id: UUID,
    payload: ReviewStatus,
    session: portal.SessionUser,
    db: portal.Database,
):
    require_teacher(session)
    row = db.execute(
        text(
            "UPDATE portal_quality SET status=:status WHERE id=:id AND course_id=:course RETURNING id"
        ),
        {"id": entry_id, "course": session["course_id"], "status": payload.status},
    ).scalar()
    if not row:
        raise HTTPException(404, "Запись недоступна")
    db.commit()
    return {"saved": True}


class AnswerFeedback(portal.StrictInput):
    feedback: Literal["helpful", "incorrect", "unclear", "wrong_source"]
    feedback_key: str = portal.Field(min_length=20, max_length=100)


@router.post("/quality/{entry_id}/feedback")
def answer_feedback(
    entry_id: UUID,
    payload: AnswerFeedback,
    session: portal.SessionUser,
    db: portal.Database,
):
    rate_limit(session, "answer-feedback", 60)
    stored = db.execute(
        text(
            "SELECT feedback_key FROM portal_quality WHERE id=:id AND course_id=:course AND day >= CURRENT_DATE-30"
        ),
        {"id": entry_id, "course": session["course_id"]},
    ).scalar()
    if not stored or not secrets.compare_digest(
        stored, hashlib.sha256(payload.feedback_key.encode()).hexdigest()
    ):
        raise HTTPException(404, "Запись недоступна")
    db.execute(
        text("UPDATE portal_quality SET feedback=:feedback,status='open' WHERE id=:id"),
        {"id": entry_id, "feedback": payload.feedback},
    )
    db.commit()
    return {"saved": True}


@router.post("/chat/stream")
async def stream_chat(
    payload: portal.Question, session: portal.SessionUser, db: portal.Database
):
    portal.validate_preview(session, payload)
    session = {**session, "_preview": payload.preview}
    rate_limit(session, "chat", 60)
    if not payload.message.strip():
        raise HTTPException(422, "Введите вопрос")

    def encode(event, **data):
        return json.dumps({"event": event, **data}, ensure_ascii=False) + "\n"

    async def events():
        try:
            yield encode("status", message="Ищем материалы…")
            await run_in_threadpool(portal.metric, db, session, "questions")
            passages, candidates, prompt = await run_in_threadpool(
                portal.prepare_chat, db, session, payload
            )
            if not passages:
                await run_in_threadpool(portal.metric, db, session, "no_context")
                result = {"answer": portal.NO_ANSWER, "citations": []}
            else:
                yield encode("status", message="Готовим объяснение…")
                prompt = (
                    "В JSON сначала выведи citations, затем answer, после них остальные поля.\n"
                    + prompt
                )
                raw, shown = "", ""
                async for fragment in stream_completion(prompt):
                    raw += fragment
                    if len(raw) > 50000:
                        raise ValueError("Answer exceeds limit")
                    preview = draft_answer(raw, {p["id"] for p in passages})
                    if preview and preview != shown:
                        shown = preview
                        yield encode("draft", answer=preview)
                yield encode("status", message="Проверяем источники…")
                result = await run_in_threadpool(
                    portal.finish_answer,
                    db,
                    session,
                    payload,
                    passages,
                    candidates,
                    json.loads(extract_json_block(raw)),
                )
            await run_in_threadpool(
                portal.course_review.record_preview, db, session, payload, result
            )
            review = await run_in_threadpool(
                lambda: course_quality.record(
                    db,
                    session,
                    payload.message,
                    result,
                    share=payload.share_for_review and not payload.preview,
                )
            )
            result.update(review)
            yield encode("result", result=result)
        except HTTPException as exc:
            await run_in_threadpool(db.rollback)
            await run_in_threadpool(portal.metric, db, session, "errors")
            yield encode("error", message=str(exc.detail), status=exc.status_code)
        except Exception:  # noqa: BLE001 - Fail closed at the external service boundary.
            await run_in_threadpool(db.rollback)
            await run_in_threadpool(portal.metric, db, session, "errors")
            yield encode(
                "error",
                message="Не удалось завершить ответ. Вопрос сохранён для повтора.",
                status=502,
            )

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
