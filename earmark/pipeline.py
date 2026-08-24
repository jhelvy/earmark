"""Wiring the stages together: source in, Markdown out, MP3 out.

Three stopping points on one line: extract+clean gives Markdown, chunk+
synthesize gives audio, and the feed comes after. ``text``, ``audio`` and
``publish`` each stop at a different one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from earmark import audio, cache, frontmatter, tag
from earmark.chunk import Chunk, chunk_blocks, estimated_seconds
from earmark.clean import Block, CleanOptions, clean, render, to_blocks
from earmark.extract import extract
from earmark.extract.meta import Metadata
from earmark.source import is_url
from earmark.tts import Backend

MARKDOWN_SUFFIXES = {".md", ".markdown"}


@dataclass
class Document:
    meta: Metadata
    blocks: list[Block]
    reused: bool = False

    @property
    def text(self) -> str:
        return render(self.blocks)


@dataclass
class Result:
    path: Path
    meta: Metadata
    chunks: int
    seconds: float
    excerpt: str = ""


def load(
    source: str,
    opts: CleanOptions,
    *,
    title: str | None = None,
    author: str | None = None,
    date: str | None = None,
) -> Document:
    """Extract and clean a source -- unless it is already-cleaned Markdown.

    A file earmark itself wrote carries ``earmark: cleaned`` in its front
    matter, and is passed through verbatim. That is the whole point of the
    Markdown step: you edit the file, fix a mangled equation or cut a section,
    and ``audio`` must not undo the edit with the same rules that caused it.
    """
    reused = _reusable_markdown(source)
    if reused is not None:
        meta = Metadata(
            title=title or reused.fields.get("title") or Path(source).stem,
            author=author or reused.fields.get("author") or None,
            date=date or reused.fields.get("date") or None,
            source=reused.fields.get("source") or str(source),
        )
        return Document(meta=meta, blocks=to_blocks(reused.body), reused=True)

    doc = extract(source, title=title, author=author, date=date)
    # A local source is recorded absolute. It is written into the Markdown's
    # front matter, and a relative path there points at wherever you happened to
    # be standing when you ran the command.
    if not is_url(source):
        doc.meta.source = str(Path(source).expanduser().resolve())
    return Document(meta=doc.meta, blocks=clean(doc.markdown, opts))


def _reusable_markdown(source: str) -> frontmatter.Parsed | None:
    if is_url(source):
        return None
    path = Path(source).expanduser()
    if path.suffix.lower() not in MARKDOWN_SUFFIXES or not path.is_file():
        return None
    parsed = frontmatter.parse(path.read_text(encoding="utf-8", errors="replace"))
    return parsed if parsed.is_cleaned else None


def write_markdown(doc: Document, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(frontmatter.dump(doc.meta, doc.text), encoding="utf-8")
    return out_path


def to_chunks(doc: Document, *, source: str = "", title_card: bool = True) -> list[Chunk]:
    chunks = chunk_blocks(
        doc.blocks,
        title=doc.meta.title if title_card else None,
        author=doc.meta.author if title_card else None,
        date=doc.meta.date if title_card else None,
    )
    if not chunks:
        raise RuntimeError(f"no speakable text found in {source or doc.meta.title}")
    return chunks


def synthesize(
    chunks: list[Chunk],
    backend: Backend,
    voice: str,
    speed: float,
    lang: str,
    on_chunk: Callable[[int, float, bool], None] | None = None,
    use_cache: bool = True,
    refresh: bool = False,
) -> Iterator[np.ndarray]:
    """Yield audio for each chunk in order, with its pauses attached."""
    rate = backend.sample_rate
    fingerprint = backend.fingerprint()
    for i, chunk in enumerate(chunks):
        if chunk.pause_before:
            yield audio.silence(chunk.pause_before, rate)

        samples = None
        key = None
        if use_cache:
            key = cache.key(chunk.text, fingerprint, voice, speed, lang)
            if not refresh:
                samples = cache.get(key)
        cached = samples is not None
        if samples is None:
            samples = backend.synth(chunk.text, voice=voice, speed=speed, lang=lang)
            if key is not None:
                cache.put(key, samples)

        yield samples
        if chunk.pause_after:
            yield audio.silence(chunk.pause_after, rate)
        if on_chunk:
            on_chunk(i, len(samples) / rate, cached)


def render_audio(
    doc: Document,
    out_path: Path,
    backend: Backend,
    *,
    source: str = "",
    voice: str = "af_heart",
    speed: float = 1.0,
    lang: str = "en-us",
    bitrate: str = audio.DEFAULT_BITRATE,
    sample_rate: int = audio.DEFAULT_SAMPLE_RATE,
    title_card: bool = True,
    on_start: Callable[[list[Chunk], Metadata], None] | None = None,
    on_chunk: Callable[[int, float, bool], None] | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    album: str | None = None,
    cover: Path | None = None,
) -> Result:
    chunks = to_chunks(doc, source=source, title_card=title_card)
    if on_start:
        on_start(chunks, doc.meta)
    stream = synthesize(
        chunks, backend, voice, speed, lang, on_chunk,
        use_cache=use_cache, refresh=refresh,
    )
    written = audio.encode(
        stream, out_path, bitrate=bitrate, sample_rate=sample_rate,
        input_rate=backend.sample_rate,
    )
    seconds = audio.duration_seconds(written, backend.sample_rate)
    tag.write(Path(out_path), doc.meta, duration_seconds=seconds, album=album, cover=cover)
    return Result(
        path=Path(out_path),
        meta=doc.meta,
        chunks=len(chunks),
        seconds=seconds,
        excerpt=excerpt(chunks),
    )


def estimate(doc: Document, *, source: str = "", title_card: bool = True):
    chunks = to_chunks(doc, source=source, title_card=title_card)
    return chunks, estimated_seconds(chunks)


EXCERPT_CHARS = 300


def excerpt(chunks: list[Chunk], limit: int = EXCERPT_CHARS) -> str:
    """A short plain-text summary for the feed, skipping the spoken title card."""
    body = " ".join(c.text for c in chunks[1:]) if len(chunks) > 1 else ""
    body = " ".join(body.split())
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut + "…"
