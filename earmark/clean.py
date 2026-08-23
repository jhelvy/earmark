"""Turn Markdown into text that sounds good read aloud.

This is the module that decides whether earmark is pleasant or unbearable, so
it is written as an explicit ordered pipeline of small named functions rather
than one clever pass. Each transform is independently testable, and
:class:`CleanOptions` decides which ones run.

The output is a list of :class:`Block`, not a string: headings have to survive
as structure so that ``chunk.py`` can put a pause after them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, replace as _replace
from typing import Literal

from earmark.lexicon import (
    ABBREVIATIONS,
    MONEY_SUFFIXES,
    REFERENCE_HEADINGS,
    UNITS,
)

# Bump whenever a transform changes what comes out of this module. It is part
# of the synthesis cache key, so a stale bump means stale audio.
CLEAN_SCHEMA_VERSION = "3"

BlockKind = Literal["title", "heading", "para", "item"]


@dataclass(frozen=True)
class Block:
    kind: BlockKind
    text: str
    level: int = 0


@dataclass(frozen=True)
class CleanOptions:
    say_code: bool = False
    tables: Literal["drop", "describe"] = "drop"
    drop_citations: bool = True
    drop_author_year: bool = False
    drop_references: bool = True
    drop_links: bool = True
    drop_sections: tuple[str, ...] = ()
    replace: dict[str, str] = field(default_factory=dict)


PROFILES: dict[str, CleanOptions] = {
    # Web articles and essays: never strip author-year, since "(and it was
    # cheap, too)" looks a lot like a citation to a regex.
    "article": CleanOptions(),
    "paper": CleanOptions(drop_author_year=True),
    # A book's back matter may be a real chapter, so keep it.
    "book": CleanOptions(tables="describe", drop_references=False),
}


def options_for(profile: str = "article", **overrides) -> CleanOptions:
    """Build :class:`CleanOptions` from a profile plus explicit overrides."""
    try:
        base = PROFILES[profile]
    except KeyError:
        raise ValueError(
            f"unknown profile {profile!r}; expected one of {', '.join(PROFILES)}"
        ) from None
    overrides = {k: v for k, v in overrides.items() if v is not None}
    return _replace(base, **overrides) if overrides else base


# --------------------------------------------------------------------------
# Block-level transforms. These are line-oriented and run before anything
# that works on inline syntax.
# --------------------------------------------------------------------------

_FRONTMATTER = re.compile(r"\A(---|\+\+\+)\n.*?\n\1\s*\n", re.DOTALL)
_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_TABLE_SEP = re.compile(r"^\s*\|?[\s:\-|]*-[\s:\-|]*\|?\s*$")
_HRULE = re.compile(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
_FOOTNOTE_DEF = re.compile(r"^\s*\[\^[^\]]+\]:")
_LINK_DEF = re.compile(r"^\s*\[[^\]^]+\]:\s*\S+")


def strip_frontmatter(text: str) -> str:
    return _FRONTMATTER.sub("", text, count=1)


def strip_code_fences(text: str, say_code: bool = False) -> str:
    """Remove fenced code blocks.

    Runs before every other transform so that no later regex can reach inside
    a code block and mangle it into speech.
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.split("\n"):
        if fence is None:
            m = _FENCE.match(line)
            if m:
                fence = m.group(1)[0] * 3
                if say_code:
                    out.append("Code block omitted.")
                continue
            out.append(line)
        else:
            if _FENCE.match(line) and line.strip().startswith(fence):
                fence = None
    return "\n".join(out)


