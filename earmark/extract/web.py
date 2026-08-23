"""Article URLs, via trafilatura.

trafilatura exists specifically to strip nav, ads and related-article rails.
markitdown's HTML path is a thin markdownify wrapper that does not attempt it,
so using markitdown here would mean listening to cookie banners.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from earmark.extract.meta import Document, Metadata, resolve_meta

MIN_USEFUL_CHARS = 500


_ARXIV_ID = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})",
    re.I,
)
ARXIV_API = "http://export.arxiv.org/api/query?id_list={}"
_ATOM = "{http://www.w3.org/2005/Atom}"


def arxiv_metadata(url: str) -> Metadata | None:
    """Ask arXiv for a paper's real title and authors.

    A PDF's own metadata is usually empty and its title is only recoverable
    from font sizes we do not have, so for the one source most likely to be
    pasted here it is worth asking the authoritative API instead of guessing.
    """
    m = _ARXIV_ID.search(url)
    if not m:
        return None
    import urllib.request
    import xml.etree.ElementTree as ET

    try:
        with urllib.request.urlopen(  # noqa: S310
            ARXIV_API.format(m.group("id")), timeout=15
        ) as resp:
            root = ET.fromstring(resp.read())
    except Exception:
        return None

    entry = root.find(f"{_ATOM}entry")
    if entry is None:
        return None
    title = (entry.findtext(f"{_ATOM}title") or "").strip()
    if not title:
        return None
    authors = [
        (a.findtext(f"{_ATOM}name") or "").strip()
        for a in entry.findall(f"{_ATOM}author")
    ]
    authors = [a for a in authors if a]
    if len(authors) > 3:
        author = f"{authors[0]} and others"
    else:
        author = ", ".join(authors) or None
    published = (entry.findtext(f"{_ATOM}published") or "")[:10] or None
    return Metadata(
        title=" ".join(title.split()),
        author=author,
        date=published,
        site="arXiv",
    )


def _looks_like_pdf(url: str) -> bool:
    path = unquote(urlparse(url).path).lower()
    return path.endswith(".pdf") or "/pdf/" in path


def _fetch_pdf(url: str) -> Path:
    import urllib.request

    # The suffix matters: extract_file dispatches on it, and an arXiv PDF URL
    # ends in a bare id ("/pdf/1706.03762") with no extension at all.
    name = Path(urlparse(url).path).name or "download"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    tmp = Path(tempfile.mkdtemp()) / name
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as fh:  # noqa: S310
        fh.write(resp.read())
    return tmp


def _is_pdf_response(html_or_bytes) -> bool:
    if isinstance(html_or_bytes, bytes):
        return html_or_bytes[:5] == b"%PDF-"
    return isinstance(html_or_bytes, str) and html_or_bytes.startswith("%PDF-")


def arxiv_pdf_url(source: str) -> str | None:
    """The PDF behind an arxiv.org/abs/... landing page.

    /abs/ is the link arXiv shows and therefore the one people copy, but it is
    a listing page: extracting it yields "View PDF", "HTML (experimental)" and
    the arXivLabs footer instead of the paper.
    """
    m = _ARXIV_ID.search(source)
    if not m or "/abs/" not in source.lower():
        return None
    return f"https://arxiv.org/pdf/{m.group('id')}"


def extract_url(source: str, **overrides) -> Document:
    # arXiv links are the URL most likely to be pasted, so the PDF detour is
    # not optional.
    if _looks_like_pdf(source):
        return _from_pdf_url(source, **overrides)

    pdf = arxiv_pdf_url(source)
    if pdf is not None:
        doc = _from_pdf_url(pdf, **overrides)
        doc.meta.source = source
        return doc

    import trafilatura

    html = trafilatura.fetch_url(source)
    if html is None:
        raise RuntimeError(f"could not fetch {source}")
    if _is_pdf_response(html):
        return _from_pdf_url(source, **overrides)

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

    upstream = arxiv_metadata(source)
    if upstream is not None:
        extracted = upstream
    meta = resolve_meta(markdown, source, extracted=extracted, **overrides)
    return Document(markdown=markdown, meta=meta)


def _from_pdf_url(source: str, **overrides):
    from earmark.extract.files import extract_file
    from earmark.extract.meta import resolve_meta

    doc = extract_file(str(_fetch_pdf(source)), **overrides)
    upstream = arxiv_metadata(source)
    if upstream is not None:
        doc.meta = resolve_meta(doc.markdown, source, extracted=upstream, **overrides)
    doc.meta.source = source
    return doc


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
