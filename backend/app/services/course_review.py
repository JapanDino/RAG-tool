"""Evidence stays separate from a teacher's persisted judgement."""

import hashlib

from sqlalchemy import text


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def document_hash(db, document_id):
    chunks = (
        db.execute(
            text("SELECT text FROM chunks WHERE document_id=:doc ORDER BY idx,id"),
            {"doc": document_id},
        )
        .scalars()
        .all()
    )
    return text_hash("\n".join(chunks))


def reviews(db, course_id):
    rows = db.execute(
        text("SELECT * FROM portal_bloom_reviews WHERE course_id=:course"),
        {"course": course_id},
    ).mappings()
    return {(r["document_id"], r["text_hash"]): dict(r) for r in rows}


def record_preview(db, session, payload, result):
    if not payload.preview or not result.get("citations"):
        return
    doc = payload.context.document_id
    db.execute(
        text("""INSERT INTO portal_preview_checks(course_id,document_id,content_hash)
        VALUES (:course,:doc,:hash) ON CONFLICT(course_id,document_id)
        DO UPDATE SET content_hash=EXCLUDED.content_hash,checked_at=NOW()"""),
        {"course": session["course_id"], "doc": doc, "hash": document_hash(db, doc)},
    )
    db.commit()
