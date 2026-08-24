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


# The cache exists to make a re-run of the same document fast, and to make an
# edit to one paragraph cost one paragraph. Neither needs history: an entry
# untouched for a season will not be wanted, and the ceiling stops a year of
# reading from quietly filling a disk. Both are enforced after a run rather
# than by a command, because a cache the user has to remember to empty is a
# cache that fills up.
MAX_AGE_DAYS = 90
MAX_BYTES = 2_000_000_000


def autoprune(max_bytes: int = MAX_BYTES, max_age_days: float = MAX_AGE_DAYS) -> tuple[int, int]:
    """Drop stale entries, then the least recently used, until under budget."""
    removed, freed = clear(max_age_days)

    paths = entries()
    stats = [(p, p.stat()) for p in paths]
    total = sum(s.st_size for _, s in stats)
    if total <= max_bytes:
        return removed, freed

    for path, stat in sorted(stats, key=lambda pair: pair[1].st_atime):
        if total <= max_bytes:
            break
        path.unlink(missing_ok=True)
        total -= stat.st_size
        freed += stat.st_size
        removed += 1
    return removed, freed
