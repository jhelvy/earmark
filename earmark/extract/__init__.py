"""Source extraction: anything you can point at, turned into Markdown."""

from __future__ import annotations

from earmark.extract.meta import Document, Metadata, resolve_meta

__all__ = ["Document", "Metadata", "resolve_meta", "extract"]


def extract(source: str, **overrides) -> Document:
    """Dispatch a path or a URL to the right extractor."""
    from earmark.source import is_url

    if is_url(source):
        from earmark.extract.web import extract_url

        return extract_url(source, **overrides)
    from earmark.extract.files import extract_file

    return extract_file(source, **overrides)
