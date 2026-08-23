"""Content-addressed cache of synthesized chunks.

At ~4.6x realtime a full paper costs minutes, so re-rendering after editing one
paragraph should not re-synthesize the other fifty-six chunks.

Entries are headerless little-endian int16. The audio is on its way to a 64
kbps MP3, so 16-bit is transparent, and it halves the cache: a 22-minute paper
costs ~62 MB instead of ~125 MB.
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np

from earmark.clean import CLEAN_SCHEMA_VERSION
from earmark import paths

_SCALE = 32767.0
SUFFIX = ".i16"
LEGACY_SUFFIXES = (".f32",)
DEFAULT_MAX_AGE_DAYS = 30


def chunks_dir() -> Path:
    return paths.cache_dir() / "chunks"


def key(
    text: str,
    fingerprint: str,
    voice: str,
    speed: float,
    lang: str,
    pause_before: float = 0.0,
    pause_after: float = 0.0,
) -> str:
    """Hash everything that can change the audio.

    The backend fingerprint and the clean-schema version are the two parts that
    are easy to omit and expensive to miss: without them, switching models or
    changing a cleaning rule silently replays the old audio.
    """
    parts = [
        fingerprint,
        voice,
        f"{speed:.3f}",
        lang,
        f"{pause_before:.3f}",
        f"{pause_after:.3f}",
        CLEAN_SCHEMA_VERSION,
        text,
    ]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:32]


def path_for(key_: str) -> Path:
    # Two-hex fan-out so one directory never holds fifty thousand entries.
    return chunks_dir() / key_[:2] / f"{key_}{SUFFIX}"


def get(key_: str) -> np.ndarray | None:
    path = path_for(key_)
    if not path.exists():
        return None
    try:
        data = np.frombuffer(path.read_bytes(), dtype="<i2")
    except (OSError, ValueError):
        return None
    if data.size == 0:
        return None
    # Refresh atime so pruning by age keeps what is actually in use.
    try:
        now = time.time()
        import os

        os.utime(path, (now, path.stat().st_mtime))
    except OSError:  # pragma: no cover - read-only cache dir
        pass
    return data.astype(np.float32) / _SCALE


def put(key_: str, samples: np.ndarray) -> None:
    path = path_for(key_)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(SUFFIX + ".tmp")
    clipped = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    quantized = np.rint(clipped * _SCALE).astype("<i2")
    tmp.write_bytes(np.ascontiguousarray(quantized).tobytes())
    tmp.replace(path)


def entries() -> list[Path]:
    root = chunks_dir()
    if not root.exists():
        return []
    found: list[Path] = []
    for suffix in (SUFFIX, *LEGACY_SUFFIXES):
        found.extend(root.rglob(f"*{suffix}"))
    return sorted(found)


def info() -> dict:
    paths = entries()
    stats = [p.stat() for p in paths]
    return {
        "count": len(paths),
        "bytes": sum(s.st_size for s in stats),
        "oldest": min((s.st_atime for s in stats), default=None),
        "newest": max((s.st_atime for s in stats), default=None),
    }


def clear(older_than_days: float | None = None) -> tuple[int, int]:
    """Delete cache entries. Returns (files removed, bytes freed)."""
    cutoff = time.time() - older_than_days * 86400 if older_than_days else None
    removed = freed = 0
    for path in entries():
        stat = path.stat()
        if cutoff is not None and stat.st_atime >= cutoff:
            continue
        freed += stat.st_size
        path.unlink()
        removed += 1
    for directory in sorted(chunks_dir().glob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return removed, freed
