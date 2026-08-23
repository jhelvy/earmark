"""Filesystem locations.

Models live in the *data* directory, never the cache: ``earmark cache clear``
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


def config_dir() -> Path:
    """Where config.toml and episodes.json live.

    Not platformdirs on macOS: there ``user_config_dir`` and ``user_data_dir``
    are the *same* path, so config.toml would sit inside the directory holding
    a 354 MB models/ folder. ~/.config/earmark is both distinct from the data
    directory and where someone editing a CLI's config actually looks.
    """
    override = os.environ.get("EARMARK_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        return Path(user_config_dir(APP))
    return Path.home() / ".config" / APP


def config_path() -> Path:
    return config_dir() / "config.toml"


def episodes_path() -> Path:
    return config_dir() / "episodes.json"
