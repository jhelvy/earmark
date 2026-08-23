"""macOS ``say``.

Here so that earmark does something useful before a 354 MB download, and so
that the Backend protocol has a second implementation keeping it honest.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from earmark.tts import SAMPLE_RATE


class SayBackend:
    name = "say"
    sample_rate = SAMPLE_RATE

    def __init__(self, **_):
        if platform.system() != "Darwin" or not shutil.which("say"):
            raise RuntimeError("the 'say' engine is only available on macOS")

    def voices(self) -> list[str]:
        out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
        return sorted({line.split()[0] for line in out.splitlines() if line.strip()})

    def fingerprint(self) -> str:
        return f"say/{platform.mac_ver()[0]}"

    def synth(
        self, text: str, voice: str = "Samantha", speed: float = 1.0, lang: str = "en-us"
    ) -> np.ndarray:
        # say refuses LEF32@24000 ("Opening output file failed: fmt?") but
        # accepts 16-bit at the same rate, so ask for that and convert.
        words_per_minute = int(175 * speed)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "s.wav"
            cmd = [
                "say", "-r", str(words_per_minute),
                f"--data-format=LEI16@{self.sample_rate}", "-o", str(out),
            ]
            # Kokoro voice names mean nothing here; fall back to the default.
            if voice and not voice[:3] in {"af_", "am_", "bf_", "bm_"}:
                cmd += ["-v", voice]
            subprocess.run([*cmd, text], check=True, capture_output=True)
            with wave.open(str(out), "rb") as wav:
                raw = wav.readframes(wav.getnframes())
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
