from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..db.session import get_db
import csv, io, json
router = APIRouter(prefix="/export", tags=["export"])

@router.get("/datasets/{dataset_id}")
def export_dataset(
    dataset_id: int,
    format: str = Query("jsonl", pattern="^(jsonl|csv|qti|moodle_xml|ragpkg)$"),
    level: str | None = Query(
        None, pattern="^(remember|understand|apply|analyze|evaluate|create)$"
    ),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    base_sql = """
        SELECT c.id as chunk_id, c.text, d.title as document_title,
               coalesce(a.level::text,'') as level, coalesce(a.label,'') as label,
               coalesce(a.rationale,'') as rationale, coalesce(a.score,0) as score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        LEFT JOIN LATERAL (
            SELECT * FROM bloom_annotations a2 WHERE a2.chunk_id=c.id ORDER BY a2.created_at DESC LIMIT 1
        ) a ON true
        WHERE d.dataset_id = :ds
        ORDER BY d.id, c.idx
    """
    if level:
        base_sql = base_sql.replace("ORDER BY", "AND a.level = :lvl ORDER BY")
    if min_score is not None:
        base_sql = base_sql.replace(
            "ORDER BY", "AND coalesce(a.score,0) >= :minsc ORDER BY"
        )
    params = {"ds": dataset_id}
    if level:
        params["lvl"] = level
    if min_score is not None:
        params["minsc"] = float(min_score)
    rows = db.execute(text(base_sql), params).mappings().all()

    if format=="jsonl":
        buf = io.StringIO()
        for r in rows: buf.write(json.dumps(dict(r), ensure_ascii=False)+"\n")
        return Response(buf.getvalue(), media_type="application/x-ndjson")
    if format=="csv":
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()) if rows else ["chunk_id","text","document_title","level","label","rationale","score"])
        w.writeheader(); [w.writerow(dict(r)) for r in rows]
        return Response(buf.getvalue(), media_type="text/csv")
    if format=="qti":
        # Простейший QTI XML-плейсхолдер
        from xml.sax.saxutils import escape
        items = []
        for i,r in enumerate(rows,1):
            body = escape(r["text"][:200])
            items.append(f'<item ident="item{i}"><presentation><material><mattext>{body}</mattext></material></presentation></item>')
        xml = f'<?xml version="1.0" encoding="UTF-8"?><questestinterop>{"".join(items)}</questestinterop>'
        return Response(xml, media_type="application/xml")
    if format=="moodle_xml":
        from xml.sax.saxutils import escape
        qs = []
        for i,r in enumerate(rows,1):
            body = escape(r["text"][:200])
            qs.append(f'<question type="essay"><name><text>chunk{i}</text></name><questiontext format="html"><text><![CDATA[{body}]]></text></questiontext></question>')
        xml = f'<?xml version="1.0" encoding="UTF-8"?><quiz>{"".join(qs)}</quiz>'
        return Response(xml, media_type="application/xml")
    if format=="ragpkg":
        pkg = {"version":"0.1","dataset_id":dataset_id,"items":[dict(r) for r in rows]}
        return pkg

    raise HTTPException(400, "unsupported format")
