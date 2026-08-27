"""Encoding synthesized audio to MP3.

One ffmpeg process, fed raw float32 over a pipe. No temporary WAV files, no
concat list, constant memory, and exactly one encode.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable, Iterator

import numpy as np

from earmark.tts import SAMPLE_RATE

DEFAULT_BITRATE = "64k"
# Kokoro produces 24 kHz. MP3 at 24 kHz is MPEG-2 Layer III, whose half-rate
# frames confuse the seek bar in some podcast players and car head units.
# Resampling to 44.1 kHz costs nothing in quality (there is no content above
# ~12 kHz) and keeps the file in MPEG-1 territory.
DEFAULT_SAMPLE_RATE = 44_100


def require_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError(
            "ffmpeg is required but was not found on PATH; install it with "
            "'brew install ffmpeg' (macOS), 'apt install ffmpeg' (Linux) or "
            "'winget install Gyan.FFmpeg' (Windows)"
        )
    return exe


def silence(seconds: float, rate: int = SAMPLE_RATE) -> np.ndarray:
    return np.zeros(int(seconds * rate), dtype=np.float32)


def encode(
    stream: Iterable[np.ndarray],
    out_path: Path,
    bitrate: str = DEFAULT_BITRATE,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    input_rate: int = SAMPLE_RATE,
) -> int:
    """Encode a stream of float32 mono arrays to one MP3. Returns sample count."""
    exe = require_ffmpeg()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        exe, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "f32le", "-ar", str(input_rate), "-ac", "1", "-i", "pipe:0",
        "-c:a", "libmp3lame", "-b:a", bitrate,
        "-ar", str(sample_rate), "-ac", "1",
        "-write_xing", "1",
        str(out_path),
    ]
    written = 0
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert proc.stdin is not None
        for block in stream:
            if block is None or len(block) == 0:
                continue
            proc.stdin.write(np.ascontiguousarray(block, dtype="<f4").tobytes())
            written += len(block)
        proc.stdin.close()
    except BrokenPipeError:  # pragma: no cover - only on an ffmpeg crash
        pass
    stderr = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.strip().splitlines()[-1] if stderr.strip() else '(no output)'}")
    if written == 0:
        raise RuntimeError("nothing to encode: the document produced no speakable text")
    return written


def duration_seconds(samples: int, rate: int = SAMPLE_RATE) -> float:
    return samples / rate


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def probe_duration(path) -> float:
    """Length of an existing audio file, in seconds.

    mutagen is already a dependency for ID3 tags and reads the header without
    decoding, so publishing a file someone else made costs no ffmpeg run.
    """
    from pathlib import Path

    import mutagen

    handle = mutagen.File(str(Path(path)))
    if handle is None or handle.info is None:
        raise RuntimeError(f"could not read an audio duration from {path}")
    return float(handle.info.length)
