"""Local files, via markitdown.

markitdown is a declared dependency rather than a shell-out to whatever
``markitdown`` happens to be on PATH: as a dependency its extras are pinned by
our own pyproject, so a PDF cannot fail because someone's global install was
made without ``[pdf]``. The CLI shell-out survives only as a fallback.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from earmark.extract.meta import Document, Metadata, resolve_meta


def _via_pypdf(path: Path) -> str:
    """Extract a PDF with pypdf rather than markitdown.

    markitdown routes PDFs through pdfminer with default layout parameters,
    which on many LaTeX-produced PDFs (arXiv preprints especially) drops the
    spaces between words entirely -- "Thedominantsequencetransduction". pypdf
    gets the spacing right on the same files, is already a dependency for
    metadata, and is MIT-licensed.
    """
    from pypdf import PdfReader

    pages = [page.extract_text() or "" for page in PdfReader(str(path)).pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _via_library(path: Path) -> str:
    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(str(path))
    return getattr(result, "markdown", None) or result.text_content


def _via_cli(path: Path) -> str:
    exe = shutil.which("markitdown")
    if not exe:
        raise RuntimeError(
            "markitdown is unavailable both as a library and on PATH; "
            "reinstall earmark or run: uv tool install 'markitdown[pdf]'"
        )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.md"
        subprocess.run([exe, str(path), "-o", str(out)], check=True, capture_output=True)
        return out.read_text(encoding="utf-8")


def _pdf_metadata(path: Path) -> Metadata:
    try:
        from pypdf import PdfReader

        info = PdfReader(str(path)).metadata or {}
        return Metadata(
            title=(info.get("/Title") or "Untitled").strip() or "Untitled",
            author=(info.get("/Author") or None),
            date=getattr(info, "creation_date", None),
        )
    except Exception:
        return Metadata()


def extract_file(source: str, **overrides) -> Document:
    path = Path(source).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"no such file: {path}")

    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        markdown = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        markdown = _via_pypdf(path)
        if not markdown.strip():
            markdown = _via_library(path)
    else:
        try:
            markdown = _via_library(path)
        except ImportError:
            markdown = _via_cli(path)

    extracted = _pdf_metadata(path) if suffix == ".pdf" else Metadata()
    if extracted.date is None:
        extracted.date = None
    meta = resolve_meta(markdown, str(path), extracted=extracted, **overrides)
    if meta.date is None:
        from datetime import datetime

        meta.date = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    return Document(markdown=markdown, meta=meta)
