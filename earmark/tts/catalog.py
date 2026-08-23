"""What the voice names mean.

Kokoro ships 54 voices named ``af_heart``, ``am_puck``, ``bf_emma`` -- a
language letter, a gender letter, a given name. That is unguessable from the
outside, and the quality spread is enormous: ``af_heart`` is graded A and
``am_adam`` is graded F+, yet the flat list gives no hint which is which.

Grades are the overall grades published in Kokoro's own VOICES.md. Only the
English voices are graded there; the rest are listed without one rather than
invented. Data only -- no logic belongs in this file.
"""

from __future__ import annotations

LANGUAGES = {
    "a": "American English",
    "b": "British English",
    "e": "Spanish",
    "f": "French",
    "h": "Hindi",
    "i": "Italian",
    "j": "Japanese",
    "p": "Brazilian Portuguese",
    "z": "Mandarin Chinese",
}

GENDERS = {"f": "female", "m": "male"}

# Overall grade from https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
GRADES = {
    "af_heart": "A",
    "af_bella": "A-",
    "af_nicole": "B-",
    "af_aoede": "C+",
    "af_kore": "C+",
    "af_sarah": "C+",
    "af_alloy": "C",
    "af_nova": "C",
    "af_sky": "C-",
    "af_jessica": "D",
    "af_river": "D",
    "am_fenrir": "C+",
    "am_michael": "C+",
    "am_puck": "C+",
    "am_echo": "D",
    "am_eric": "D",
    "am_liam": "D",
    "am_onyx": "D",
    "am_santa": "D-",
    "am_adam": "F+",
    "bf_emma": "B-",
    "bf_isabella": "C",
    "bf_alice": "D",
    "bf_lily": "D",
    "bm_fable": "C",
    "bm_george": "C",
    "bm_lewis": "D+",
    "bm_daniel": "D",
}

GRADE_ORDER = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F+", "F"]

DEFAULT_VOICE = "af_heart"

SAMPLE_TEXT = (
    "The dominant sequence transduction models are based on complex "
    "recurrent or convolutional neural networks."
)


def language_of(voice: str) -> str:
    return LANGUAGES.get(voice[:1], "Other")


def gender_of(voice: str) -> str:
    return GENDERS.get(voice[1:2], "")


def grade_of(voice: str) -> str:
    return GRADES.get(voice, "")


def sort_key(voice: str) -> tuple[int, str]:
    """Best-graded first, then alphabetical. Ungraded voices sort last."""
    grade = grade_of(voice)
    rank = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else len(GRADE_ORDER)
    return (rank, voice)


def group(voices: list[str]) -> dict[str, list[str]]:
    """Voices by language, English first, best grade first within a language."""
    out: dict[str, list[str]] = {}
    for voice in voices:
        out.setdefault(language_of(voice), []).append(voice)
    order = list(LANGUAGES.values())
    return {
        lang: sorted(out[lang], key=sort_key)
        for lang in sorted(out, key=lambda n: order.index(n) if n in order else 99)
    }
