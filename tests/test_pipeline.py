import pytest

from conftest import needs_ffmpeg

from earmark import pipeline
from earmark.clean import options_for


@pytest.fixture
def article(tmp_path):
    path = tmp_path / "an-article.md"
    path.write_text(
        "# A Short Article\n\n"
        "This is the first paragraph. It has two sentences.\n\n"
        "## A Section\n\n"
        "And this is the body of that section.\n"
    )
    return path


def load(path):
    return pipeline.load(str(path), options_for("article"))


def test_load_builds_blocks_and_metadata(article):
    doc = load(article)
    assert doc.meta.title == "A Short Article"
    assert doc.reused is False
    assert "first paragraph" in doc.text


def test_chunks_open_with_the_title_card(article):
    chunks = pipeline.to_chunks(load(article))
    assert chunks[0].text.startswith("A Short Article.")


def test_an_empty_document_is_rejected(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("```\njust code\n```\n")
    with pytest.raises(RuntimeError, match="no speakable text"):
        pipeline.to_chunks(load(empty), source=str(empty), title_card=False)


def test_estimate_costs_no_synthesis(article):
    chunks, seconds = pipeline.estimate(load(article))
    assert seconds > 0 and len(chunks) >= 3


# -- the Markdown round trip ---------------------------------------------


def test_written_markdown_carries_its_metadata(article, tmp_path):
    out = pipeline.write_markdown(load(article), tmp_path / "text" / "a.md")
    text = out.read_text()
    assert text.startswith("---\n")
    assert "title: A Short Article" in text
    assert "earmark: cleaned" in text


def test_written_markdown_is_reused_verbatim(article, tmp_path):
    """The whole point of the Markdown step: your edits survive convert."""
    out = pipeline.write_markdown(load(article), tmp_path / "a.md")
    out.write_text(out.read_text().replace("Rewritten", "x").replace(
        "And this is the body of that section.", "A sentence I typed myself."))
    doc = pipeline.load(str(out), options_for("article"))
    assert doc.reused is True
    assert "A sentence I typed myself." in doc.text
    assert doc.meta.title == "A Short Article"


def test_markdown_without_front_matter_is_still_cleaned(article):
    assert pipeline.load(str(article), options_for("article")).reused is False


def test_an_explicit_title_beats_the_front_matter(article, tmp_path):
    out = pipeline.write_markdown(load(article), tmp_path / "a.md")
    doc = pipeline.load(str(out), options_for("article"), title="My Own Title")
    assert doc.meta.title == "My Own Title"


@needs_ffmpeg
def test_render_end_to_end(article, backend, tmp_path):
    out = tmp_path / "article.mp3"
    result = pipeline.render_audio(load(article), out, backend, use_cache=False)
    assert result.path.exists()
    assert result.seconds > 0
    assert result.meta.title == "A Short Article"
    assert result.chunks == len(backend.calls)


@needs_ffmpeg
def test_pauses_lengthen_the_output(article, backend, tmp_path):
    from earmark import chunk as chunk_mod

    quiet = pipeline.render_audio(load(article), tmp_path / "a.mp3", backend, use_cache=False)
    original = chunk_mod.PAUSE_PARAGRAPH
    try:
        chunk_mod.PAUSE_PARAGRAPH = original * 4
        louder = pipeline.render_audio(load(article), tmp_path / "b.mp3", backend, use_cache=False)
    finally:
        chunk_mod.PAUSE_PARAGRAPH = original
    assert louder.seconds > quiet.seconds


@needs_ffmpeg
def test_cache_avoids_resynthesis(article, backend, tmp_path):
    opts = options_for("article")
    first = pipeline.render_audio(load(article), tmp_path / "1.mp3", backend)
    calls_after_first = len(backend.calls)
    assert calls_after_first == first.chunks

    second = pipeline.render_audio(load(article), tmp_path / "2.mp3", backend)
    assert len(backend.calls) == calls_after_first, "should have been served from cache"
    assert second.seconds == pytest.approx(first.seconds, abs=0.05)


@needs_ffmpeg
def test_refresh_bypasses_the_cache(article, backend, tmp_path):
    opts = options_for("article")
    pipeline.render_audio(load(article), tmp_path / "1.mp3", backend)
    before = len(backend.calls)
    pipeline.render_audio(load(article), tmp_path / "2.mp3", backend, refresh=True)
    assert len(backend.calls) > before


@needs_ffmpeg
def test_a_changed_paragraph_only_resynthesizes_that_chunk(article, backend, tmp_path):
    opts = options_for("article")
    pipeline.render_audio(load(article), tmp_path / "1.mp3", backend)
    before = len(backend.calls)

    article.write_text(article.read_text().replace("And this is the body", "Rewritten body"))
    pipeline.render_audio(load(article), tmp_path / "2.mp3", backend)
    assert len(backend.calls) == before + 1


def test_a_local_source_is_recorded_absolute(article, tmp_path, monkeypatch):
    """The path goes into front matter, where a relative one means nothing."""
    monkeypatch.chdir(tmp_path)
    doc = pipeline.load("an-article.md", options_for("article"))
    assert doc.meta.source == str(article.resolve())