def strip_html(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    # A space, not "": otherwise words on either side of a tag fuse together.
    return re.sub(r"</?[a-zA-Z][^>]*>", " ", text)


def strip_math(text: str) -> str:
    text = re.sub(r"\$\$.*?\$\$", "", text, flags=re.DOTALL)
    text = re.sub(r"\\\[.*?\\\]", "", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{equation\*?\}.*?\\end\{equation\*?\}", "", text, flags=re.DOTALL)

    def _inline(m: re.Match[str]) -> str:
        body = m.group(1)
        # A bare "$n$" is worth saying; anything with LaTeX machinery is not.
        return "" if re.search(r"[\\^_{}]", body) else body

    text = re.sub(r"\$([^$\n]{1,60})\$", _inline, text)
    return re.sub(r"\\\((.*?)\\\)", lambda m: _inline(m), text)


def strip_tables(text: str, mode: str = "drop") -> str:
    """Remove GFM pipe tables. Reading a table aloud is unlistenable."""
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        is_table = (
            "|" in lines[i]
            and i + 1 < len(lines)
            and "|" in lines[i + 1]
            and _TABLE_SEP.match(lines[i + 1])
        )
        if not is_table:
            out.append(lines[i])
            i += 1
            continue
        while i < len(lines) and lines[i].strip() and "|" in lines[i]:
            i += 1
        if mode == "describe":
            out.append("Table omitted.")
    return "\n".join(out)


_ORPHAN_ROW = re.compile(r"^\s*\|.*\|\s*$")


def strip_orphan_table_rows(text: str) -> str:
    """Drop lone pipe-wrapped rows left behind by HTML infoboxes."""
    return "\n".join(
        line for line in text.split("\n") if not _ORPHAN_ROW.match(line)
    )


def _heading_text(line: str) -> tuple[int, str] | None:
    m = _HEADING.match(line)
    return (len(m.group(1)), m.group(2)) if m else None


def drop_sections(text: str, names: tuple[str, ...]) -> str:
    """Cut from a matching heading to the next heading of equal-or-higher level.

    On a paper this is the single highest-value transform in the module: it is
    what stops the last ten minutes of audio being a bibliography.
    """
    if not names:
        return text
    lines = text.split("\n")
    out: list[str] = []
    cutting_at: int | None = None
    for line in lines:
        head = _heading_text(line)
        if head is not None:
            level, title = head
            norm = re.sub(r"^\d+[.)]?\s*", "", title).strip().lower().rstrip(":")
            if cutting_at is not None and level <= cutting_at:
                cutting_at = None
            if cutting_at is None and any(norm.startswith(n) for n in names):
                cutting_at = level
                continue
        if cutting_at is None:
            out.append(line)
    return "\n".join(out)


def strip_definition_lines(text: str) -> str:
    """Drop footnote definitions and link reference definitions."""
    out: list[str] = []
    skipping = False
    for line in text.split("\n"):
        if _FOOTNOTE_DEF.match(line):
            skipping = True
            continue
        if skipping:
            # Continuation lines of a footnote are indented.
            if line.startswith(("    ", "\t")) or not line.strip():
                if not line.strip():
                    skipping = False
                continue
            skipping = False
        if _LINK_DEF.match(line):
            continue
        out.append(line)
    return "\n".join(out)


# --------------------------------------------------------------------------
# Inline transforms.
# --------------------------------------------------------------------------

_ESCAPE = re.compile(r"\\([\\\[\]()*_~`#+.!-])")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# A link whose text is itself a bracketed marker: "[[update]](url)".
_NESTED_LINK = re.compile(r"\[\[[^\]]*\]\]\([^)]*\)")
# Wikipedia-style editorial markers. Nobody wants these narrated.
_EDITORIAL = re.compile(
    r"\[\s*(?:citation needed|update|clarification needed|sic|dead link|"
    r"verification needed|who\?|when\?|why\?|according to whom)\s*\]",
    re.I,
)
_INLINE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_REF_LINK = re.compile(r"\[([^\]^]*)\]\[[^\]]*\]")
_AUTOLINK = re.compile(r"<https?://[^>]+>")
_BARE_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+")
_FOOTNOTE_MARK = re.compile(r"\[\^[^\]]+\]")
_NUM_CITATION = re.compile(r"\[\s*\d+(\s*[,;–—-]\s*\d+)*\s*\]")
_AUTHOR_YEAR = re.compile(
    r"\(\s*(?:see\s+)?[A-Z][A-Za-z''`-]+"
    r"(?:\s+(?:et al\.?|and|&|,)\s*[A-Z]?[A-Za-z''`-]*)*"
    r",?\s*(?:19|20)\d{2}[a-z]?"
    r"(?:\s*[;,]\s*[^()]{0,60}?(?:19|20)\d{2}[a-z]?)*\s*\)"
)
_INLINE_CODE = re.compile(r"`+([^`]*)`+")
_BOLD_ITALIC = re.compile(r"(\*{1,3}|_{1,3}|~~)(?=\S)(.+?)(?<=\S)\1")


def unescape_markdown(text: str) -> str:
    r"""Turn ``\[update\]`` back into ``[update]`` so bracket rules can see it."""
    return _ESCAPE.sub(r"\1", text)


def strip_editorial(text: str) -> str:
    return _EDITORIAL.sub(" ", text)


def strip_images(text: str) -> str:
    return _IMAGE.sub(" ", text)


def strip_links(text: str, drop_targets: bool = True) -> str:
    if not drop_targets:
        return text
    text = _NESTED_LINK.sub(" ", text)
    # Padded with spaces: two adjacent links must not fuse into one word.
    text = _INLINE_LINK.sub(r" \1 ", text)
    text = _REF_LINK.sub(r" \1 ", text)
    text = _AUTOLINK.sub(" ", text)
    return _BARE_URL.sub(" ", text)


def strip_citations(text: str, numeric: bool = True, author_year: bool = False) -> str:
    text = _FOOTNOTE_MARK.sub(" ", text)
    if numeric:
        text = _NUM_CITATION.sub(" ", text)
    if author_year:
        text = _AUTHOR_YEAR.sub("", text)
    return text


_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# The reversed side-stamp every arXiv PDF carries: "...:viXra" is "arXiv:..."
# read bottom-to-top. Harmless to drop, and it appears on every preprint.
_ARXIV_STAMP = re.compile(r"^.*:viXra.*$", re.MULTILINE)
# Removing citations can leave "such as [1] and [2]." as "such as and."
_VERB_AFTER = (
    r"(?:are|is|was|were|be|been|have|has|had|can|could|will|would|may|might|do|does)\b"
)
_DANGLING = [
    # "such as [1] and [2] are common" -> "such as and are common"
    (re.compile(r"\b(such as|as in|see also|see)\s+(?:and|or)\b", re.I), r"\1"),
    # A lead-in with nothing left to introduce: drop the lead-in itself.
    (
        re.compile(
            r"[,;]?\s*\b(?:such as|as in|similar to|including|see also|see)\s+"
            r"(?=" + _VERB_AFTER + r"|[.,;:])",
            re.I,
        ),
        " ",
    ),
    (
        re.compile(
            r"[,;]?\s*\b(?:such as|as in|similar to|including|see also|see)\s*(?=[.,;:)])",
            re.I,
        ),
        "",
    ),
    (re.compile(r"\s+(?:and|or)\s*(?=[.,;:])", re.I), ""),
    # Guarded so it cannot eat the parentheses in "df.head()".
    (re.compile(r"(?<![\w)])\(\s*[,;]?\s*\)"), ""),
]


def strip_emails(text: str) -> str:
    return _EMAIL.sub("", text)


def strip_arxiv_stamp(text: str) -> str:
    return _ARXIV_STAMP.sub("", text)


def repair_after_citations(text: str) -> str:
    """Tidy the grammar wreckage that citation removal leaves behind."""
    for pattern, repl in _DANGLING:
        text = pattern.sub(repl, text)
    return text


def strip_emphasis(text: str) -> str:
    text = _INLINE_CODE.sub(r"\1", text)
    for _ in range(3):  # nested emphasis needs a couple of passes
        new = _BOLD_ITALIC.sub(r"\2", text)
        if new == text:
            break
        text = new
    return text


# --------------------------------------------------------------------------
# Word-level transforms. These must run AFTER structure is settled and,
# critically, BEFORE sentence splitting in chunk.py -- expanding trailing-period
# abbreviations is what removes the main source of bogus sentence breaks.
# --------------------------------------------------------------------------

def _table_pattern(keys) -> re.Pattern[str]:
    ordered = sorted(keys, key=len, reverse=True)
    return re.compile("|".join(re.escape(k) for k in ordered))


_ABBREV_RE = _table_pattern(ABBREVIATIONS)
# Word-like units need word boundaries so "km" does not fire inside "kmart".
# Symbol units must not have them: in "42%" the "%" is preceded by a digit.
_UNIT_WORDS = sorted((k for k in UNITS if k[0].isalnum()), key=len, reverse=True)
_UNIT_SYMBOLS = sorted((k for k in UNITS if not k[0].isalnum()), key=len, reverse=True)
_UNIT_WORD_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(k) for k in _UNIT_WORDS) + r")(?![A-Za-z0-9])"
)
_UNIT_SYMBOL_RE = re.compile("(" + "|".join(re.escape(k) for k in _UNIT_SYMBOLS) + ")")
_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*([KMBT])\b")
_PLAIN_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
_GROUPED_DIGITS = re.compile(r"\b(\d{1,3}(?:,\d{3})+)\b")
_RANGE = re.compile(r"(?<=\d)\s*[–—]\s*(?=\d)")


