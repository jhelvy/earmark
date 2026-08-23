"""Removing page furniture from PDF text.

A PDF does not know what a paragraph is. pypdf emits each page in content-stream
order, which for a LaTeX paper means body text, then footnotes, then the page
number -- and flattening that into one string turns all three into prose. A
paper's abstract runs straight on into "Equal contribution. Listing order is
random", and the body of section 3.2 is interrupted by the footnote hanging off
its last line.

Nothing here guesses at meaning. Every rule is positional: footnotes and page
numbers live at the bottom of a page and nowhere else, so each rule looks only
at the tail of a page, and running heads are found by being the same line on
several pages at once. That is also the safety argument -- a rule that can only
fire in the last 45% of a page cannot eat an argument in the middle of one.

Called from ``extract.files._via_pypdf`` while page boundaries still exist; by
the time ``clean`` sees the text they are just blank lines.
"""

from __future__ import annotations

import re
from collections import Counter

# Footnote markers as LaTeX actually emits them. Requiring no space after the
# marker is what separates a footnote ("*Equal contribution") from a bullet
# ("* item"), and requiring a letter after the digit separates a numbered
# footnote ("4To illustrate") from a section heading ("4 Why Self-Attention").
_SYMBOL_NOTE = re.compile(r"^[*∗†‡§¶]{1,3}(?=\S)")
_NUMBERED_NOTE = re.compile(r"^(\d{1,3})(?=[A-Za-z])")

_ROMAN = r"m{0,3}(?:cm|cd|d?c{0,3})(?:xc|xl|l?x{0,3})(?:ix|iv|v?i{0,3})"
_PAGE_NUMBER = re.compile(
    rf"^[\[(\-–—\s]*(?:\d{{1,4}}|{_ROMAN})[\])\-–—\s]*$",
    re.IGNORECASE,
)

# Publication stamps: never part of the text, always pinned to a page edge.
_STAMP = re.compile(
    r"^\s*(?:arXiv:\d{4}\.\d{4,5}"
    r"|\d+(?:st|nd|rd|th)\s+(?:annual\s+)?(?:conference|workshop|symposium|meeting)\b"
    r"|(?:proceedings\s+of|preprint|to\s+appear\s+in|submitted\s+to|under\s+review)\b"
    r"|(?:copyright|©)\s+\d{4}"
    r"|permission\s+to\s+make\s+digital)",
    re.IGNORECASE,
)

# Words that legitimately precede a bare number, so "see Table 4." survives the
# inline-superscript cleanup that turns "gradients 4." into "gradients."
_REF_WORDS = frozenset(
    """table tables figure figures fig figs section sections sec eq eqs equation
    equations chapter part page pages ref refs reference references appendix
    algorithm theorem lemma corollary definition example note step line item
    number no version level layer type class group phase round trial run"""
    .split()
)

# A footnote may only start in the last 45% of a page, and may not swallow more
# than this many lines. Both bounds exist to make a false positive survivable.
TAIL_FRACTION = 0.55
MAX_NOTE_LINES = 30

# A line must repeat on at least this many pages to count as a running head.
MIN_HEADER_PAGES = 3
MAX_HEADER_CHARS = 90

_INLINE_REF = re.compile(r"(\w+) (\d{1,3})(?=[.,;:)])")


def is_page_number(line: str) -> bool:
    stripped = line.strip()
    if not stripped or not any(c.isalnum() for c in stripped):
        return False
    return bool(_PAGE_NUMBER.match(stripped))


def is_stamp(line: str) -> bool:
    return bool(_STAMP.match(line))


def running_heads(pages: list[str]) -> set[str]:
    """Lines that sit at the top or bottom edge of many pages.

    A journal PDF repeats the article title or the author list on every page.
    Counting only the outermost two lines of each page keeps a genuinely
    repeated sentence in the body from being mistaken for one.
    """
    if len(pages) < MIN_HEADER_PAGES:
        return set()
    counts: Counter[str] = Counter()
    for page in pages:
        lines = [ln.strip() for ln in page.split("\n") if ln.strip()]
        if not lines:
            continue
        edges = {ln for ln in lines[:2] + lines[-2:] if len(ln) <= MAX_HEADER_CHARS}
        counts.update(ln for ln in edges if not is_page_number(ln))
    return {line for line, n in counts.items() if n >= MIN_HEADER_PAGES}


def _drop_edges(lines: list[str], heads: set[str]) -> list[str]:
    """Remove running heads and page numbers, but only from the page edges."""
    while lines and (
        not lines[0].strip() or lines[0].strip() in heads or is_page_number(lines[0])
    ):
        lines = lines[1:]
    while lines and (
        not lines[-1].strip()
        or lines[-1].strip() in heads
        or is_page_number(lines[-1])
        or is_stamp(lines[-1])
    ):
        lines = lines[:-1]
    return lines


def _note_start(lines: list[str]) -> int | None:
    """Index of the first footnote line in the page's tail, if there is one."""
    if not lines:
        return None
    window = max(1, int(len(lines) * TAIL_FRACTION))
    for i in range(window, len(lines)):
        line = lines[i].strip()
        if _SYMBOL_NOTE.match(line) or _NUMBERED_NOTE.match(line):
            return i if len(lines) - i <= MAX_NOTE_LINES else None
    return None


def _strip_inline_refs(text: str, numbers: set[str]) -> str:
    """Delete superscript footnote references pypdf renders as " 4".

    Only numbers whose footnote was actually found and removed from this page
    are eligible, which is what keeps the rule from eating real ones.
    """
    if not numbers:
        return text

    def repl(m: re.Match[str]) -> str:
        word, num = m.group(1), m.group(2)
        if num in numbers and word.isalpha() and word.lower() not in _REF_WORDS:
            return word
        return m.group(0)

    return _INLINE_REF.sub(repl, text)


def strip_furniture(pages: list[str]) -> list[str]:
    """Strip footnotes, page numbers, running heads and stamps from PDF pages."""
    heads = running_heads(pages)
    out: list[str] = []
    for page in pages:
        lines = _drop_edges(page.split("\n"), heads)
        numbers: set[str] = set()
        start = _note_start(lines)
        if start is not None:
            for line in lines[start:]:
                m = _NUMBERED_NOTE.match(line.strip())
                if m:
                    numbers.add(m.group(1))
            lines = _drop_edges(lines[:start], heads)
        out.append(_strip_inline_refs("\n".join(lines).strip(), numbers))
    return [p for p in out if p]
