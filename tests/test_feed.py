import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from earmark import feed as feed_mod
from earmark.feed import Episode, FeedConfig, FeedState
from earmark.feedops import Library, parse_size
from earmark.publish import FolderPublisher, from_config

ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
ATOM = "{http://www.w3.org/2005/Atom}"


@pytest.fixture
def state():
    return FeedState(
        config=FeedConfig(title="Reading Pile", author="Jane Doe"),
        episodes=[
            Episode(id="a1", title="First", filename="a.mp3", bytes=1234,
                    seconds=61, published="2026-01-01", author="Jane"),
            Episode(id="b2", title="Second", filename="b.mp3", bytes=5678,
                    seconds=3661, published="2026-02-01"),
        ],
    )


def xml_of(state):
    return ET.fromstring(feed_mod.build(state, lambda n: f"https://example.com/{n}"))


def test_required_channel_elements(state):
    channel = xml_of(state).find("channel")
    for tag in ("title", "description", "link", "language", "lastBuildDate"):
        assert channel.findtext(tag), f"missing <{tag}>"
    assert channel.find(f"{ATOM}link").get("rel") == "self"
    assert channel.findtext(f"{ITUNES}author") == "Jane Doe"
    assert channel.find(f"{ITUNES}category") is not None
    assert channel.findtext(f"{ITUNES}explicit") == "false"


def test_items_are_newest_first(state):
    titles = [i.findtext("title") for i in xml_of(state).find("channel").findall("item")]
    assert titles == ["Second", "First"]


def test_enclosure_carries_exact_byte_length(state):
    item = xml_of(state).find("channel").find("item")
    enclosure = item.find("enclosure")
    assert enclosure.get("length") == "5678"
    assert enclosure.get("type") == "audio/mpeg"
    assert enclosure.get("url") == "https://example.com/audio/b.mp3"


def test_duration_formatting(state):
    items = xml_of(state).find("channel").findall("item")
    assert items[0].findtext(f"{ITUNES}duration") == "1:01:01"
    assert items[1].findtext(f"{ITUNES}duration") == "0:01:01"


def test_guid_is_not_a_permalink(state):
    guid = xml_of(state).find("channel").find("item").find("guid")
    assert guid.get("isPermaLink") == "false" and guid.text == "b2"


def test_state_round_trips(state):
    assert FeedState.from_json(state.to_json()).episodes[0].title == "First"


@pytest.mark.parametrize(
    "text,expected",
    [("800MB", 800_000_000), ("2GB", 2_000_000_000), ("1500", 1500), ("1.5 GB", 1_500_000_000)],
)
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_parse_size_rejects_nonsense():
    with pytest.raises(ValueError):
        parse_size("some big number")


@pytest.fixture
def library(tmp_path, state):
    from earmark import feed as fm

    pub = FolderPublisher(folder=tmp_path / "pub", base_url="https://example.com/em")
    lib = Library(state=state, publisher=pub, path=tmp_path / "episodes.json")
    return lib


def _fake_mp3(tmp_path, name, size=2048):
    path = tmp_path / name
    path.write_bytes(b"\xff\xfb" + b"0" * size)
    return path


def test_orphans_are_detected_and_removable(library, tmp_path):
    library.publisher.put(_fake_mp3(tmp_path, "stray.mp3"), "audio/stray.mp3")
    library.publisher.put(_fake_mp3(tmp_path, "a.mp3"), "audio/a.mp3")
    assert library.orphans() == ["audio/stray.mp3"]
    assert library.drop_orphans() == ["audio/stray.mp3"]
    assert library.orphans() == []


def test_feed_and_manifest_are_never_orphans(library, tmp_path):
    library.publish_feed()
    assert library.orphans() == []


def test_prune_keeps_the_newest(library, tmp_path):
    for e in library.state.episodes:
        library.publisher.put(_fake_mp3(tmp_path, e.filename), e.name)
    dropped = library.prune(keep=1)
    assert [d.title for d in dropped] == ["First"]
    assert [e.title for e in library.state.episodes] == ["Second"]
    assert library.orphans() == []


