from __future__ import annotations

import shutil

import numpy as np
import pytest

from earmark.tts import SAMPLE_RATE

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)


class FakeBackend:
    """A backend that produces silence at a plausible speaking rate.

    Lets the whole pipeline -- chunking, pauses, a real ffmpeg encode -- run in
    the test suite without the 325 MB model.
    """

    name = "fake"
    sample_rate = SAMPLE_RATE

    def __init__(self, chars_per_second: float = 15.0):
        self.chars_per_second = chars_per_second
        self.calls: list[str] = []

    def voices(self) -> list[str]:
        return ["af_heart"]

    def fingerprint(self) -> str:
        return "fake/1"

    def synth(self, text, voice="af_heart", speed=1.0, lang="en-us"):
        self.calls.append(text)
        n = int(len(text) / self.chars_per_second * self.sample_rate / speed)
        return np.zeros(max(n, 1), dtype=np.float32)


@pytest.fixture
def backend():
    return FakeBackend()


@pytest.fixture(autouse=True)
def tmp_dirs(tmp_path, monkeypatch):
    """Keep cache, config and model paths out of the real home directory."""
    import earmark.paths as paths

    monkeypatch.setattr(paths, "cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(paths, "config_dir", lambda: tmp_path / "config")
    return tmp_path
