"""Voice catalog: making 54 opaque names legible."""

from __future__ import annotations

import pytest

from earmark.tts import catalog


def test_name_decoding():
    assert catalog.language_of("af_heart") == "American English"
    assert catalog.language_of("bm_george") == "British English"
    assert catalog.language_of("zf_xiaoni") == "Mandarin Chinese"
    assert catalog.gender_of("af_heart") == "female"
    assert catalog.gender_of("am_puck") == "male"


def test_unknown_prefix_is_not_a_crash():
    assert catalog.language_of("qq_test") == "Other"
    assert catalog.gender_of("aq_test") == ""


def test_best_voice_sorts_first():
    ordered = sorted(["am_adam", "af_bella", "af_heart"], key=catalog.sort_key)
    assert ordered == ["af_heart", "af_bella", "am_adam"]


def test_ungraded_voices_sort_last():
    ordered = sorted(["zf_xiaoni", "am_adam"], key=catalog.sort_key)
    assert ordered == ["am_adam", "zf_xiaoni"]


def test_grouping_puts_english_first():
    groups = catalog.group(["zf_xiaoni", "bf_emma", "af_heart"])
    assert list(groups) == ["American English", "British English", "Mandarin Chinese"]


def test_default_voice_is_the_best_graded_one():
    """If this ever fails, either the default or the grade table moved."""
    assert catalog.grade_of(catalog.DEFAULT_VOICE) == "A"


@pytest.mark.parametrize("voice", catalog.GRADES)
def test_every_grade_is_orderable(voice):
    assert catalog.GRADES[voice] in catalog.GRADE_ORDER


def test_grades_only_claimed_for_english():
    """VOICES.md grades only English; inventing grades for the rest would be
    making them up."""
    assert all(v[0] in "ab" for v in catalog.GRADES)
