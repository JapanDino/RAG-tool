import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_into_chunks(text: str, min_len: int = 20) -> list[str]:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    parts = [p.strip() for p in SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    chunks = [p for p in parts if len(p) >= min_len]
    if not chunks:
        return [cleaned]
    return chunks
