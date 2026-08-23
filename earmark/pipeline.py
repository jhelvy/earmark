"""Wiring the stages together: source in, MP3 out."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from earmark import audio, cache, tag
from earmark.chunk import Chunk, chunk_blocks, estimated_seconds
from earmark.clean import CleanOptions, clean
from earmark.extract import extract
from earmark.extract.meta import Metadata
from earmark.tts import Backend


@dataclass
class Result:
    path: Path
    meta: Metadata
    chunks: int
    seconds: float
    excerpt: str = ""


def prepare(
    source: str,
    opts: CleanOptions,
    *,
    title: str | None = None,
    author: str | None = None,
    date: str | None = None,
    title_card: bool = True,
) -> tuple[list[Chunk], Metadata]:
    doc = extract(source, title=title, author=author, date=date)
    blocks = clean(doc.markdown, opts)
    chunks = chunk_blocks(
        blocks,
        title=doc.meta.title if title_card else None,
        author=doc.meta.author if title_card else None,
        date=doc.meta.date if title_card else None,
    )
    if not chunks:
        raise RuntimeError(f"no speakable text found in {source}")
    return chunks, doc.meta


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


def render(
    source: str,
    out_path: Path,
    opts: CleanOptions,
    backend: Backend,
    *,
    voice: str = "af_heart",
    speed: float = 1.0,
    lang: str = "en-us",
    bitrate: str = audio.DEFAULT_BITRATE,
    sample_rate: int = audio.DEFAULT_SAMPLE_RATE,
    title: str | None = None,
    author: str | None = None,
    date: str | None = None,
    on_start: Callable[[list[Chunk], Metadata], None] | None = None,
    on_chunk: Callable[[int, float, bool], None] | None = None,
    use_cache: bool = True,
    refresh: bool = False,
    album: str | None = None,
    cover: Path | None = None,
) -> Result:
    chunks, meta = prepare(source, opts, title=title, author=author, date=date)
    if on_start:
        on_start(chunks, meta)
    stream = synthesize(
        chunks, backend, voice, speed, lang, on_chunk,
        use_cache=use_cache, refresh=refresh,
    )
    written = audio.encode(
        stream, out_path, bitrate=bitrate, sample_rate=sample_rate,
        input_rate=backend.sample_rate,
    )
    seconds = audio.duration_seconds(written, backend.sample_rate)
    tag.write(Path(out_path), meta, duration_seconds=seconds, album=album, cover=cover)
    return Result(
        path=Path(out_path),
        meta=meta,
        chunks=len(chunks),
        seconds=seconds,
        excerpt=excerpt(chunks),
    )


def dry_run(source: str, opts: CleanOptions, **kw) -> tuple[list[Chunk], Metadata, float]:
    chunks, meta = prepare(source, opts, **kw)
    return chunks, meta, estimated_seconds(chunks)


EXCERPT_CHARS = 300


def excerpt(chunks: list[Chunk], limit: int = EXCERPT_CHARS) -> str:
    """A short plain-text summary for the feed, skipping the spoken title card."""
    body = " ".join(c.text for c in chunks[1:]) if len(chunks) > 1 else ""
    body = " ".join(body.split())
    if len(body) <= limit:
        return body
    cut = body[:limit].rsplit(" ", 1)[0]
    return cut + "\u2026"
