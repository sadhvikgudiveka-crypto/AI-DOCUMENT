import pytest

from backend.app.core import chunk_pages, extract_text, local_embedding, retrieve
from backend.app.providers import AIProvider


def test_extract_text_reads_utf8_text():
    pages = extract_text("notes.txt", b"First line\nSecond line")
    assert pages == [(None, "First line\nSecond line")]


def test_extract_text_rejects_unsupported_and_invalid_text():
    with pytest.raises(ValueError, match="PDF or plain-text"):
        extract_text("notes.docx", b"no")
    with pytest.raises(ValueError, match="valid UTF-8"):
        extract_text("notes.txt", b"\xff")


def test_chunk_pages_preserves_page_and_overlaps():
    text = "word " * 120
    chunks = chunk_pages([(3, text)], size=120, overlap=20)
    assert len(chunks) > 1
    assert all(chunk.page == 3 for chunk in chunks)
    assert chunks[0].end > chunks[1].start


def test_retrieve_ranks_related_chunk_first():
    pages = [
        (1, "Photosynthesis converts sunlight into chemical energy. " * 4),
        (2, "The annual budget outlines projected costs and revenue. " * 4),
    ]
    chunks = chunk_pages(pages, size=200, overlap=20)
    for chunk in chunks:
        chunk.vector = local_embedding(chunk.text)
    result = retrieve(chunks, local_embedding("How does photosynthesis use sunlight?"), limit=1)
    assert result[0].page == 1


def test_demo_answer_uses_relevant_sentence_and_declines_unsupported_question():
    chunks = chunk_pages([(
        None,
        "Gardens need seasonal blooms. Avoid pesticides because they harm bees. Leave bare soil for nesting.",
    )])
    answer, source_ids = AIProvider._demo_answer("Why avoid pesticides?", chunks)
    assert answer == "Avoid pesticides because they harm bees."
    assert source_ids == [chunks[0].id]
    answer, source_ids = AIProvider._demo_answer("What is the moon made of?", chunks)
    assert "couldn't find enough information" in answer
    assert source_ids == []


def test_demo_answer_supports_summary_prompts():
    chunks = chunk_pages([(None, "First grounded point. Second grounded point.")])
    answer, source_ids = AIProvider._demo_answer("Can you summarize this document?", chunks)
    assert answer == "First grounded point. Second grounded point."
    assert source_ids == [chunks[0].id]


def test_demo_answer_prefers_the_sentence_matching_a_rare_query_term():
    text = (
        "Field Notes: Urban Pollinator Gardens. "
        "A small community garden supports native pollinators. "
        "Avoid pesticides because they harm bees."
    )
    chunks = chunk_pages([(None, text)])
    answer, source_ids = AIProvider._demo_answer("What should the garden avoid?", chunks)
    assert answer == "Avoid pesticides because they harm bees."
    assert source_ids == [chunks[0].id]