def expand_abbreviations(text: str) -> str:
    return _ABBREV_RE.sub(lambda m: ABBREVIATIONS[m.group(0)], text)


def expand_units(text: str) -> str:
    text = _UNIT_WORD_RE.sub(lambda m: UNITS[m.group(1)], text)
    # The leading space keeps "42%" from becoming "42percent"; _tidy collapses
    # any double space this introduces.
    return _UNIT_SYMBOL_RE.sub(lambda m: " " + UNITS[m.group(1)], text)


def expand_numbers(text: str) -> str:
    text = _MONEY.sub(
        lambda m: f"{m.group(1).replace(',', '')} {MONEY_SUFFIXES[m.group(2)]} dollars", text
    )
    text = _PLAIN_MONEY.sub(lambda m: f"{m.group(1).replace(',', '')} dollars", text)
    text = _GROUPED_DIGITS.sub(lambda m: m.group(1).replace(",", ""), text)
    return _RANGE.sub(" to ", text)


def normalize_punctuation(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\s*[–—]\s*", ", ", text)
    text = text.replace("\u2026", ", ")
    # Drop emoji and other symbol/control codepoints.
    text = "".join(
        ch for ch in text if unicodedata.category(ch)[0] != "C" or ch == "\n"
    )
    text = "".join(ch for ch in text if unicodedata.category(ch) not in {"So", "Sk"})
    return text


def apply_replacements(text: str, table: dict[str, str]) -> str:
    """User pronunciation fixes from the config file. Applied last."""
    if not table:
        return text
    pattern = re.compile(
        r"(?<![A-Za-z0-9])("
        + "|".join(re.escape(k) for k in sorted(table, key=len, reverse=True))
        + r")(?![A-Za-z0-9])"
    )
    return pattern.sub(lambda m: table[m.group(1)], text)


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])\1+", r"\1", text)
    text = re.sub(r"(?<![\w)])\(\s*\)", "", text)
    return text.strip(" ,;:")


