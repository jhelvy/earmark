"""Deciding what a source string actually is."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def is_url(source: str) -> bool:
    if not _SCHEME.match(source):
        return False
    return urlparse(source).scheme in {"http", "https"}


def slugify(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return (slug[:max_len].rstrip("-") or "untitled")


def default_output(title: str, source: str, output_dir: str | None = None) -> Path:
    stem = slugify(title) if title else Path(source).stem
    base = Path(output_dir).expanduser() if output_dir else Path.cwd()
    return base / f"{stem}.mp3"
