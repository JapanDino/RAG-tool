import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def split_into_chunks(
    text: str,
    min_len: int = 20,
    max_chars: int = 1500,
    overlap_chars: int = 150,
) -> list[str]:
    """Split *text* into sentence-aware chunks with optional overlap.

    Each chunk is at most *max_chars* characters long.  An overlap tail of
    *overlap_chars* characters from the previous chunk is prepended to the
    next one so that concepts straddling a boundary stay visible in both.
    """
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(cleaned) if len(s.strip()) >= min_len]
    if not sentences:
        part = cleaned[:max_chars]
        return [part] if len(part) >= min_len else []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def flush() -> str:
        joined = " ".join(current_parts)
        if len(joined) >= min_len:
            chunks.append(joined)
        return joined

    for sent in sentences:
        # A single sentence longer than max_chars is word-split.
        if len(sent) > max_chars:
            if current_parts:
                flush()
            sub_parts: list[str] = []
            sub_len = 0
            for word in sent.split():
                trial_len = sub_len + len(word) + (1 if sub_parts else 0)
                if trial_len <= max_chars:
                    sub_parts.append(word)
                    sub_len = trial_len
                else:
                    if sub_parts:
                        chunk = " ".join(sub_parts)
                        if len(chunk) >= min_len:
                            chunks.append(chunk)
                    sub_parts = [word]
                    sub_len = len(word)
            if sub_parts:
                chunk = " ".join(sub_parts)
                if len(chunk) >= min_len:
                    chunks.append(chunk)
            current_parts = []
            current_len = 0
            # Seed overlap from the last appended sub-chunk.
            if overlap_chars > 0 and chunks:
                seed = chunks[-1][-overlap_chars:].strip()
                if seed:
                    current_parts = [seed]
                    current_len = len(seed)
            continue

        added_len = current_len + len(sent) + (1 if current_parts else 0)
        if added_len > max_chars and current_parts:
            prev = flush()
            current_parts = []
            current_len = 0
            # Seed overlap from the end of the flushed chunk.
            if overlap_chars > 0 and prev:
                seed = prev[-overlap_chars:].strip()
                if seed:
                    current_parts = [seed]
                    current_len = len(seed)

        current_parts.append(sent)
        current_len = len(" ".join(current_parts))

    if current_parts:
        remaining = " ".join(current_parts)
        if len(remaining) >= min_len:
            chunks.append(remaining)

    return chunks if chunks else ([cleaned[:max_chars]] if len(cleaned) >= min_len else [])
