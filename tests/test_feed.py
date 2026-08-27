import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from earmark import feed as feed_mod
from earmark.feed import Episode, FeedConfig, FeedState
from earmark.feedops import Feed, parse_size
from earmark.publish import Site

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
def published(tmp_path, state, library):
    """A Feed over a real library folder, pre-loaded with two episodes."""
    return Feed(
        library=library,
        state=state,
        site=Site(root=library.root, base_url="https://example.com/em"),
    )


def _fake_mp3(tmp_path, name, size=2048):
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfb" + b"0" * size)
    return path


def test_orphans_are_detected_and_removable(published, tmp_path):
    published.site.put(_fake_mp3(tmp_path, "stray.mp3"), "audio/stray.mp3")
    published.site.put(_fake_mp3(tmp_path, "a.mp3"), "audio/a.mp3")
    assert published.orphans() == ["audio/stray.mp3"]
    assert published.drop_orphans() == ["audio/stray.mp3"]
    assert published.orphans() == []


def test_the_config_and_feed_are_never_orphans(published):
    published.write()
    assert published.orphans() == []


def test_text_is_never_an_orphan(published):
    """The Markdown is the editable source, not something the feed points at."""
    (published.library.text_dir / "note.md").write_text("hi", encoding="utf-8")
    published.write()
    assert published.orphans() == []


def test_prune_keeps_the_newest(published, tmp_path):
    for e in published.state.episodes:
        published.site.put(_fake_mp3(tmp_path, e.filename), e.name)
    dropped = published.prune(keep=1)
    assert [d.title for d in dropped] == ["First"]
    assert [e.title for e in published.state.episodes] == ["Second"]
    assert published.orphans() == []


def test_prune_respects_a_size_budget(published, tmp_path):
    for e in published.state.episodes:
        published.site.put(_fake_mp3(tmp_path, e.filename), e.name)
    published.prune(max_bytes=6000)
    assert [e.title for e in published.state.episodes] == ["Second"]


def test_remove_takes_the_episode_and_its_audio(published, tmp_path):
    for e in published.state.episodes:
        published.site.put(_fake_mp3(tmp_path, e.filename), e.name)
    dropped = published.remove(published.match("First"))
    assert [d.title for d in dropped] == ["First"]
    assert [e.title for e in published.state.episodes] == ["Second"]
    assert not (published.library.root / "audio" / "a.mp3").exists()
    assert published.orphans() == []


def test_a_number_means_a_line_of_the_listing(published):
    """The listing is newest first, so 1 is the newest episode, not the first
    one added."""
    assert [e.title for e in published.listing()] == ["Second", "First"]
    assert published.match("1")[0].title == "Second"
    assert published.match("2")[0].title == "First"


def test_matching_a_title_ignores_case_and_matches_a_part(published):
    assert published.match("seco")[0].title == "Second"
    assert published.match("SECOND")[0].title == "Second"


def test_an_exact_title_wins_over_a_longer_one_containing_it(published):
    published.state.episodes.append(
        Episode(id="c3", title="First Principles", filename="c.mp3", bytes=9,
                seconds=9, published="2026-03-01")
    )
    assert [e.title for e in published.match("First")] == ["First"]
    assert [e.title for e in published.match("first p")] == ["First Principles"]


def test_text_that_matches_nothing_is_an_error(published):
    with pytest.raises(ValueError, match="no episode matches"):
        published.match("nothing here")
    with pytest.raises(ValueError, match="the feed has 2"):
        published.match("9")


def test_select_takes_numbers_ranges_and_titles_at_once(published):
    published.state.episodes.append(
        Episode(id="c3", title="Third", filename="c.mp3", bytes=9,
                seconds=9, published="2026-03-01")
    )
    picked = published.select(["1-2, First"])
    assert [e.title for e in picked] == ["Third", "Second", "First"]


def test_select_returns_each_episode_once_and_newest_first(published):
    picked = published.select(["2", "First", "seco"])
    assert [e.title for e in picked] == ["Second", "First"]


def test_republishing_the_same_file_replaces_its_episode(published, tmp_path):
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(tmp_path, "same.mp3")
    meta = Metadata(title="Same", source="https://example.com/a")
    before = len(published.state.episodes)
    published.add(mp3, meta, 10.0)
    published.add(mp3, meta, 10.0)
    assert len(published.state.episodes) == before + 1


