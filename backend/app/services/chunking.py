import re

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
WHITESPACE_RE = re.compile(r"\s+")
STRUCTURED_LINE_RE = re.compile(r"^(#{1,6}\s+|[-*\u2022]\s+|\d+[.)]\s+)")
HEADING_LIKE_RE = re.compile(r"^[A-Z0-9\u0400-\u04FF][^.!?]{0,80}:$")


def _normalize_line(line: str) -> str:
    return WHITESPACE_RE.sub(" ", line.strip())


def _is_structured_line(line: str) -> bool:
    if not line:
        return False
    return bool(STRUCTURED_LINE_RE.match(line) or HEADING_LIKE_RE.match(line))


def _structured_units(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    units: list[str] = []
    paragraph_parts: list[str] = []

    def flush_paragraph() -> None:
        if paragraph_parts:
            units.append(" ".join(paragraph_parts))
            paragraph_parts.clear()

    for raw_line in lines:
        line = _normalize_line(raw_line)
        if not line:
            flush_paragraph()
            continue
        if _is_structured_line(line):
            flush_paragraph()
            units.append(line)
            continue
        paragraph_parts.append(line)

    flush_paragraph()
    return units


def _split_long_unit(unit: str, min_len: int, max_chars: int) -> list[str]:
    if len(unit) <= max_chars:
        if len(unit) >= min_len or _is_structured_line(unit):
            return [unit]
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(unit) if s.strip()]
    if len(sentences) <= 1:
        sentences = unit.split()
        if not sentences:
            return []

    pieces: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for part in sentences:
        trial_len = current_len + len(part) + (1 if current_parts else 0)
        if trial_len <= max_chars:
            current_parts.append(part)
            current_len = trial_len
            continue

        if current_parts:
            joined = " ".join(current_parts)
            if len(joined) >= min_len:
                pieces.append(joined)
        current_parts = []
        current_len = 0

        if len(part) <= max_chars:
            current_parts = [part]
            current_len = len(part)
            continue

        sub_parts: list[str] = []
        sub_len = 0
        for word in part.split():
            word_len = sub_len + len(word) + (1 if sub_parts else 0)
            if word_len <= max_chars:
                sub_parts.append(word)
                sub_len = word_len
            else:
                joined = " ".join(sub_parts)
                if len(joined) >= min_len:
                    pieces.append(joined)
                sub_parts = [word]
                sub_len = len(word)
        if sub_parts:
            joined = " ".join(sub_parts)
            if len(joined) >= min_len:
                pieces.append(joined)

    if current_parts:
        joined = " ".join(current_parts)
        if len(joined) >= min_len:
            pieces.append(joined)

    return pieces


def _join_chunk(parts: list[str]) -> str:
    return "\n\n".join(parts).strip()


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
    Uses razdel for Russian-aware sentence splitting when available.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    units = _structured_units(cleaned)
    if not units:
        part = _normalize_line(cleaned)[:max_chars]
        return [part] if len(part) >= min_len else []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    def flush() -> str:
        joined = _join_chunk(current_parts)
        if len(joined) >= min_len:
            chunks.append(joined)
        return joined

    for unit in units:
        split_units = _split_long_unit(unit, min_len=min_len, max_chars=max_chars)
        if not split_units:
            continue

        for split_unit in split_units:
            separator_len = 2 if current_parts else 0
            added_len = current_len + len(split_unit) + separator_len
            if added_len > max_chars and current_parts:
                prev = flush()
                current_parts = []
                current_len = 0
                if overlap_chars > 0 and prev:
                    seed = prev[-overlap_chars:].strip()
                    if seed:
                        current_parts = [seed]
                        current_len = len(seed)

            if len(split_unit) > max_chars:
                # Defensive fallback for pathological inputs.
                if current_parts:
                    flush()
                    current_parts = []
                    current_len = 0
                chunk = split_unit[:max_chars].strip()
                if len(chunk) >= min_len:
                    chunks.append(chunk)
                continue

            current_parts.append(split_unit)
            current_len = len(_join_chunk(current_parts))

    if current_parts:
        remaining = _join_chunk(current_parts)
        if len(remaining) >= min_len:
            chunks.append(remaining)

    # If no chunks were produced (e.g. the whole text is shorter than min_len),
    # return the full text as one chunk rather than silently discarding it.
    if not chunks:
        fallback = _normalize_line(cleaned)[:max_chars]
        return [fallback] if fallback else []
    return chunks
