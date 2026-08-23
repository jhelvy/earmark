"""Downloading the Kokoro model files.

kokoro-onnx does not fetch anything itself -- ``KoKoroConfig.validate()`` only
raises ``FileNotFoundError`` -- so this is required infrastructure rather than a
convenience.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

from earmark import paths

RELEASE = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
)

# Measured on an Apple Silicon CPU: full 4.7x realtime, fp16 4.4x, int8 1.8x.
# onnxruntime's CPU provider has no fast quantized kernels for this graph, so
# the smaller variants buy disk space and cost speed. "full" is the default.
MODELS: dict[str, str] = {
    "full": "kokoro-v1.0.onnx",
    "fp16": "kokoro-v1.0.fp16.onnx",
    "int8": "kokoro-v1.0.int8.onnx",
}
VOICES_FILE = "voices-v1.0.bin"

_CHUNK = 1 << 20


def model_path(variant: str = "full") -> Path:
    try:
        return paths.models_dir() / MODELS[variant]
    except KeyError:
        raise ValueError(
            f"unknown model {variant!r}; expected one of {', '.join(MODELS)}"
        ) from None


def voices_path() -> Path:
    return paths.models_dir() / VOICES_FILE


def is_downloaded(variant: str = "full") -> bool:
    return model_path(variant).exists() and voices_path().exists()


def _download(url: str, dest: Path, progress=None) -> None:
    """Fetch one file, resuming a partial download if one is lying around."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0

    request = urllib.request.Request(url)
    if have:
        request.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(request) as resp:  # noqa: S310
        resuming = resp.status == 206
        if have and not resuming:
            have = 0
        total = int(resp.headers.get("Content-Length", 0)) + have
        mode = "ab" if resuming and have else "wb"
        task = progress(dest.name, total, have) if progress else None
        with part.open(mode) as fh:
            while block := resp.read(_CHUNK):
                fh.write(block)
                if task:
                    task(len(block))

    size = part.stat().st_size
    if total and size != total:
        part.unlink(missing_ok=True)
        raise RuntimeError(
            f"download of {dest.name} was truncated: got {size} bytes, expected {total}"
        )
    part.replace(dest)


def ensure(variant: str = "full", progress=None) -> tuple[Path, Path]:
    """Return paths to the model and voices files, downloading what is missing."""
    model, voices = model_path(variant), voices_path()
    if not model.exists():
        _download(RELEASE + MODELS[variant], model, progress)
    if not voices.exists():
        _download(RELEASE + VOICES_FILE, voices, progress)
    return model, voices


def remove(variant: str | None = None) -> list[Path]:
    targets = [voices_path()] if variant is None else []
    targets += [model_path(v) for v in (MODELS if variant is None else [variant])]
    removed = []
    for path in targets:
        if path.exists():
            path.unlink()
            removed.append(path)
    return removed
