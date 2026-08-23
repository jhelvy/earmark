"""User configuration, read from ``~/.config/earmark/config.toml``.

Example::

    voice = "af_heart"
    speed = 1.0
    profile = "paper"

    [feed]
    title = "John's Reading Pile"
    folder = "~/pCloud Drive/Public Folder/earmark"
    base_url = "https://filedn.com/XXXXXXXX/earmark"

    [clean.replace]
    BEV = "battery electric vehicle"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from earmark.paths import config_path

DEFAULTS: dict[str, Any] = {
    "voice": "af_heart",
    "speed": 1.0,
    "lang": "en-us",
    "profile": "article",
    "model": "full",
    "engine": "kokoro",
    "bitrate": "64k",
    "sample_rate": 44100,
    "jobs": 1,
    "output_dir": None,
}


@dataclass
class Config:
    values: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))
    feed: dict[str, Any] = field(default_factory=dict)
    replace: dict[str, str] = field(default_factory=dict)
    path: Path | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default if default is not None else DEFAULTS.get(key))


def load(path: Path | None = None) -> Config:
    path = path or config_path()
    if not path.exists():
        return Config(path=path)
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    values = dict(DEFAULTS)
    values.update({k: v for k, v in raw.items() if not isinstance(v, dict)})
    clean_section = raw.get("clean", {})
    if "profile" in clean_section:
        values["profile"] = clean_section["profile"]
    return Config(
        values=values,
        feed=raw.get("feed", {}),
        replace=dict(clean_section.get("replace", {})),
        path=path,
    )
