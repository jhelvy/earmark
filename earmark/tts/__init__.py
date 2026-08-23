"""Speech backends.

The protocol is deliberately small. ``fingerprint()`` is the part that is easy
to leave out and expensive to miss: it goes into the synthesis cache key, so
without it a switch to a different model silently replays the old audio.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np

SAMPLE_RATE = 24_000


@runtime_checkable
class Backend(Protocol):
    name: str
    sample_rate: int

    def voices(self) -> list[str]: ...

    def synth(self, text: str, voice: str, speed: float, lang: str) -> np.ndarray: ...

    def fingerprint(self) -> str: ...


def get_backend(name: str = "kokoro", **kwargs) -> Backend:
    if name == "kokoro":
        from earmark.tts.kokoro import KokoroBackend

        return KokoroBackend(**kwargs)
    if name == "say":
        from earmark.tts.say import SayBackend

        return SayBackend(**kwargs)
    raise ValueError(f"unknown engine {name!r}; expected 'kokoro' or 'say'")
