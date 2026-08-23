"""Turning any image into podcast cover art a phone will actually display.

Podcast apps are unusually strict about the channel image, and they fail
*silently*: a feed with a non-compliant `<itunes:image>` shows the app's grey
placeholder rather than an error, which makes the problem very hard to
diagnose from the phone. The rules that matter, from Apple's spec (Castbox,
Overcast, Pocket Casts and Spotify all follow it):

- square, 1400x1400 minimum, 3000x3000 recommended
- JPEG or PNG, RGB (CMYK is rejected outright)
- **no transparency** -- a PNG with an alpha channel renders wrong
- under 512 KB

A logo exported for a README hits none of the last three: it is usually RGBA,
often under 1400px, and often over 512 KB. So earmark does not ask for a
compliant file, it makes one -- flatten onto a solid background, pad to square,
scale, and step the JPEG quality down until it fits the size budget. The
original is never modified.

ffmpeg does all of it and is already a hard prerequisite, so this costs no new
dependency.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

# Apple's published limits. Every major app follows them.
MIN_SIZE = 1400
MAX_SIZE = 3000
MAX_BYTES = 512 * 1024

DEFAULT_SIZE = MAX_SIZE
DEFAULT_BACKGROUND = "white"
COVER_NAME = "cover.jpg"

# Tried in order until the file fits MAX_BYTES. 2 is visually lossless for a
# logo; 12 is still perfectly readable at the size an app shows it.
_QUALITY_LADDER = (2, 4, 6, 9, 12, 16)

SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def dimensions(path: Path) -> tuple[int, int] | None:
    """(width, height) via ffprobe, or None if it cannot be determined.

    Informational only -- `prepare` copes with any shape. ffprobe ships with
    ffmpeg, but a stripped build might not have it, hence the None.
    """
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    result = subprocess.run(
        [exe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "csv=p=0:s=x", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        width, height = result.stdout.strip().split("\n")[0].split("x")[:2]
    except ValueError:
        return None
    # ffprobe exits 0 with "0x0" on a file it cannot decode.
    if int(width) <= 0 or int(height) <= 0:
        return None
    return int(width), int(height)


def prepare(
    src: Path,
    dest: Path,
    *,
    size: int = DEFAULT_SIZE,
    background: str = DEFAULT_BACKGROUND,
    max_bytes: int = MAX_BYTES,
) -> Path:
    """Write a compliant square JPEG cover at ``dest``. Returns ``dest``.

    Non-square input is **padded**, never cropped: cropping a logo silently
    eats part of it, and a letterboxed cover is a cosmetic problem the user can
    see and fix, not a data loss they cannot.
    """
    from earmark.audio import require_ffmpeg

    src, dest = Path(src), Path(dest)
    if not src.exists():
        raise FileNotFoundError(f"no such image: {src}")
    exe = require_ffmpeg()
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Overlaying onto a generated solid colour is what flattens the alpha
    # channel; scale+pad alone would leave transparency intact.
    chain = (
        f"[1:v]scale={size}:{size}:force_original_aspect_ratio=decrease[fg];"
        f"[0:v][fg]overlay=(W-w)/2:(H-h)/2,format=yuvj420p"
    )
    last = ""
    for quality in _QUALITY_LADDER:
        result = subprocess.run(
            [exe, "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c={background}:s={size}x{size}",
             "-i", str(src),
             "-filter_complex", chain,
             "-frames:v", "1", "-q:v", str(quality), str(dest)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            last = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ""
            raise RuntimeError(f"could not convert {src.name} to cover art: {last}")
        if dest.stat().st_size <= max_bytes:
            return dest

    # Every quality step still too big: the image is enormously detailed.
    # Halving the dimensions is the honest fallback, and 1500px still clears
    # the 1400 minimum.
    if size > MIN_SIZE:
        return prepare(
            src, dest,
            size=max(MIN_SIZE, size // 2),
            background=background,
            max_bytes=max_bytes,
        )
    return dest


def describe(path: Path) -> str:
    """One line about a produced cover, for the CLI to print."""
    dims = dimensions(path)
    shape = f"{dims[0]}x{dims[1]}" if dims else "?"
    return f"{shape}, {path.stat().st_size / 1024:.0f} KB"
