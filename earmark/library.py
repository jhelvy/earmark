"""The library: one folder that holds the config, the text, the audio and the feed.

A library is self-contained on purpose. ``earmark.toml`` sits inside it, so the
config never needs a ``library =`` key -- the library *is* the folder the config
file lives in. Copy the folder and the podcast moves with it, and pointing
earmark at a second library is a ``cd`` rather than a setting.

Only one thing lives outside a library: ``~/.config/earmark/default``, a single
line naming the library to use when the working directory does not answer the
question. It holds a path, never a setting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from earmark import paths

CONFIG_NAME = "earmark.toml"
TEXT_DIR = "text"
AUDIO_DIR = "audio"
FEED_FILE = "feed.xml"
STATE_FILE = "episodes.json"


class LibraryError(Exception):
    """No usable library could be found."""


def _walk_up(start: Path) -> Path | None:
    for folder in [start, *start.parents]:
        if (folder / CONFIG_NAME).is_file():
            return folder
    return None


def read_default() -> Path | None:
    pointer = paths.pointer_path()
    if not pointer.is_file():
        return None
    text = pointer.read_text(encoding="utf-8").strip()
    return Path(text).expanduser() if text else None


def write_default(root: Path) -> Path:
    pointer = paths.pointer_path()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"{root}\n", encoding="utf-8")
    return pointer


def find(explicit: str | os.PathLike | None = None) -> Path:
    """Resolve the library to act on.

    ``--library`` beats ``$EARMARK_LIBRARY``, which beats an ``earmark.toml``
    in the working directory or above it, which beats the recorded default.
    The walk-up rule is what makes ``cd`` the way to switch libraries.
    """
    if explicit:
        return Path(explicit).expanduser().resolve()

    env = os.environ.get("EARMARK_LIBRARY")
    if env:
        return Path(env).expanduser().resolve()

    found = _walk_up(Path.cwd().resolve())
    if found is not None:
        return found

    default = read_default()
    if default is not None:
        return default.resolve()

    raise LibraryError(
        "no library found.\n"
        "  Make one:   earmark init ~/path/to/library --base-url https://example.com/audio\n"
        "  Or point at one:  earmark --library ~/path/to/library ..."
    )


@dataclass(frozen=True)
class Library:
    """Where everything in one library lives."""

    root: Path

    @classmethod
    def at(cls, root: Path | str) -> "Library":
        return cls(root=Path(root).expanduser().resolve())

    @classmethod
    def resolve(cls, explicit: str | None = None, *, must_exist: bool = True) -> "Library":
        lib = cls.at(find(explicit))
        if must_exist and not lib.config_path.is_file():
            raise LibraryError(
                f"{lib.root} is not a library ({CONFIG_NAME} is missing).\n"
                f"  Make it one:  earmark init {lib.root}"
            )
        return lib

    @property
    def config_path(self) -> Path:
        return self.root / CONFIG_NAME

    @property
    def text_dir(self) -> Path:
        return self.root / TEXT_DIR

    @property
    def audio_dir(self) -> Path:
        return self.root / AUDIO_DIR

    @property
    def state_path(self) -> Path:
        return self.root / STATE_FILE

    @property
    def feed_path(self) -> Path:
        return self.root / FEED_FILE

    def audio_path(self, slug: str) -> Path:
        return self.audio_dir / f"{slug}.mp3"

    def markdown_path(self, slug: str) -> Path:
        return self.text_dir / f"{slug}.md"

    def ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.text_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def contains(self, path: Path) -> bool:
        try:
            Path(path).expanduser().resolve().relative_to(self.root)
        except ValueError:
            return False
        return True
