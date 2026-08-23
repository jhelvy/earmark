"""User configuration, read from ``~/.config/earmark/config.toml``.

Every value is a default that a command-line flag overrides, which is why each
``read`` flag defaults to ``None`` rather than to its real default: ``None``
means "not given", and only then does the config file get a say.

Loading never raises on a bad value. A broken config must still be inspectable
with ``earmark config show``, so problems are collected and only turned into an
error by :meth:`Config.check`, called by the commands about to use the values.

Example::

    voice = "af_heart"
    speed = 1.0
    profile = "paper"

    [feed]
    title = "John's Reading Pile"
    folder = "~/pCloud Drive/public/earmark"
    base_url = "https://filedn.com/XXXXXXXX/earmark"

    [clean.replace]
    BEV = "battery electric vehicle"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from earmark import paths

DEFAULTS: dict[str, Any] = {
    "voice": "af_heart",
    "speed": 1.0,
    "lang": "en-us",
    "profile": "article",
    "model": "full",
    "engine": "kokoro",
    "bitrate": "64k",
    "sample_rate": 44100,
    "output_dir": None,
}

PROFILES = ("article", "paper", "book")
MODELS = ("full", "fp16", "int8")
ENGINES = ("kokoro", "say")
SPEED_RANGE = (0.5, 2.0)

# Tables are handled separately from scalar keys; anything else at the top level
# is a typo worth reporting rather than silently ignoring.
KNOWN_TABLES = ("feed", "clean")

TEMPLATE = """\
# earmark configuration
#
# Everything here is a default. A command-line flag always wins.
# Uncomment what you want to change.

# voice = "af_heart"      # see: earmark voices
# speed = 1.0             # 0.5 to 2.0
# lang = "en-us"
# profile = "article"     # article | paper | book
# model = "full"          # full | fp16 | int8
# engine = "kokoro"       # kokoro | say
# bitrate = "64k"
# sample_rate = 44100
# output_dir = "~/Audiobooks"

# Fix a mispronunciation once instead of every time. Matched on word
# boundaries, longest key first.
[clean.replace]
# BEV = "battery electric vehicle"

# Written for you by: earmark feed init --help
# [feed]
# publisher = "folder"
# folder = "~/pCloud Drive/public/earmark"
# base_url = "https://filedn.com/XXXXXXXX/earmark"
# title = "My Reading Pile"
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
        return self.values.get(key, default if default is not None else DEFAULTS.get(key))

    def check(self) -> None:
        """Raise if any value cannot be used. Call before acting on settings."""
        if self.errors:
            where = f" in {self.path}" if self.path else ""
            raise ConfigError(f"config problem{where}:\n  " + "\n  ".join(self.errors))


def _validate(values: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    def bad(key: str, want: str) -> None:
        errors.append(f"{key} = {values[key]!r} is not {want}")

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

    for key in ("sample_rate",):
        value = values.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            bad(key, "a positive whole number")

    output_dir = values.get("output_dir")
    if output_dir is not None and not isinstance(output_dir, str):
        bad("output_dir", "a path string")

    return errors


def load(path: Path | None = None) -> Config:
    path = path or paths.config_path()
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

    clean_section = raw.get("clean", {})
    if "profile" in clean_section:
        values["profile"] = clean_section["profile"]
    for key in clean_section:
        if key not in ("profile", "replace"):
            warnings.append(f"unknown setting 'clean.{key}' ignored")

    replace = clean_section.get("replace", {})
    if not isinstance(replace, dict):
        replace = {}
        warnings.append("[clean.replace] must be a table of strings; ignored")

    return Config(
        values=values,
        feed=raw.get("feed", {}),
        replace={str(k): str(v) for k, v in replace.items()},
        path=path,
        errors=_validate(values),
        warnings=warnings,
    )


def init(path: Path | None = None, force: bool = False) -> tuple[Path, bool]:
    """Write the commented template. Returns (path, whether it was written)."""
    path = path or paths.config_path()
    if path.exists() and not force:
        return path, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return path, True
