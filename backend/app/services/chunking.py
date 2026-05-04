import re

try:
    from razdel import sentenize as _razdel_sentenize  # type: ignore
    _HAS_RAZDEL = True
except ImportError:
    _HAS_RAZDEL = False

# Fallback: split only on hard punctuation followed by whitespace, with a
# negative lookbehind that skips single-letter abbreviations (т., д., е.)
# and common Russian abbreviation roots.
_ABBREV_ROOT_RE = re.compile(
    r"\b(?:рис|табл|стр|проф|доц|акад|ул|пр|кв|гл|разд|см|ср|напр|д-р|mr|dr|no|vs)$",
    re.IGNORECASE,
)
_FALLBACK_SPLIT_RE = re.compile(r"[!?]\s+|\.{3,}\s+")


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, Russian-abbreviation-aware."""
    if _HAS_RAZDEL:
        return [s.text.strip() for s in _razdel_sentenize(text) if s.text.strip()]
    # Fallback: split on ! and ? unconditionally; split on . only when not
    # preceded by a single Cyrillic/Latin letter or a known abbreviation root.
    parts: list[str] = []
    buf_start = 0
    for m in re.finditer(r"[.!?]+", text):
        punct_start = m.start()
        after = text[m.end():]
        if not re.match(r"\s", after):
            continue  # no whitespace after punct → not a sentence boundary
        punct_char = m.group()[0]
        if punct_char == ".":
            before = text[:punct_start]
            word_m = re.search(r"(\w+)$", before)
            if word_m:
                word = word_m.group(1)
                if len(word) == 1 and word.isalpha():
                    continue  # initial / single-letter abbreviation
                if _ABBREV_ROOT_RE.search(word):
                    continue  # known abbreviation root
        parts.append(text[buf_start:m.end()].strip())
        buf_start = m.end()
    tail = text[buf_start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


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
    cleaned = " ".join(text.strip().split())
    if not cleaned:
        return []

    sentences = [s for s in _split_sentences(cleaned) if len(s) >= min_len]
    if not sentences:
        # Text is shorter than min_len or has no sentence boundaries —
        # return it as a single chunk (don't apply min_len to the whole text).
        part = cleaned[:max_chars]
        return [part] if part else []

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
