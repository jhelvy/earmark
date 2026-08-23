from pathlib import Path

import pytest

from earmark.publish import (
    CommandPublisher, FolderPublisher, GitHubPagesPublisher, from_config,
)


@pytest.fixture
def mp3(tmp_path):
    path = tmp_path / "episode.mp3"
    path.write_bytes(b"\xff\xfb" + b"0" * 500)
    return path


def test_folder_publisher_round_trip(tmp_path, mp3):
    pub = FolderPublisher(folder=tmp_path / "public", base_url="https://example.com/em/")
    pub.put(mp3, "audio/one.mp3")
    assert (tmp_path / "public" / "audio" / "one.mp3").exists()
    assert pub.url_for("audio/one.mp3") == "https://example.com/em/audio/one.mp3"
    pub.remove("audio/one.mp3")
    assert not (tmp_path / "public" / "audio" / "one.mp3").exists()


def test_folder_publisher_removing_a_missing_file_is_fine(tmp_path):
    FolderPublisher(folder=tmp_path, base_url="https://x.com").remove("nope.mp3")


def test_url_encoding(tmp_path):
    pub = FolderPublisher(folder=tmp_path, base_url="https://x.com/f")
    assert pub.url_for("audio/a b.mp3") == "https://x.com/f/audio/a%20b.mp3"


def test_command_publisher_runs_the_template(tmp_path, mp3):
    dest = tmp_path / "dest"
    dest.mkdir()
    pub = CommandPublisher(
        command="cp {local} " + str(dest) + "/{name}", base_url="https://x.com"
    )
    pub.put(mp3, "one.mp3")
    assert (dest / "one.mp3").exists()


def test_command_publisher_reports_failure(tmp_path, mp3):
    pub = CommandPublisher(command="false {local} {name}", base_url="https://x.com")
    with pytest.raises(RuntimeError, match="publish command failed"):
        pub.put(mp3, "one.mp3")


def test_github_publisher_rejects_oversized_files(tmp_path, monkeypatch, mp3):
    pub = GitHubPagesPublisher(repo=tmp_path, base_url="https://x.github.io/f")
    monkeypatch.setattr(GitHubPagesPublisher, "MAX_FILE_BYTES", 10)
    with pytest.raises(RuntimeError, match="over 100 MB"):
        pub.put(mp3, "big.mp3")


def test_github_publisher_writes_under_subdir(tmp_path, mp3):
    pub = GitHubPagesPublisher(repo=tmp_path, base_url="https://x.github.io/f", subdir="docs")
    pub.put(mp3, "audio/a.mp3")
    assert (tmp_path / "docs" / "audio" / "a.mp3").exists()


@pytest.mark.parametrize(
    "cfg,kind",
    [
        ({"publisher": "folder", "folder": "/tmp/x", "base_url": "https://x.com"}, "folder"),
        ({"publisher": "rclone", "remote": "r2:b", "base_url": "https://x.com"}, "rclone"),
        ({"publisher": "command", "command": "cp {local} {name}", "base_url": "https://x.com"}, "command"),
        ({"publisher": "github", "repo": "/tmp/r", "base_url": "https://x.com"}, "github"),
    ],
)
def test_from_config_builds_each_publisher(cfg, kind):
    assert from_config(cfg).name == kind


def test_from_config_requires_base_url():
    with pytest.raises(ValueError, match="base_url"):
        from_config({"publisher": "folder", "folder": "/tmp/x"})


def test_from_config_requires_publisher_specific_setting():
    with pytest.raises(ValueError, match="feed.folder is required"):
        from_config({"publisher": "folder", "base_url": "https://x.com"})


def test_from_config_rejects_unknown_publisher():
    with pytest.raises(ValueError, match="unknown publisher"):
        from_config({"publisher": "carrier-pigeon", "base_url": "https://x.com"})


def test_folder_publisher_lists_what_it_holds(tmp_path, mp3):
    pub = FolderPublisher(folder=tmp_path / "pub", base_url="https://x.com")
    pub.put(mp3, "audio/a.mp3")
    pub.put(mp3, "feed.xml")
    assert pub.list_names() == ["audio/a.mp3", "feed.xml"]


def test_folder_publisher_lists_nothing_before_first_publish(tmp_path):
    assert FolderPublisher(folder=tmp_path / "nope", base_url="https://x.com").list_names() == []


def test_command_publisher_cannot_enumerate(tmp_path):
    pub = CommandPublisher(command="true", base_url="https://x.com")
    assert pub.list_names() is None
