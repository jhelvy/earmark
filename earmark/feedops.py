"""Operations on the feed: add, rebuild, prune, check.

Kept separate from :mod:`earmark.feed` (which only renders XML) and
:mod:`earmark.publish` (which only moves bytes) so that neither knows about the
other.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from earmark import feed as feed_mod
from earmark import publish as publish_mod
from earmark import paths
from earmark.source import slugify


def state_path() -> Path:
    return paths.config_dir() / "episodes.json"


@dataclass
class Library:
    state: feed_mod.FeedState
    publisher: publish_mod.Publisher
    path: Path

    @classmethod
    def open(cls, feed_config: dict) -> "Library":
        state = feed_mod.load(state_path())
        # Channel-level settings live in config.toml; mirror them into state so
        # the feed can still be rebuilt if the config moves.
        for key in ("title", "description", "author", "link", "language", "category", "image"):
            if feed_config.get(key):
                setattr(state.config, key, feed_config[key])
        return cls(
            state=state,
            publisher=publish_mod.from_config(feed_config),
            path=state_path(),
        )

    # -- writing -----------------------------------------------------------

    def add(self, mp3: Path, meta, seconds: float, description: str = "") -> feed_mod.Episode:
        mp3 = Path(mp3)
        digest = _content_id(mp3)
        filename = _episode_filename(meta.title, digest)
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
        self.publisher.put(mp3, episode.name)
        return episode

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
            self.publisher.remove(episode.name)
        self.state.episodes = survivors
        return dropped

    def publish_feed(self) -> str:
        """Render feed.xml, upload it, and finalize the publisher."""
        import tempfile

        xml = feed_mod.build(self.state, self.publisher.url_for)
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / feed_mod.FEED_FILE
            local.write_bytes(xml)
            self.publisher.put(local, feed_mod.FEED_FILE)
            # Publish the manifest too, so the feed is recoverable on a new machine.
            manifest = Path(tmp) / "episodes.json"
            manifest.write_text(self.state.to_json(), encoding="utf-8")
            self.publisher.put(manifest, "episodes.json")
        finish = getattr(self.publisher, "finish", None)
        if finish:
            finish()
        return self.url

    def save(self) -> None:
        feed_mod.save(self.state, self.path)

    # -- reading -----------------------------------------------------------

    @property
    def url(self) -> str:
        return self.publisher.url_for(feed_mod.FEED_FILE)

    def total_bytes(self) -> int:
        return sum(e.bytes for e in self.state.episodes)

    def orphans(self) -> list[str] | None:
        """Published files the manifest no longer references.

        ``None`` when the publisher cannot enumerate what it holds.
        """
        lister = getattr(self.publisher, "list_names", None)
        names = lister() if lister else None
        if names is None:
            return None
        known = {e.name for e in self.state.episodes}
        known |= {feed_mod.FEED_FILE, "episodes.json"}
        return sorted(n for n in names if n not in known)

    def drop_orphans(self) -> list[str]:
        orphans = self.orphans() or []
        for name in orphans:
            self.publisher.remove(name)
        return orphans

    def check(self) -> list[tuple[str, bool, str]]:
        """HEAD the feed and the newest episodes to prove the URLs really work."""
        targets = [feed_mod.FEED_FILE]
        newest = sorted(self.state.episodes, key=lambda e: e.published, reverse=True)
        targets += [e.name for e in newest[:3]]
        results = []
        for name in targets:
            url = self.publisher.url_for(name)
            ok, detail = publish_mod.check_url(url)
            results.append((url, ok, detail))
        return results


def _is_url(value: str | None) -> bool:
    return bool(value) and value.startswith(("http://", "https://"))


def _content_id(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()[:16]


def _episode_filename(title: str, digest: str) -> str:
    slug = slugify(title, max_len=50)
    stamp = date.today().isoformat()
    return f"{stamp}-{slug}-{digest[:8]}.mp3"


def parse_size(text: str) -> int:
    """Parse '800MB', '2GB', '1500000' into bytes."""
    m = re.fullmatch(r"\s*([\d.]+)\s*([kKmMgG]?)[bB]?\s*", text)
    if not m:
        raise ValueError(f"could not read a size from {text!r}; try something like 800MB")
    scale = {"": 1, "k": 10**3, "m": 10**6, "g": 10**9}[m.group(2).lower()]
    return int(float(m.group(1)) * scale)
