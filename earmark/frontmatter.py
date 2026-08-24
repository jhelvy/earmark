"""YAML-ish front matter on the Markdown earmark writes.

``earmark text`` produces a file you are meant to edit by hand, and ``earmark
audio`` then has to answer two questions about it: what is the title, and has
this text already been through the cleaner? Re-cleaning an edited file would
undo the edit with the same rules that made it, so the answer has to be written
down rather than guessed.

The format is deliberately not YAML -- no dependency, and nothing to learn.
Every line is ``key: value``, split on the *first* colon so a title may contain
one, and every value is a plain string.
"""

from __future__ import annotations

from dataclasses import dataclass

FENCE = "---"
CLEANED = "cleaned"
KEYS = ("title", "author", "date", "source", "earmark")


@dataclass
class Parsed:
    fields: dict[str, str]
    body: str

    @property
    def is_cleaned(self) -> bool:
        return self.fields.get("earmark", "").strip() == CLEANED


def parse(text: str) -> Parsed:
    """Split front matter from body. Text without a leading fence is all body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return Parsed(fields={}, body=text)

    fields: dict[str, str] = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == FENCE:
            return Parsed(fields=fields, body="\n".join(lines[i + 1:]).lstrip("\n"))
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        fields[key.strip().lower()] = value.strip()
    # An unterminated block is not front matter; treat the whole file as body.
    return Parsed(fields={}, body=text)


def dump(meta, body: str, *, cleaned: bool = True) -> str:
    """Render a document with front matter carrying its metadata."""
    fields = {
        "title": meta.title,
        "author": meta.author,
        "date": meta.date,
        "source": meta.source,
        "earmark": CLEANED if cleaned else None,
    }
    lines = [FENCE]
    lines += [f"{k}: {v}" for k, v in fields.items() if v]
    lines.append(FENCE)
    return "\n".join(lines) + "\n\n" + body.strip() + "\n"
