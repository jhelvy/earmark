"""Filesystem locations outside a library.

Almost nothing lives here. A library holds its own config, state, text and
audio; what remains is the machine-local stuff that must *not* sync to a public
folder: the 354 MB model download, the synthesis cache, and a one-line pointer
at the default library.

Models live in the *data* directory, never the cache: clearing the chunk cache
must not delete a 354 MB download.
"""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir

APP = "earmark"


def cache_dir() -> Path:
    return Path(user_cache_dir(APP))


def chunk_cache_dir() -> Path:
    return cache_dir() / "chunks"


def data_dir() -> Path:
    return Path(user_data_dir(APP))


def models_dir() -> Path:
    return data_dir() / "models"


def state_dir() -> Path:
    """Where the default-library pointer lives.

    Not platformdirs on macOS: there ``user_config_dir`` and ``user_data_dir``
    are the *same* path, so the pointer would sit inside the directory holding
    a 354 MB models/ folder. ``EARMARK_CONFIG_DIR`` overrides it, which is also
    how the test suite keeps out of a real home directory.
    """
    override = os.environ.get("EARMARK_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(user_config_dir(APP))
    return Path.home() / ".config" / APP


def pointer_path() -> Path:
    return state_dir() / "default"
