"""Course quality review stores redacted content, never student identities."""

import hashlib
import json
import logging
import re
import secrets
import threading
import uuid
from functools import lru_cache

from sqlalchemy import text

logger = logging.getLogger(__name__)
_ner_lock = threading.Lock()


@lru_cache(maxsize=1)
def _ner():
    from natasha import NewsEmbedding, NewsNERTagger, Segmenter

    return Segmenter(), NewsNERTagger(NewsEmbedding())


def redact(value: str) -> str:
    from natasha import Doc

    value = re.sub(
        r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", "[контакт]", value
    )
    value = re.sub(r"(?<!\w)(?:\+?\d[\s().-]*){7,}(?!\w)", "[номер]", value)
    value = re.sub(r"(?<!\w)@[\w.]+", "[контакт]", value)
    value = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", "[имя]", value)
    with _ner_lock:
        segmenter, tagger = _ner()
        doc = Doc(value)
        doc.segment(segmenter)
        doc.tag_ner(tagger)
        for span in reversed(doc.spans):
            if span.type == "PER":
                value = value[: span.start] + "[имя]" + value[span.stop :]
    return value


def settings(db, course_id: int) -> dict:
    row = (
        db.execute(
            text(
                "SELECT quality_enabled,allow_solutions,solution_after_attempts FROM portal_settings WHERE course_id=:course"
            ),
            {"course": course_id},
        )
        .mappings()
        .first()
    )
    return (
        dict(row)
        if row
        else {
            "quality_enabled": False,
            "allow_solutions": False,
            "solution_after_attempts": 2,
        }
    )


def purge(db, course_id: int):
    db.execute(
        text(
            "DELETE FROM portal_quality WHERE course_id=:course AND day <= CURRENT_DATE - 30"
        ),
        {"course": course_id},
    )


def record(db, session: dict, question: str, answer: dict, *, share: bool) -> dict:
    if (
        not share
        or session["role"] != "student"
        or not settings(db, session["course_id"])["quality_enabled"]
    ):
        return {}
    try:
        content = (
            answer["answer"]
            + "\n"
            + "\n".join(
                "\n".join([section["heading"], section["body"], *section["bullets"]])
                for section in answer.get("sections", [])
            )
        )
        if answer.get("diagram"):
            labels = {node["id"]: node["label"] for node in answer["diagram"]["nodes"]}
            content += "\nСхема: " + "; ".join(
                f"{labels[e['source']]} → {e['label']} → {labels[e['target']]}"
                for e in answer["diagram"]["edges"]
            )
        clean_question, clean_answer = redact(question[:4000]), redact(content[:20000])
    except Exception:  # noqa: BLE001 - Never fall back to retaining raw student text.
        logger.warning("Quality entry skipped: redaction unavailable")
        return {}
    ident, key = str(uuid.uuid4()), secrets.token_urlsafe(32)
    purge(db, session["course_id"])
    db.execute(
        text("""INSERT INTO portal_quality(id,course_id,question,answer,document_ids,feedback_key)
        VALUES (:id,:course,:question,:answer,CAST(:docs AS jsonb),:key)"""),
        {
            "id": ident,
            "course": session["course_id"],
            "question": clean_question,
            "answer": clean_answer,
            "docs": json.dumps(
                list(
                    dict.fromkeys(c["document_id"] for c in answer.get("citations", []))
                )
            ),
            "key": hashlib.sha256(key.encode()).hexdigest(),
        },
    )
    db.commit()
    return {"review_id": ident, "feedback_key": key}
