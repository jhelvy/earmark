"""Filesystem locations.

Models live in the *data* directory, never the cache: ``earmark cache clear``
must not delete a 354 MB download.
"""

from __future__ import annotations

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
    return Path(user_config_dir(APP))


def config_path() -> Path:
    return config_dir() / "config.toml"


def episodes_path() -> Path:
    return config_dir() / "episodes.json"
