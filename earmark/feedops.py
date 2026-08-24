"""Operations on the feed: add, rebuild, prune, check.

Kept separate from :mod:`earmark.feed` (which only renders XML) and
:mod:`earmark.publish` (which only knows the library is a public folder) so
that neither knows about the other.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from earmark import art
from earmark import feed as feed_mod
from earmark import publish as publish_mod
from earmark.library import Library
from earmark.source import slugify

CHANNEL_KEYS = ("title", "description", "author", "link", "language", "category", "image")

# Files in the library root that earmark owns. Anything else there is an orphan.
RESERVED = {feed_mod.FEED_FILE, "episodes.json", "earmark.toml", art.COVER_NAME}


@dataclass
class Feed:
    """One library's episode list, plus the folder it is served from."""

    library: Library
    state: feed_mod.FeedState
    site: publish_mod.Site
    after_publish: str | None = None
    cover: str | None = None

    @classmethod
    def open(cls, library: Library, cfg) -> "Feed":
        state = feed_mod.load(library.state_path)
        # Channel-level settings live in earmark.toml; mirror them into the
        # state so the feed can still be rebuilt if the config is lost.
        for key in CHANNEL_KEYS:
            if cfg.feed.get(key):
                setattr(state.config, key, cfg.feed[key])
        return cls(
            library=library,
            state=state,
            site=publish_mod.Site(root=library.root, base_url=cfg.require_base_url()),
            after_publish=cfg.get("after_publish"),
            # A hand-written `image` URL is artwork earmark did not make and must
            # not replace, so it disables the cover pipeline rather than racing it.
            cover=None if cfg.feed.get("image") else cfg.feed.get("cover"),
        )

    # -- writing -----------------------------------------------------------

    def add(self, mp3: Path, meta, seconds: float, description: str = "") -> feed_mod.Episode:
        mp3 = Path(mp3)
        digest = _content_id(mp3)
        filename = _episode_filename(meta.title, mp3)
        episode = feed_mod.Episode(
            id=digest,
            title=meta.title,
            filename=filename,
            bytes=mp3.stat().st_size,
            seconds=seconds,
            published=meta.date or date.today().isoformat(),
            author=meta.author,
            # Only a real URL belongs in the feed; a local path would leak a
            # filesystem layout to every subscriber and links nowhere.
            source=meta.source if _is_url(meta.source) else None,
            description=description or (meta.source if _is_url(meta.source) else ""),
        )
        # Re-publishing the same document replaces its episode rather than
        # accumulating duplicates.
        self.state.episodes = [e for e in self.state.episodes if e.id != digest]
        self.state.episodes.append(episode)
        self.site.put(mp3, episode.name)
        return episode

    def refresh_cover(self) -> tuple[str, str] | None:
        """Normalize the configured cover image and point the feed at it.

        Returns ``(url, detail)``, or ``None`` if no cover is configured.

        A non-compliant ``<itunes:image>`` produces no error anywhere -- the app
        shows its grey placeholder and the feed still validates -- so earmark
        normalizes rather than validates, every time the feed is written.
        """
        if not self.cover:
            return None
        source = Path(self.cover).expanduser()
        if not source.is_absolute():
            source = self.library.root / source
        if not source.is_file():
            raise FileNotFoundError(f"cover image not found: {source}")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / art.COVER_NAME
            art.prepare(source, local, size=art.DEFAULT_SIZE,
                        background=art.DEFAULT_BACKGROUND)
            detail = art.describe(local)
            # Podcast apps cache show artwork by URL and re-check it rarely --
            # Castbox will keep a placeholder for days after the image appears.
            # A content hash in the query string makes a changed cover a
            # different URL, so it is fetched immediately, while the file in the
            # library keeps one name and never orphans an old one.
            stamp = hashlib.sha256(local.read_bytes()).hexdigest()[:8]
            self.site.put(local, art.COVER_NAME)
        url = f"{self.site.url_for(art.COVER_NAME)}?v={stamp}"
        self.state.config.image = url
        return url, detail

    def prune(self, keep: int | None = None, max_bytes: int | None = None) -> list[feed_mod.Episode]:
        ordered = sorted(self.state.episodes, key=lambda e: e.published, reverse=True)
        survivors: list[feed_mod.Episode] = []
        running = 0
        for i, episode in enumerate(ordered):
            if keep is not None and i >= keep:
                break
            if max_bytes is not None and running + episode.bytes > max_bytes:
                break
            running += episode.bytes
            survivors.append(episode)
        dropped = [e for e in ordered if e not in survivors]
        for episode in dropped:
            self.site.remove(episode.name)
        self.state.episodes = survivors
        return dropped

    def write(self) -> str:
        """Render feed.xml into the library, save state, run the hook."""
        xml = feed_mod.build(self.state, self.site.url_for)
        self.library.feed_path.write_bytes(xml)
        self.save()
        self.site.finish(self.after_publish)
        return self.url

    def save(self) -> None:
        feed_mod.save(self.state, self.library.state_path)

    # -- reading -----------------------------------------------------------

    @property
    def url(self) -> str:
        return self.site.url_for(feed_mod.FEED_FILE)

    def total_bytes(self) -> int:
        return sum(e.bytes for e in self.state.episodes)

    def orphans(self) -> list[str]:
        """Published files in the library root the manifest no longer lists."""
        known = {e.name for e in self.state.episodes} | RESERVED
        return sorted(n for n in self.site.list_names() if n not in known)

    def drop_orphans(self) -> list[str]:
        orphans = self.orphans()
        for name in orphans:
            self.site.remove(name)
        return orphans

    def check(self) -> list[tuple[str, bool, str]]:
        """HEAD the feed and the newest episodes to prove the URLs really work."""
        newest = sorted(self.state.episodes, key=lambda e: e.published, reverse=True)
        urls = [self.url]
        # The cover is the one asset that fails silently in a podcast app -- a
        # broken URL shows a grey placeholder, not an error -- so check it. Use
        # the configured URL rather than url_for(COVER_NAME): the image may be
        # hosted somewhere else entirely.
        if self.state.config.image:
            urls.append(self.state.config.image)
        urls += [self.site.url_for(e.name) for e in newest[:3]]
        return [(url, *publish_mod.check_url(url)) for url in urls]


def _is_url(value: str | None) -> bool:
    return bool(value) and value.startswith(("http://", "https://"))


def _content_id(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()[:16]


def _episode_filename(title: str, mp3: Path) -> str:
    """The published name of an episode.

    The slug and nothing else. ``convert`` already wrote ``audio/<slug>.mp3``,
    and if publishing renamed it the two commands would disagree about where a
    document's audio lives. Re-publishing therefore overwrites in place; the
    content digest still distinguishes episodes, as the feed's guid.
    """
    if mp3.parent.name == "audio":
        return mp3.name
    return f"{slugify(title, max_len=50)}.mp3"


def parse_size(text: str) -> int:
    """Parse '800MB', '2GB', '1500000' into bytes."""
    m = re.fullmatch(r"\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*", text)
    if not m:
        raise ValueError(f"could not read a size from {text!r}; try something like 800MB")
    scale = {"": 1, "k": 10**3, "m": 10**6, "g": 10**9}[m.group(2).lower()]
    return int(float(m.group(1)) * scale)
