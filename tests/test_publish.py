"""The library, viewed as a public web folder."""

from __future__ import annotations

import pytest

from earmark.publish import PublishError, Site, check_url


@pytest.fixture
def mp3(tmp_path):
    path = tmp_path / "episode.mp3"
    path.write_bytes(b"\xff\xfb" + b"0" * 500)
    return path


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    return Site(root=root, base_url="https://example.com/em/")


def test_put_copies_a_file_in(site, mp3):
    site.put(mp3, "one.mp3")
    assert (site.root / "one.mp3").read_bytes() == mp3.read_bytes()


def test_put_is_a_no_op_for_a_file_already_in_place(site, mp3):
    import shutil

    shutil.copy2(mp3, site.root / "one.mp3")
    site.put(site.root / "one.mp3", "one.mp3")
    assert (site.root / "one.mp3").exists()


def test_url_for_joins_and_encodes(site):
    assert site.url_for("one.mp3") == "https://example.com/em/one.mp3"
    assert site.url_for("a b.mp3") == "https://example.com/em/a%20b.mp3"


def test_remove_tolerates_a_missing_file(site):
    site.remove("nope.mp3")


def test_list_names_sees_only_files(site, mp3):
    site.put(mp3, "one.mp3")
    (site.root / "text").mkdir()
    assert site.list_names() == ["one.mp3"]


def test_finish_runs_the_hook_inside_the_library(site):
    site.finish("pwd > where.txt")
    assert (site.root / "where.txt").read_text().strip() == str(site.root)


def test_finish_does_nothing_without_a_hook(site):
    site.finish(None)
    site.finish("   ")
    assert site.list_names() == []


def test_finish_reports_a_failing_hook(site):
    with pytest.raises(PublishError, match="after_publish failed"):
        site.finish("false")


def test_check_url_reports_the_failure_rather_than_raising():
    ok, detail = check_url("http://127.0.0.1:9/nothing", timeout=0.5)
    assert ok is False and detail
