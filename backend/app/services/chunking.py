import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
SENTENCE_WITH_OFFSETS_RE = re.compile(r"\S(?:.*?\S)?(?:[.!?](?=\s|$)|$)", re.DOTALL)


def split_into_chunks(text: str, min_len: int = 20) -> list[str]:
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []
    parts = [p.strip() for p in SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    chunks = [p for p in parts if len(p) >= min_len]
    if not chunks:
        return [cleaned]
    return chunks


def chunk_text_with_offsets(
    text: str,
    max_chars: int = 1200,
    min_chars: int = 120,
) -> list[dict]:
    """Build sentence-aware chunks while preserving offsets into the source text."""
    if not text or not text.strip():
        return []
    sentences = [
        {"text": match.group(0).strip(), "start": match.start(), "end": match.end()}
        for match in SENTENCE_WITH_OFFSETS_RE.finditer(text)
        if match.group(0).strip()
    ]
    if not sentences:
        stripped = text.strip()
        start = text.find(stripped)
        return [
            {
                "text": stripped,
                "start": start,
                "end": start + len(stripped),
                "sentence_start": 0,
                "sentence_end": 0,
            }
        ]

    chunks: list[dict] = []
    current: list[dict] = []
    current_len = 0
    first_sentence = 0

    def flush(last_sentence: int) -> None:
        nonlocal current, current_len, first_sentence
        if not current:
            return
        start = current[0]["start"]
        end = current[-1]["end"]
        chunks.append(
            {
                "text": text[start:end].strip(),
                "start": start,
                "end": end,
                "sentence_start": first_sentence,
                "sentence_end": last_sentence,
            }
        )
        current = []
        current_len = 0

    for index, sentence in enumerate(sentences):
        sentence_len = len(sentence["text"])
        if (
            current
            and current_len + sentence_len + 1 > max_chars
            and current_len >= min_chars
        ):
            flush(index - 1)
            first_sentence = index
        if not current:
            first_sentence = index
        current.append(sentence)
        current_len += sentence_len + (1 if current_len else 0)
    flush(len(sentences) - 1)
    return chunks
