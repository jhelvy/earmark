"""The podcast feed.

``episodes.json`` is the source of truth and ``feed.xml`` is always rebuilt
from it -- the XML is never parsed back. That keeps the feed reproducible and
makes prune, retitle and re-host operations trivial.

Hand-written with ElementTree rather than feedgen: the podcast RSS shape is
small and fixed, and feedgen is sdist-only and pulls lxml.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
FEED_FILE = "feed.xml"
AUDIO_PREFIX = "audio"


@dataclass
class Episode:
    id: str
    title: str
    filename: str
    bytes: int
    seconds: float
    published: str
    author: str | None = None
    source: str | None = None
    description: str = ""

    @property
    def name(self) -> str:
        return f"{AUDIO_PREFIX}/{self.filename}"


@dataclass
class FeedConfig:
    title: str = "earmark"
    description: str = "Things I meant to read."
    author: str = "earmark"
    link: str = ""
    language: str = "en-us"
    category: str = "Education"
    image: str | None = None
    explicit: bool = False


@dataclass
class FeedState:
    config: FeedConfig = field(default_factory=FeedConfig)
    episodes: list[Episode] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {"config": asdict(self.config), "episodes": [asdict(e) for e in self.episodes]},
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "FeedState":
        raw = json.loads(text)
        return cls(
            config=FeedConfig(**raw.get("config", {})),
            episodes=[Episode(**e) for e in raw.get("episodes", [])],
        )


def load(path: Path) -> FeedState:
    if not Path(path).exists():
        return FeedState()
    return FeedState.from_json(Path(path).read_text(encoding="utf-8"))


def save(state: FeedState, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.to_json(), encoding="utf-8")


def _duration(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 3600:d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def _rfc2822(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def build(state: FeedState, url_for) -> bytes:
    """Render feed.xml. ``url_for(name)`` maps a stored name to a public URL."""
    ET.register_namespace("itunes", ITUNES)
    ET.register_namespace("atom", ATOM)

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    cfg = state.config

    ET.SubElement(channel, "title").text = cfg.title
    ET.SubElement(channel, "description").text = cfg.description
    # <link> is the show's page, not the feed: pointing it at feed.xml is what
    # <atom:link rel="self"> below already does. With no site of your own, the
    # directory the episodes live in is the closest honest answer.
    ET.SubElement(channel, "link").text = cfg.link or url_for("").rstrip("/")
    ET.SubElement(channel, "language").text = cfg.language
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(
        datetime.now(timezone.utc)
    )
    ET.SubElement(channel, "generator").text = "earmark"
    # A self link is required for a feed to validate and for some apps to
    # follow redirects correctly.
    ET.SubElement(
        channel,
        f"{{{ATOM}}}link",
        {"rel": "self", "type": "application/rss+xml", "href": url_for(FEED_FILE)},
    )
    ET.SubElement(channel, f"{{{ITUNES}}}author").text = cfg.author
    ET.SubElement(channel, f"{{{ITUNES}}}summary").text = cfg.description
    ET.SubElement(channel, f"{{{ITUNES}}}explicit").text = "false" if not cfg.explicit else "true"
    ET.SubElement(channel, f"{{{ITUNES}}}category", {"text": cfg.category})
    owner = ET.SubElement(channel, f"{{{ITUNES}}}owner")
    ET.SubElement(owner, f"{{{ITUNES}}}name").text = cfg.author
    if cfg.image:
        # Both spellings. <itunes:image> is what podcast apps read, but the
        # plain RSS <image> is what feed validators and a few older readers
        # look for, and it costs three lines.
        ET.SubElement(channel, f"{{{ITUNES}}}image", {"href": cfg.image})
        image = ET.SubElement(channel, "image")
        ET.SubElement(image, "url").text = cfg.image
        ET.SubElement(image, "title").text = cfg.title
        ET.SubElement(image, "link").text = cfg.link or url_for("").rstrip("/")

    for episode in sorted(state.episodes, key=lambda e: e.published, reverse=True):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = episode.title
        ET.SubElement(item, "description").text = episode.description or episode.source or ""
        guid = ET.SubElement(item, "guid", {"isPermaLink": "false"})
        guid.text = episode.id
        ET.SubElement(item, "pubDate").text = _rfc2822(episode.published)
        ET.SubElement(
            item,
            "enclosure",
            {
                "url": url_for(episode.name),
                # Taken from the file on disk, never estimated: a wrong length
                # is what makes an episode show as zero-length in a player.
                "length": str(episode.bytes),
                "type": "audio/mpeg",
            },
        )
        ET.SubElement(item, f"{{{ITUNES}}}duration").text = _duration(episode.seconds)
        if episode.author:
            ET.SubElement(item, f"{{{ITUNES}}}author").text = episode.author
        if episode.source and episode.source.startswith(("http://", "https://")):
            ET.SubElement(item, "link").text = episode.source

    ET.indent(rss, space="  ")
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="utf-8")
