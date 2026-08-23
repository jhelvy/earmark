"""Kokoro-82M via kokoro-onnx."""

from __future__ import annotations

import numpy as np

from earmark import models
from earmark.tts import SAMPLE_RATE

DEFAULT_VOICE = "af_heart"
SPEED_RANGE = (0.5, 2.0)


class KokoroBackend:
    name = "kokoro"
    sample_rate = SAMPLE_RATE

    def __init__(self, variant: str = "full", download: bool = True):
        self.variant = variant
        if not models.is_downloaded(variant) and not download:
            raise RuntimeError(
                "the Kokoro model files are not downloaded yet; run: earmark models download"
            )
        self._model_path, self._voices_path = models.ensure(variant)
        self._kokoro = None

    @property
    def kokoro(self):
        if self._kokoro is None:
            import onnxruntime

            # The graph has ops the CPU provider cannot constant-fold, and it
            # says so once per node. Nothing is wrong; nobody needs to see it.
            onnxruntime.set_default_logger_severity(3)
            from kokoro_onnx import Kokoro

            self._kokoro = Kokoro(str(self._model_path), str(self._voices_path))
        return self._kokoro

    def voices(self) -> list[str]:
        return sorted(self.kokoro.get_voices())

    def fingerprint(self) -> str:
        size = self._model_path.stat().st_size
        return f"kokoro-onnx/{self._model_path.name}@{size}"

    def synth(
        self,
        text: str,
        voice: str = DEFAULT_VOICE,
        speed: float = 1.0,
        lang: str = "en-us",
    ) -> np.ndarray:
        low, high = SPEED_RANGE
        if not low <= speed <= high:
            raise ValueError(f"speed must be between {low} and {high}, got {speed}")
        samples, rate = self.kokoro.create(text, voice=voice, speed=speed, lang=lang)
        if rate != self.sample_rate:  # pragma: no cover - kokoro is fixed at 24 kHz
            raise RuntimeError(f"unexpected sample rate {rate} from kokoro")
        return np.asarray(samples, dtype=np.float32)