def test_prune_respects_a_size_budget(library, tmp_path):
    for e in library.state.episodes:
        library.publisher.put(_fake_mp3(tmp_path, e.filename), e.name)
    library.prune(max_bytes=6000)
    assert [e.title for e in library.state.episodes] == ["Second"]


def test_republishing_the_same_file_replaces_its_episode(library, tmp_path):
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(tmp_path, "same.mp3")
    meta = Metadata(title="Same", source="https://example.com/a")
    before = len(library.state.episodes)
    library.add(mp3, meta, 10.0)
    library.add(mp3, meta, 10.0)
    assert len(library.state.episodes) == before + 1


def test_local_paths_never_reach_the_feed(library, tmp_path):
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(tmp_path, "local.mp3")
    episode = library.add(mp3, Metadata(title="Local", source="/Users/me/secret/paper.pdf"), 5.0)
    assert episode.source is None
    xml = feed_mod.build(library.state, library.publisher.url_for).decode()
    assert "/Users/me" not in xml


def test_no_image_elements_when_no_cover_is_set(state):
    channel = xml_of(state).find("channel")
    assert channel.find(f"{ITUNES}image") is None
    assert channel.find("image") is None


def test_cover_appears_in_both_image_spellings(state):
    state.config.image = "https://example.com/cover.jpg"
    channel = xml_of(state).find("channel")
    # <itunes:image> is what podcast apps read; plain <image> is what feed
    # validators want. A cover that shows in neither is the bug being guarded.
    assert channel.find(f"{ITUNES}image").get("href") == "https://example.com/cover.jpg"
    assert channel.find("image/url").text == "https://example.com/cover.jpg"
    assert channel.find("image/title").text == state.config.title


def test_cover_is_never_an_orphan(library, tmp_path):
    from earmark import art

    library.publisher.put(_fake_mp3(tmp_path, "c.jpg"), art.COVER_NAME)
    library.state.config.image = library.publisher.url_for(art.COVER_NAME)
    library.publish_feed()
    assert library.orphans() == []


def test_set_cover_publishes_and_points_the_feed_at_it(library, tmp_path):
    import shutil as _shutil

    if _shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    from earmark import art

    src = tmp_path / "logo.png"
    __import__("subprocess").run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "color=c=blue:s=800x800",
         "-frames:v", "1", "-pix_fmt", "rgba", str(src)],
        check=True,
    )
    url, detail = library.set_cover(src, size=1400)
    assert f"/{art.COVER_NAME}?v=" in url
    assert library.state.config.image == url
    assert (library.publisher.folder / art.COVER_NAME).exists()
    assert "1400x1400" in detail


def test_a_config_image_still_wins_over_the_published_one(tmp_path):
    """Setting `image` by hand in [feed] must not be silently overwritten."""
    lib = Library.open({
        "publisher": "folder",
        "folder": str(tmp_path / "pub"),
        "base_url": "https://example.com/em",
        "image": "https://cdn.example.com/mine.png",
    })
    assert lib.state.config.image == "https://cdn.example.com/mine.png"


def test_cover_url_is_cache_busted_by_content(library, tmp_path):
    """Apps cache artwork by URL, so a changed cover must be a changed URL."""
    import shutil as _shutil
    import subprocess

    if _shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    def image(name, colour):
        path = tmp_path / name
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c={colour}:s=800x800",
             "-frames:v", "1", "-pix_fmt", "rgba", str(path)],
            check=True,
        )
        return path

    first, _ = library.set_cover(image("a.png", "blue"), size=1400)
    again, _ = library.set_cover(image("a2.png", "blue"), size=1400)
    changed, _ = library.set_cover(image("b.png", "green"), size=1400)
    assert "?v=" in first
    assert first == again          # same bytes, same URL: no pointless refetch
    assert changed != first
