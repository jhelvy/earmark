import pytest

from earmark.chunk import (
    MAX_CHARS, Chunk, chunk_blocks, estimated_seconds, pack, split_sentences, title_card,
)
from earmark.clean import Block


@pytest.mark.parametrize(
    "text,count",
    [
        ("One. Two. Three.", 3),
        ("A single sentence with no breaks", 1),
        ("Question? Yes! Done.", 3),
        # clean.py has already expanded these, so no false break remains.
        ("Tools exist, for example pandas. Then more.", 2),
    ],
)
def test_sentence_splitting(text, count):
    assert len(split_sentences(text)) == count


def test_decimal_does_not_split():
    assert len(split_sentences("The value 3.14 is fixed. Next.")) == 2


def test_pack_never_splits_a_sentence():
    sentences = [f"Sentence number {i} with some length to it." for i in range(40)]
    packed = pack(sentences)
    assert all(len(p) <= MAX_CHARS for p in packed)
    assert " ".join(packed) == " ".join(sentences)


def test_pack_groups_short_sentences():
    assert len(pack(["A.", "B.", "C."])) == 1


def test_title_card():
    assert title_card("A Paper", "Jane Doe", "2026-01-01") == "A Paper. By Jane Doe. 2026-01-01."
    assert title_card("A Paper") == "A Paper."


def test_headings_get_pauses_on_both_sides():
    chunks = chunk_blocks([Block("heading", "Methods.", 2)])
    assert chunks[0].pause_before > 0 and chunks[0].pause_after > 0


def test_only_the_last_chunk_of_a_paragraph_pauses():
    long_para = " ".join(f"Sentence {i} here with words." for i in range(40))
    chunks = chunk_blocks([Block("para", long_para)])
    assert len(chunks) > 1
    assert all(c.pause_after == 0 for c in chunks[:-1])
    assert chunks[-1].pause_after > 0


def test_title_card_is_first_and_optional():
    blocks = [Block("para", "Body.")]
    assert chunk_blocks(blocks, title="T", author="A")[0].text == "T. By A."
    assert chunk_blocks(blocks)[0].text == "Body."


def test_estimated_seconds_counts_pauses():
    chunks = [Chunk("a" * 145, pause_after=2.0)]
    assert estimated_seconds(chunks) == pytest.approx(12.0, abs=0.5)
