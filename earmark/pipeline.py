"""Wiring the stages together: source in, MP3 out."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import numpy as np

from earmark import audio
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
    on_chunk: Callable[[int, float], None] | None = None,
) -> Iterator[np.ndarray]:
    """Yield audio for each chunk in order, with its pauses attached."""
    rate = backend.sample_rate
    for i, chunk in enumerate(chunks):
        if chunk.pause_before:
            yield audio.silence(chunk.pause_before, rate)
        samples = backend.synth(chunk.text, voice=voice, speed=speed, lang=lang)
        yield samples
        if chunk.pause_after:
            yield audio.silence(chunk.pause_after, rate)
        if on_chunk:
            on_chunk(i, len(samples) / rate)


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
    on_chunk: Callable[[int, float], None] | None = None,
) -> Result:
    chunks, meta = prepare(source, opts, title=title, author=author, date=date)
    if on_start:
        on_start(chunks, meta)
    stream = synthesize(chunks, backend, voice, speed, lang, on_chunk)
    written = audio.encode(
        stream, out_path, bitrate=bitrate, sample_rate=sample_rate,
        input_rate=backend.sample_rate,
    )
    return Result(
        path=Path(out_path),
        meta=meta,
        chunks=len(chunks),
        seconds=audio.duration_seconds(written, backend.sample_rate),
    )


def dry_run(source: str, opts: CleanOptions, **kw) -> tuple[list[Chunk], Metadata, float]:
    chunks, meta = prepare(source, opts, **kw)
    return chunks, meta, estimated_seconds(chunks)
