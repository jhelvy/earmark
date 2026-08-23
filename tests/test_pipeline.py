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


def test_prepare_builds_chunks_and_metadata(article):
    chunks, meta = pipeline.prepare(str(article), options_for("article"))
    assert meta.title == "A Short Article"
    assert chunks[0].text.startswith("A Short Article.")
    assert any("first paragraph" in c.text for c in chunks)


def test_prepare_rejects_an_empty_document(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("```\njust code\n```\n")
    with pytest.raises(RuntimeError, match="no speakable text"):
        pipeline.prepare(str(empty), options_for("article"), title_card=False)


def test_dry_run_estimates_without_synthesizing(article):
    chunks, meta, seconds = pipeline.dry_run(str(article), options_for("article"))
    assert seconds > 0 and len(chunks) >= 3


@needs_ffmpeg
def test_render_end_to_end(article, backend, tmp_path):
    out = tmp_path / "article.mp3"
    result = pipeline.render(
        str(article), out, options_for("article"), backend, use_cache=False
    )
    assert result.path.exists()
    assert result.seconds > 0
    assert result.meta.title == "A Short Article"
    assert result.chunks == len(backend.calls)


@needs_ffmpeg
def test_pauses_lengthen_the_output(article, backend, tmp_path):
    from earmark import chunk as chunk_mod

    quiet = pipeline.render(
        str(article), tmp_path / "a.mp3", options_for("article"), backend, use_cache=False
    )
    original = chunk_mod.PAUSE_PARAGRAPH
    try:
        chunk_mod.PAUSE_PARAGRAPH = original * 4
        louder = pipeline.render(
            str(article), tmp_path / "b.mp3", options_for("article"), backend, use_cache=False
        )
    finally:
        chunk_mod.PAUSE_PARAGRAPH = original
    assert louder.seconds > quiet.seconds


@needs_ffmpeg
def test_cache_avoids_resynthesis(article, backend, tmp_path):
    opts = options_for("article")
    first = pipeline.render(str(article), tmp_path / "1.mp3", opts, backend)
    calls_after_first = len(backend.calls)
    assert calls_after_first == first.chunks

    second = pipeline.render(str(article), tmp_path / "2.mp3", opts, backend)
    assert len(backend.calls) == calls_after_first, "should have been served from cache"
    assert second.seconds == pytest.approx(first.seconds, abs=0.05)


@needs_ffmpeg
def test_refresh_bypasses_the_cache(article, backend, tmp_path):
    opts = options_for("article")
    pipeline.render(str(article), tmp_path / "1.mp3", opts, backend)
    before = len(backend.calls)
    pipeline.render(str(article), tmp_path / "2.mp3", opts, backend, refresh=True)
    assert len(backend.calls) > before


@needs_ffmpeg
def test_a_changed_paragraph_only_resynthesizes_that_chunk(article, backend, tmp_path):
    opts = options_for("article")
    pipeline.render(str(article), tmp_path / "1.mp3", opts, backend)
    before = len(backend.calls)

    article.write_text(article.read_text().replace("And this is the body", "Rewritten body"))
    pipeline.render(str(article), tmp_path / "2.mp3", opts, backend)
    assert len(backend.calls) == before + 1
