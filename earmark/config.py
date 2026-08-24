"""Library configuration, read from ``<library>/earmark.toml``.

Every value is a default that a command-line flag overrides, which is why each
flag defaults to ``None`` rather than to its real default: ``None`` means "not
given", and only then does the config file get a say.

Loading never raises on a bad value. A broken config must still be inspectable
with ``earmark config --show``, so problems are collected and only turned into
an error by :meth:`Config.check`, called by the commands about to use them.

There is no ``library`` key and there never will be: the library is the folder
this file sits in.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULTS: dict[str, Any] = {
    "voice": "af_heart",
    "speed": 1.0,
    "lang": "en-us",
    "profile": "article",
    "model": "full",
    "engine": "kokoro",
    "bitrate": "64k",
    "sample_rate": 44100,
    "after_publish": None,
}

PROFILES = ("article", "paper", "book")
MODELS = ("full", "fp16", "int8")
ENGINES = ("kokoro", "say")
SPEED_RANGE = (0.5, 2.0)

FEED_KEYS = (
    "base_url", "title", "author", "description", "link", "language", "category",
    # `cover` is a file in the library that earmark normalizes; `image` is a URL
    # to artwork hosted somewhere else, which earmark only passes through.
    "cover", "image",
)
KNOWN_TABLES = ("feed", "replace")

TEMPLATE = """\
# earmark configuration
#
# This file marks the folder it lives in as an earmark library. Everything
# earmark makes -- markdown in text/, MP3s, feed.xml -- lands beside it.
#
# Every setting here is a default; a command-line flag always wins.

# voice = "af_heart"      # see: earmark voices
# speed = 1.0             # 0.5 to 2.0
# profile = "article"     # article | paper | book
# lang = "en-us"
# model = "full"          # full | fp16 | int8
# engine = "kokoro"       # kokoro | say
# bitrate = "64k"
# sample_rate = 44100

# Run this after every publish, from inside the library. Only needed if your
# library is not already a folder that syncs to the web -- a git push, say.
# after_publish = "git add -A && git commit -m 'earmark' && git push"

# Fix a mispronunciation once instead of every time. Matched on word
# boundaries, longest key first.
[replace]
# BEV = "battery electric vehicle"

# [feed] is last on purpose. TOML puts a key you add at the bottom of the file
# into whichever table came before it, and an unknown key here warns, while an
# extra entry under [replace] would look like a word you wanted respoken.
[feed]
base_url = "{base_url}"
title = "{title}"
# author = "Your Name"
# description = "Things I meant to read."
# cover = "cover.jpg"     # a file in this folder; square PNG or JPEG
# image = "https://..."   # or artwork already hosted somewhere; this wins
"""


class ConfigError(Exception):
    """A config value that cannot be used as written."""


@dataclass
class Config:
    values: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))
    feed: dict[str, Any] = field(default_factory=dict)
    replace: dict[str, str] = field(default_factory=dict)
    path: Path | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.values.get(key, DEFAULTS.get(key))
        return default if value is None and default is not None else value

    def check(self) -> None:
        """Raise if any value cannot be used. Call before acting on settings."""
        if self.errors:
            where = f" in {self.path}" if self.path else ""
            raise ConfigError(f"config problem{where}:\n  " + "\n  ".join(self.errors))

    def require_base_url(self) -> str:
        url = (self.feed.get("base_url") or "").strip().rstrip("/")
        if not url:
            raise ConfigError(
                "no base_url set. Publishing needs the public URL your library "
                f"is served at.\n  Set it with:  earmark config    (in [feed], {self.path})"
            )
        return url


def _validate(values: dict[str, Any], feed: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def bad(key: str, want: str) -> None:
        errors.append(f"{key} = {values.get(key)!r} is not {want}")

    speed = values.get("speed")
    if not isinstance(speed, (int, float)) or isinstance(speed, bool):
        bad("speed", "a number")
    elif not SPEED_RANGE[0] <= speed <= SPEED_RANGE[1]:
        bad("speed", f"between {SPEED_RANGE[0]} and {SPEED_RANGE[1]}")

    for key, allowed in (("profile", PROFILES), ("model", MODELS), ("engine", ENGINES)):
        if values.get(key) not in allowed:
            bad(key, "one of " + ", ".join(allowed))

    for key in ("voice", "lang", "bitrate"):
        if not isinstance(values.get(key), str) or not values[key].strip():
            bad(key, "a non-empty string")

    sample_rate = values.get("sample_rate")
    if not isinstance(sample_rate, int) or isinstance(sample_rate, bool) or sample_rate < 1:
        bad("sample_rate", "a positive whole number")

    after = values.get("after_publish")
    if after is not None and not isinstance(after, str):
        bad("after_publish", "a shell command string")

    base_url = feed.get("base_url")
    if base_url is not None:
        if not isinstance(base_url, str):
            errors.append("feed.base_url is not a URL string")
        elif base_url.strip() and not base_url.startswith(("http://", "https://")):
            errors.append(f"feed.base_url = {base_url!r} must start with http:// or https://")

    return errors


def load(path: Path) -> Config:
    """Read one library's config. Missing file means built-in defaults."""
    path = Path(path)
    if not path.exists():
        return Config(path=path)

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        return Config(path=path, errors=[f"not valid TOML: {exc}"])

    warnings: list[str] = []
    values = dict(DEFAULTS)
    for key, value in raw.items():
        if isinstance(value, dict):
            if key not in KNOWN_TABLES:
                warnings.append(f"unknown section [{key}] ignored")
            continue
        if key not in DEFAULTS:
            warnings.append(f"unknown setting {key!r} ignored")
            continue
        values[key] = value

    feed = dict(raw.get("feed", {}))
    for key in list(feed):
        if key not in FEED_KEYS:
            warnings.append(f"unknown setting 'feed.{key}' ignored")
            feed.pop(key)

    replace = raw.get("replace", {})
    if not isinstance(replace, dict):
        replace = {}
        warnings.append("[replace] must be a table of strings; ignored")

    return Config(
        values=values,
        feed=feed,
        replace={str(k): str(v) for k, v in replace.items()},
        path=path,
        errors=_validate(values, feed),
        warnings=warnings,
    )


def render_template(base_url: str = "", title: str = "earmark") -> str:
    return TEMPLATE.format(base_url=base_url.rstrip("/"), title=title)


def init(path: Path, *, base_url: str = "", title: str = "earmark", force: bool = False):
    """Write the commented template. Returns (path, whether it was written)."""
    path = Path(path)
    if path.exists() and not force:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_template(base_url, title), encoding="utf-8")
    return path, True
