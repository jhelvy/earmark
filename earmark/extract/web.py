"""Article URLs, via trafilatura.

trafilatura exists specifically to strip nav, ads and related-article rails.
markitdown's HTML path is a thin markdownify wrapper that does not attempt it,
so using markitdown here would mean listening to cookie banners.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from earmark.extract.meta import Document, Metadata, resolve_meta

MIN_USEFUL_CHARS = 500


def _looks_like_pdf(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    return path.endswith(".pdf") or "/pdf/" in path


def _fetch_pdf(url: str) -> Path:
    import urllib.request

    tmp = Path(tempfile.mkdtemp()) / (Path(urlparse(url).path).name or "download.pdf")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as fh:  # noqa: S310
        fh.write(resp.read())
    return tmp


def _is_pdf_response(html_or_bytes) -> bool:
    if isinstance(html_or_bytes, bytes):
        return html_or_bytes[:5] == b"%PDF-"
    return isinstance(html_or_bytes, str) and html_or_bytes.startswith("%PDF-")


def extract_url(source: str, **overrides) -> Document:
    # arXiv links are the URL most likely to be pasted, so the PDF detour is
    # not optional.
    if _looks_like_pdf(source):
        from earmark.extract.files import extract_file

        doc = extract_file(str(_fetch_pdf(source)), **overrides)
        doc.meta.source = source
        return doc

    import trafilatura

    html = trafilatura.fetch_url(source)
    if html is None:
        raise RuntimeError(f"could not fetch {source}")
    if _is_pdf_response(html):
        from earmark.extract.files import extract_file

        doc = extract_file(str(_fetch_pdf(source)), **overrides)
        doc.meta.source = source
        return doc

    doc = _extract(html, source, favor_precision=True)
    if doc is None or len(doc.text or "") < MIN_USEFUL_CHARS:
        recalled = _extract(html, source, favor_recall=True)
        if recalled is not None and len(recalled.text or "") > len(
            (doc.text if doc else "") or ""
        ):
            doc = recalled

    if doc is None or not (doc.text or "").strip():
        markdown, extracted = _via_markitdown(source)
    else:
        markdown = doc.text
        extracted = Metadata(
            title=(doc.title or "Untitled"),
            author=getattr(doc, "author", None),
            date=getattr(doc, "date", None),
            site=getattr(doc, "sitename", None),
        )

    meta = resolve_meta(markdown, source, extracted=extracted, **overrides)
    return Document(markdown=markdown, meta=meta)


def _extract(html: str, url: str, **flags):
    import trafilatura

    try:
        return trafilatura.extract_with_metadata(
            html,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_links=True,
            **flags,
        )
    except Exception:
        return None


def _via_markitdown(url: str) -> tuple[str, Metadata]:
    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert_url(url)
    markdown = getattr(result, "markdown", None) or result.text_content
    return markdown, Metadata(title=getattr(result, "title", None) or "Untitled")