def test_an_episode_keeps_the_name_convert_gave_it(published, library, tmp_path):
    """convert writes audio/<slug>.mp3; publish must not rename it."""
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(library.audio_dir, "attention-is-all-you-need.mp3")
    episode = published.add(mp3, Metadata(title="Attention Is All You Need"), 10.0)
    assert episode.filename == "attention-is-all-you-need.mp3"
    assert episode.name == "audio/attention-is-all-you-need.mp3"


def test_an_outside_mp3_is_named_from_its_title(published, tmp_path):
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(tmp_path, "recording001.mp3")
    episode = published.add(mp3, Metadata(title="A Talk I Gave"), 10.0)
    assert episode.filename == "a-talk-i-gave.mp3"
    assert (published.library.audio_dir / "a-talk-i-gave.mp3").exists()


def test_local_paths_never_reach_the_feed(published, tmp_path):
    from earmark.extract.meta import Metadata

    mp3 = _fake_mp3(tmp_path, "local.mp3")
    episode = published.add(mp3, Metadata(title="Local", source="/Users/me/secret/paper.pdf"), 5.0)
    assert episode.source is None
    xml = feed_mod.build(published.state, published.site.url_for).decode()
    assert "/Users/me" not in xml


def test_write_runs_the_after_publish_hook(published):
    published.after_publish = "pwd > ran.txt"
    published.write()
    assert (published.library.root / "ran.txt").read_text().strip() == str(published.library.root)


def test_write_leaves_feed_xml_in_the_library(published):
    url = published.write()
    assert published.library.feed_path.is_file()
    assert published.library.state_path.is_file()
    assert url == "https://example.com/em/feed.xml"


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


def test_cover_is_never_an_orphan(published, tmp_path):
    from earmark import art

    published.site.put(_fake_mp3(tmp_path, "c.jpg"), art.COVER_NAME)
    published.state.config.image = published.site.url_for(art.COVER_NAME)
    published.write()
    assert published.orphans() == []


def test_no_cover_configured_is_not_an_error(published):
    assert published.refresh_cover() is None


def test_a_missing_cover_file_is_named(published):
    published.cover = "nope.png"
    with pytest.raises(FileNotFoundError, match="nope.png"):
        published.refresh_cover()


@pytest.fixture
def solid_image(tmp_path):
    import shutil as _shutil
    import subprocess

    if _shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")

    def make(name, colour):
        path = tmp_path / name
        subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "lavfi", "-i", f"color=c={colour}:s=800x800",
             "-frames:v", "1", "-pix_fmt", "rgba", str(path)],
            check=True,
        )
        return path

    return make


def test_refresh_cover_publishes_and_points_the_feed_at_it(published, solid_image):
    from earmark import art

    src = solid_image("logo.png", "blue")
    published.cover = str(src)
    url, detail = published.refresh_cover()
    assert f"/{art.COVER_NAME}?v=" in url
    assert published.state.config.image == url
    assert (published.library.root / art.COVER_NAME).exists()


def test_the_cover_may_be_named_relative_to_the_library(published, solid_image):
    import shutil

    shutil.copy2(solid_image("logo.png", "blue"), published.library.root / "logo.png")
    published.cover = "logo.png"
    url, _ = published.refresh_cover()
    assert url.startswith("https://example.com/em/cover.jpg?v=")


def test_a_config_image_still_wins_over_the_published_one(library):
    """Setting `image` by hand in [feed] must not be silently overwritten."""
    from earmark.config import load

    library.config_path.write_text(
        '[feed]\nbase_url = "https://example.com/em"\n'
        'cover = "logo.png"\n'
        'image = "https://cdn.example.com/mine.png"\n',
        encoding="utf-8",
    )
    cfg = load(library.config_path)
    assert cfg.warnings == []
    feed = Feed.open(library, cfg)
    assert feed.state.config.image == "https://cdn.example.com/mine.png"
    assert feed.refresh_cover() is None


def test_cover_url_is_cache_busted_by_content(published, solid_image):
    """Apps cache artwork by URL, so a changed cover must be a changed URL."""
    published.cover = str(solid_image("a.png", "blue"))
    first, _ = published.refresh_cover()
    published.cover = str(solid_image("a2.png", "blue"))
    again, _ = published.refresh_cover()
    published.cover = str(solid_image("b.png", "green"))
    changed, _ = published.refresh_cover()
    assert "?v=" in first
    assert first == again          # same bytes, same URL: no pointless refetch
    assert changed != first
