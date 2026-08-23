"""Metadata resolution.

The precedence rule lives here and only here: an explicit flag beats extracted
metadata, which beats the first H1, which beats the filename, which beats
"Untitled".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path


@dataclass
class Metadata:
    title: str = "Untitled"
    author: str | None = None
    date: str | None = None
    source: str = ""
    site: str | None = None


@dataclass
class Document:
    markdown: str
    meta: Metadata


_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


def first_heading(markdown: str) -> str | None:
    m = _H1.search(markdown)
    return m.group(1).strip() if m else None


# Extractors sometimes hand back a page's whole "authority control" rail or a
# newsroom boilerplate block as the author. A byline is short.
MAX_AUTHOR_WORDS = 8
MAX_AUTHOR_CHARS = 80


def _clean_author(value: str | None) -> str | None:
    value = _clean_title(value)
    if not value:
        return None
    if len(value) > MAX_AUTHOR_CHARS or len(value.split()) > MAX_AUTHOR_WORDS:
        return None
    return value


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value).strip()
    return value or None


def _clean_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        return m.group(0) if m else None
    try:
        return value.date().isoformat()
    except AttributeError:
        try:
            return _date.fromtimestamp(float(value)).isoformat()
        except (TypeError, ValueError):
            return None


def resolve_meta(
    markdown: str,
    source: str,
    *,
    extracted: Metadata | None = None,
    title: str | None = None,
    author: str | None = None,
    date: str | None = None,
) -> Metadata:
    extracted = extracted or Metadata()
    filename_title = None
    if not source.startswith(("http://", "https://")):
        filename_title = Path(source).stem.replace("_", " ").replace("-", " ").strip()

    resolved_title = (
        _clean_title(title)
        or _clean_title(extracted.title if extracted.title != "Untitled" else None)
        or _clean_title(first_heading(markdown))
        or _clean_title(filename_title)
        or "Untitled"
    )
    return Metadata(
        title=resolved_title,
        author=_clean_author(author) or _clean_author(extracted.author),
        date=_clean_date(date) or _clean_date(extracted.date),
        source=source,
        site=extracted.site,
    )
