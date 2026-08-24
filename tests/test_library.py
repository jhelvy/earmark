"""Finding the library, and where things land inside it."""

from __future__ import annotations

import pytest

from earmark import library as library_mod
from earmark.library import Library, LibraryError


@pytest.fixture
def two(tmp_path):
    from earmark import config as config_mod

    made = []
    for name in ("papers", "fiction"):
        lib = Library.at(tmp_path / name)
        lib.ensure_dirs()
        config_mod.init(lib.config_path, base_url=f"https://example.com/{name}")
        made.append(lib)
    return made


def test_explicit_beats_everything(two, monkeypatch, tmp_path):
    papers, fiction = two
    monkeypatch.chdir(fiction.root)
    monkeypatch.setenv("EARMARK_LIBRARY", str(fiction.root))
    library_mod.write_default(fiction.root)
    assert library_mod.find(str(papers.root)) == papers.root


def test_env_beats_the_working_directory(two, monkeypatch):
    papers, fiction = two
    monkeypatch.chdir(fiction.root)
    monkeypatch.setenv("EARMARK_LIBRARY", str(papers.root))
    assert library_mod.find() == papers.root


def test_the_working_directory_beats_the_default(two, monkeypatch):
    papers, fiction = two
    library_mod.write_default(papers.root)
    monkeypatch.chdir(fiction.root)
    assert library_mod.find() == fiction.root


def test_a_nested_directory_walks_up(two, monkeypatch):
    papers, _ = two
    deep = papers.root / "text" / "deeper"
    deep.mkdir(parents=True)
    monkeypatch.chdir(deep)
    assert library_mod.find() == papers.root


def test_the_default_is_the_last_resort(two, monkeypatch, tmp_path):
    papers, _ = two
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    library_mod.write_default(papers.root)
    assert library_mod.find() == papers.root


def test_nothing_anywhere_explains_how_to_start(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(LibraryError, match="earmark init"):
        library_mod.find()


def test_a_folder_without_a_config_is_not_a_library(tmp_path):
    with pytest.raises(LibraryError, match="is not a library"):
        Library.resolve(str(tmp_path))


def test_layout(two):
    papers, _ = two
    assert papers.config_path == papers.root / "earmark.toml"
    assert papers.markdown_path("a-paper") == papers.root / "text" / "a-paper.md"
    assert papers.audio_path("a-paper") == papers.root / "audio" / "a-paper.mp3"
    assert papers.feed_path == papers.root / "feed.xml"
    assert papers.state_path == papers.root / "episodes.json"


def test_the_config_has_no_library_key(two):
    """The library is the folder, so moving it must need no edit."""
    papers, _ = two
    from earmark.config import DEFAULTS, load

    assert "library" not in DEFAULTS
    assert load(papers.config_path).warnings == []
    assert "library =" not in papers.config_path.read_text()


def test_a_library_survives_being_moved(two, monkeypatch, tmp_path):
    from earmark.config import load

    papers, _ = two
    moved = tmp_path / "moved-elsewhere"
    papers.root.rename(moved)
    monkeypatch.chdir(moved)
    assert library_mod.find() == moved
    assert load(Library.at(moved).config_path).errors == []
