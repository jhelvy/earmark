"""Splitting cleaned blocks into synthesis-sized chunks.

Chunking is for cache granularity and progress reporting, not correctness:
``Kokoro.create()`` already re-splits phonemes internally at its own limit. The
size target comes from Kokoro's VOICES.md, which notes quality degrading above
roughly 400 tokens and below 10-20.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from earmark.clean import Block

TARGET_CHARS = 600
MAX_CHARS = 900

# Pause lengths in seconds. Long enough to hear as structure, short enough that
# a listener does not think the file has stopped.
PAUSE_TITLE = 1.0
PAUSE_BEFORE_HEADING = 0.7
PAUSE_AFTER_HEADING = 0.4
PAUSE_PARAGRAPH = 0.25
PAUSE_ITEM = 0.2

# Abbreviation expansion in clean.py has already removed the trailing-period
# traps, so a boundary rule is enough and no sentence tokenizer is needed.
_SENTENCE_END = re.compile(r'(?<=[.!?])["\'”’)]?\s+(?=[A-Z0-9"\'“‘(])')


@dataclass(frozen=True)
class Chunk:
    text: str
    pause_after: float = 0.0
    pause_before: float = 0.0


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def pack(sentences: list[str], target: int = TARGET_CHARS, cap: int = MAX_CHARS) -> list[str]:
    """Greedily group sentences, never splitting one."""
    out: list[str] = []
    current = ""
    for sentence in sentences:
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= target or len(current) < target // 3:
            candidate = f"{current} {sentence}"
            if len(candidate) > cap and current:
                out.append(current)
                current = sentence
            else:
                current = candidate
        else:
            out.append(current)
            current = sentence
    if current:
        out.append(current)
    return out


def title_card(title: str, author: str | None = None, date: str | None = None) -> str:
    parts = [title.rstrip(".") + "."]
    if author:
        parts.append(f"By {author.rstrip('.')}.")
    if date:
        parts.append(f"{date}.")
    return " ".join(parts)


def chunk_blocks(
    blocks: list[Block],
    title: str | None = None,
    author: str | None = None,
    date: str | None = None,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    if title:
        chunks.append(Chunk(title_card(title, author, date), pause_after=PAUSE_TITLE))

    for block in blocks:
        if block.kind == "heading":
            # A heading is short, but the pause after it masks any artifact.
            chunks.append(
                Chunk(
                    block.text,
                    pause_after=PAUSE_AFTER_HEADING,
                    pause_before=PAUSE_BEFORE_HEADING,
                )
            )
            continue
        pause = PAUSE_ITEM if block.kind == "item" else PAUSE_PARAGRAPH
        pieces = pack(split_sentences(block.text))
        for i, piece in enumerate(pieces):
            chunks.append(Chunk(piece, pause_after=pause if i == len(pieces) - 1 else 0.0))
    return chunks


def estimated_seconds(chunks: list[Chunk], chars_per_second: float = 14.5) -> float:
    """Rough spoken duration, for ``--dry-run``."""
    speech = sum(len(c.text) for c in chunks) / chars_per_second
    pauses = sum(c.pause_before + c.pause_after for c in chunks)
    return speech + pauses
