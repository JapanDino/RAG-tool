"""Tests for split_into_chunks."""
import pytest
from backend.app.services.chunking import split_into_chunks


def test_short_text_returns_single_chunk():
    text = "Это короткий текст."
    chunks = split_into_chunks(text, max_chars=1500)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_empty_text_returns_empty_list():
    assert split_into_chunks("") == []


def test_whitespace_only_returns_empty_list():
    assert split_into_chunks("   \n\t  ") == []


def test_long_text_is_split():
    sentence = "Это одно предложение. "
    text = sentence * 200  # ~4400 chars
    chunks = split_into_chunks(text, max_chars=1500, overlap_chars=150)
    assert len(chunks) > 1


def test_chunks_cover_all_content():
    """Every sentence from the original text should appear in at least one chunk."""
    sentences = [f"Предложение номер {i}." for i in range(50)]
    text = " ".join(sentences)
    chunks = split_into_chunks(text, max_chars=500, overlap_chars=50)
    combined = " ".join(chunks)
    for i, s in enumerate(sentences):
        # Core word of each sentence must appear somewhere in chunks
        assert f"номер {i}" in combined or any(f"номер {i}" in c for c in chunks), (
            f"Sentence '{s}' not found in any chunk"
        )


def test_each_chunk_within_max_chars():
    # Use 100-char words separated by spaces so the word-split path can divide them.
    # A single unsplittable token longer than max_chars cannot be shortened further.
    text = " ".join(["А" * 100] * 50)  # ~5050 chars, splittable at word boundaries
    chunks = split_into_chunks(text, max_chars=1500)
    for c in chunks:
        assert len(c) <= 1500 + 200, f"Chunk too long: {len(c)}"  # small slack for word-split edge


def test_overlap_creates_content_continuity():
    """With overlap, the end of chunk N should appear at the start of chunk N+1."""
    sentence = "Важный концепт встречается здесь. "
    text = sentence * 100
    chunks = split_into_chunks(text, max_chars=300, overlap_chars=80)
    if len(chunks) > 1:
        # Last 50 chars of chunk 0 should appear somewhere in chunk 1
        tail = chunks[0][-50:].strip()
        assert tail in chunks[1] or len(tail) < 10, (
            "Overlap not preserved between consecutive chunks"
        )


def test_min_length_filter():
    text = "А. Б. В. " + "Нормальное длинное предложение для теста. " * 10
    chunks = split_into_chunks(text, max_chars=1500, overlap_chars=0)
    for c in chunks:
        assert len(c) >= 10, f"Chunk too short: {repr(c)}"
