import json as _json
import logging
import os
import re as _re

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..services.query_embed import embed_query
from ..utils.vector import vector_literal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])

_SYSTEM_PROMPT = """\
Ты — интеллектуальный ассистент образовательной платформы Bloom RAG.
Платформа извлекает знания из учебных курсов (Canvas LMS) и размечает их по таксономии Блума:
  • Remember (Запомни) — воспроизведение фактов
  • Understand (Пойми) — объяснение смысла
  • Apply (Примени) — использование в новых ситуациях
  • Analyze (Проанализируй) — разложение на части, выявление связей
  • Evaluate (Оцени) — суждения по критериям
  • Create (Создай) — генерация нового

Ниже — фрагменты из базы знаний, найденные по запросу пользователя.
Используй их для ответа. Если фрагменты не помогают — отвечай из общих знаний.
При ссылке на конкретный узел указывай его название в кавычках.

КОНТЕКСТ ИЗ БАЗЫ:
{context}
{courses_section}
УПРАВЛЕНИЕ ИНТЕРФЕЙСОМ:
Если пользователь просит выполнить действие в приложении (например «проанализируй курс биологии»,
«переключись на граф», «открой поиск»), используй команды [ACTION: {{...}}] на отдельной строке.
Доступные команды:
  Переключить вкладку: [ACTION: {{"type": "switchTab", "tab": "canvas"}}]
    Вкладки: analysis, graph, labeling, search, dashboard, canvas
  Выбрать курс: [ACTION: {{"type": "selectCourse", "course_id": 1234}}]
  Запустить анализ курса: [ACTION: {{"type": "startIngest"}}]

Пример ответа на «проанализируй курс биологии»:
[ACTION: {{"type": "switchTab", "tab": "canvas"}}]
[ACTION: {{"type": "selectCourse", "course_id": 5718}}]
[ACTION: {{"type": "startIngest"}}]
Открываю вкладку Canvas и запускаю анализ курса «Биология»…
"""


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class UiContext(BaseModel):
    courses: list[dict] = []  # [{id: int, name: str}]
    active_tab: str = "analysis"
    dataset_id: int | None = None


class ChatRequest(BaseModel):
    message: str
    dataset_id: int | None = None
    history: list[ChatMessage] = []
    top_k: int = 6
    ui_context: UiContext | None = None


def _search_context(message: str, dataset_id: int | None, top_k: int, db: Session) -> str:
    try:
        qvec = embed_query(message)
    except Exception as exc:
        logger.warning("chat embed failed: %s", exc)
        return "(поиск по базе недоступен)"

    qvec_str = vector_literal(qvec)
    em = os.getenv("EMBEDDING_MODEL_LOCAL", "")
    full_model = f"local:{em}:padded1536" if em else None

    ds_filter = "AND kn.dataset_id = :ds" if dataset_id else ""
    model_filter = "AND kn.embedding_model = :em" if full_model else ""

    sql = f"""
        WITH q AS (SELECT CAST(:qvec AS vector) AS v)
        SELECT kn.title,
               kn.context_text,
               kn.top_levels,
               kn.model_info,
               1.0 - (kn.vec <=> (SELECT v FROM q)) AS score
        FROM knowledge_nodes kn
        WHERE kn.vec IS NOT NULL
          {ds_filter}
          {model_filter}
        ORDER BY kn.vec <=> (SELECT v FROM q)
        LIMIT :k
    """
    params: dict = {"qvec": qvec_str, "k": top_k}
    if dataset_id:
        params["ds"] = dataset_id
    if full_model:
        params["em"] = full_model

    from sqlalchemy import text
    rows = db.execute(text(sql), params).fetchall()

    if not rows:
        return "(в базе знаний ничего не найдено)"

    parts = []
    for row in rows:
        levels = ", ".join(row.top_levels or [])
        rationale = ""
        try:
            mi = row.model_info or {}
            rationale = mi.get("rationale") or ""
        except Exception:
            pass
        topic = ""
        try:
            t = (row.model_info or {}).get("topic")
            if t and t.get("subject"):
                topic = " | Тема: " + " → ".join(filter(None, [t.get("subject"), t.get("topic"), t.get("subtopic")]))
        except Exception:
            pass
        snippet = (row.context_text or "")[:300]
        score_pct = int((row.score or 0) * 100)
        parts.append(
            f"[{score_pct}%] «{row.title}» (Bloom: {levels}{topic})\n"
            f"  {snippet}"
            + (f"\n  Обоснование: {rationale}" if rationale else "")
        )

    return "\n\n".join(parts)


def _sse(data: str) -> str:
    return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_action(buf: str, start: int) -> tuple[dict | None, int] | None:
    """Parse [ACTION: {...}] starting at buf[start]. Returns (action_dict, end_pos) or None."""
    prefix = "[ACTION:"
    if not buf[start:].startswith(prefix):
        return None
    json_start = buf.find("{", start + len(prefix))
    if json_start == -1:
        return None
    depth = 0
    json_end = -1
    for i in range(json_start, len(buf)):
        if buf[i] == "{":
            depth += 1
        elif buf[i] == "}":
            depth -= 1
            if depth == 0:
                json_end = i
                break
    if json_end == -1:
        return None
    closing = buf.find("]", json_end)
    if closing == -1:
        return None
    try:
        action = _json.loads(buf[json_start : json_end + 1])
        return action, closing + 1
    except Exception:
        return action if False else None  # invalid JSON


@router.post("/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)):
    def generate():
        context = _search_context(payload.message, payload.dataset_id, payload.top_k, db)

        courses_section = ""
        if payload.ui_context and payload.ui_context.courses:
            lines = "\n".join(
                f"  - ID {c.get('id')}: {c.get('name', '?')}"
                for c in payload.ui_context.courses[:40]
            )
            courses_section = f"\nДОСТУПНЫЕ КУРСЫ:\n{lines}\n"

        system = _SYSTEM_PROMPT.format(context=context, courses_section=courses_section)

        messages = [{"role": "system", "content": "/no_think\n" + system}]
        for h in payload.history[-10:]:
            messages.append({"role": h.role, "content": h.content})
        messages.append({"role": "user", "content": payload.message})

        model = os.getenv("LLM_MODEL", "qwen3:14b")
        try:
            from ..services.openai_client import chat_completion_stream
            buf = ""
            for chunk in chat_completion_stream(model, messages, max_tokens=1024):
                buf += chunk
                # Extract complete [ACTION: {...}] blocks
                while True:
                    action_pos = buf.find("[ACTION:")
                    if action_pos == -1:
                        break
                    result = _extract_action(buf, action_pos)
                    if result is None:
                        break  # incomplete block, wait for more chunks
                    action, end_pos = result
                    # Flush text before action
                    before = buf[:action_pos].rstrip("\n")
                    if before:
                        yield _sse({"type": "chunk", "text": before})
                    yield _sse({"type": "action", "action": action})
                    buf = buf[end_pos:].lstrip("\n")
                # Flush safe prefix (leave 20 chars as lookahead for partial "[ACTION:")
                if len(buf) > 20 and "[" not in buf[:-20]:
                    safe = len(buf) - 20
                    yield _sse({"type": "chunk", "text": buf[:safe]})
                    buf = buf[safe:]
            # Flush remainder
            if buf:
                yield _sse({"type": "chunk", "text": buf})
        except Exception as exc:
            logger.error("chat stream error: %s", exc)
            yield _sse({"type": "error", "message": str(exc)})

        yield _sse({"type": "done"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