def to_blocks(text: str) -> list[Block]:
    """Group cleaned lines into headings, paragraphs and list items."""
    blocks: list[Block] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            body = _tidy(" ".join(buffer))
            if body and not is_figure_dump(body):
                blocks.append(Block("para", body))
            buffer.clear()

    lines = text.split("\n")
    for i, raw in enumerate(lines):
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if _HRULE.match(line):
            flush()
            continue
        head = _heading_text(line)
        if head is not None:
            flush()
            body = _tidy(head[1])
            if body:
                blocks.append(Block("heading", _terminate(body), head[0]))
            continue
        if _SETEXT.match(line) and buffer:
            body = _tidy(" ".join(buffer))
            buffer.clear()
            if body:
                level = 1 if line.strip().startswith("=") else 2
                blocks.append(Block("heading", _terminate(body), level))
            continue
        item = _LIST_ITEM.match(line)
        if item:
            flush()
            body = _tidy(item.group(1))
            if body:
                # The appended period is what stops a bulleted list being read
                # as one breathless run-on sentence.
                blocks.append(Block("item", _terminate(body)))
            continue
        buffer.append(re.sub(r"^\s*>+\s?", "", line))
    flush()
    return blocks


_TOKEN = re.compile(r"\S+")


def is_figure_dump(text: str, threshold: int = 3) -> bool:
    """True for the token soup that comes out of extracting a figure.

    Attention heatmaps, axis labels and similar artwork extract as the same
    short token repeated back to back ("ehT ehT waL waL"). Immediate repetition
    at this rate essentially never occurs in prose, so it is a safe signal.
    """
    tokens = _TOKEN.findall(text)
    if len(tokens) < 8:
        return False
    runs = 0
    for a, b in zip(tokens, tokens[1:]):
        if a == b:
            runs += 1
    return runs >= threshold or runs / len(tokens) > 0.15


def _terminate(text: str) -> str:
    return text if text.endswith((".", "!", "?", ":", ";")) else text + "."


def clean(markdown: str, opts: CleanOptions | None = None) -> list[Block]:
    """Run the full pipeline. The order of these calls is load-bearing."""
    opts = opts or CleanOptions()
    text = markdown

    # Structure first: code fences before anything that could reach inside one.
    text = strip_frontmatter(text)
    text = strip_code_fences(text, say_code=opts.say_code)
    text = strip_html(text)
    text = strip_math(text)
    text = strip_tables(text, mode=opts.tables)
    text = strip_orphan_table_rows(text)
    text = strip_definition_lines(text)

    names = tuple(n.lower() for n in opts.drop_sections)
    if opts.drop_references:
        names = names + REFERENCE_HEADINGS
    text = drop_sections(text, names)

    # Then inline syntax.
    text = unescape_markdown(text)
    text = strip_editorial(text)
    text = strip_images(text)
    text = strip_links(text, drop_targets=opts.drop_links)
    text = strip_citations(
        text, numeric=opts.drop_citations, author_year=opts.drop_author_year
    )
    if opts.drop_citations or opts.drop_author_year:
        text = repair_after_citations(text)
    text = strip_emphasis(text)
    text = strip_emails(text)
    text = strip_arxiv_stamp(text)

    # Then words. Abbreviations before anything downstream splits sentences.
    text = expand_abbreviations(text)
    text = expand_units(text)
    text = expand_numbers(text)
    text = normalize_punctuation(text)
    text = apply_replacements(text, opts.replace)

    return to_blocks(text)


def render(blocks: list[Block]) -> str:
    """Flatten blocks back to plain text, for ``earmark text``."""
    return "\n\n".join(b.text for b in blocks)
