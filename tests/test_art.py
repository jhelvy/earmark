"""Cover art. Every rule here exists because breaking it fails *silently* in a
podcast app -- a grey placeholder, no error anywhere."""

from __future__ import annotations

import subprocess

import pytest

from earmark import art
from tests.conftest import needs_ffmpeg

pytestmark = needs_ffmpeg


def make_image(path, width=1254, height=1254, rgba=True):
    """A test image with an alpha channel, which is what a logo export is."""
    fmt = "rgba" if rgba else "rgb24"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=red@0.5:s={width}x{height}",
         "-frames:v", "1", "-pix_fmt", fmt, str(path)],
        check=True,
    )
    return path


def test_produces_a_square_jpeg_within_the_size_budget(tmp_path):
    src = make_image(tmp_path / "logo.png")
    out = art.prepare(src, tmp_path / "cover.jpg")
    assert art.dimensions(out) == (art.DEFAULT_SIZE, art.DEFAULT_SIZE)
    assert out.stat().st_size <= art.MAX_BYTES


def test_upscales_an_image_below_the_1400_minimum(tmp_path):
    # The exact case that started this: a 1254px README logo is under Apple's
    # floor, and an app may refuse it outright.
    src = make_image(tmp_path / "small.png", 600, 600)
    out = art.prepare(src, tmp_path / "cover.jpg", size=1400)
    assert art.dimensions(out) == (1400, 1400)


def test_pads_rather_than_crops_a_non_square_image(tmp_path):
    src = make_image(tmp_path / "wide.png", 2000, 1000)
    out = art.prepare(src, tmp_path / "cover.jpg", size=1400)
    assert art.dimensions(out) == (1400, 1400)


def test_transparency_is_flattened_onto_the_background(tmp_path):
    """A transparent PNG renders wrong in Apple Podcasts, so alpha must go."""
    src = make_image(tmp_path / "logo.png", 1400, 1400)
    out = art.prepare(src, tmp_path / "cover.jpg", background="white")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=pix_fmt", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert "a" not in probe.stdout.strip()  # yuvj420p, not any *a* format


def test_shrinks_when_quality_alone_cannot_reach_the_budget(tmp_path):
    src = make_image(tmp_path / "logo.png", 1400, 1400)
    out = art.prepare(src, tmp_path / "cover.jpg", max_bytes=2000)
    # Either it got under budget, or it fell back to the 1400 floor and stopped
    # -- never an endless recursion, and never smaller than the minimum.
    assert art.dimensions(out)[0] >= art.MIN_SIZE


def test_missing_file_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        art.prepare(tmp_path / "nope.png", tmp_path / "cover.jpg")


def test_dimensions_of_a_non_image_is_none(tmp_path):
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not an image")
    assert art.dimensions(junk) is None
