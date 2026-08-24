"""Getting library files to a URL a podcast app can fetch.

A podcast feed needs two things from a host: somewhere to put bytes, and a
public URL for those bytes. In earmark the first one is already answered -- the
library *is* the folder, and whatever syncs it to the web does the rest: pCloud,
Dropbox, iCloud Drive, Syncthing, a mounted WebDAV share, an nginx docroot. So
publishing is not a transfer at all; the MP3 is written where it belongs the
first time, and this module only has to turn a filename into a URL.

Anything that needs a real push -- a git repo behind GitHub Pages, an rclone
remote, an scp -- is one line of shell in the ``after_publish`` config key,
which runs inside the library once the feed is written. That is a config key
instead of a plugin system, and it covers every host without earmark knowing
the name of a single one.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


class PublishError(Exception):
    """Something outside earmark refused to move the bytes."""


@dataclass
class Site:
    """The library, viewed as a public web folder."""

    root: Path
    base_url: str

    def url_for(self, name: str) -> str:
        return f"{self.base_url.rstrip('/')}/{quote(name)}"

    def path_for(self, name: str) -> Path:
        return self.root / name

    def put(self, local: Path, name: str) -> None:
        """Place a file under its published name.

        Files made by ``earmark audio`` are already inside the library under a
        readable name; publishing renames them to the content-addressed name the
        feed uses. A file from outside is copied in.
        """
        import shutil

        local = Path(local)
        target = self.path_for(name)
        if local.resolve() == target.resolve():
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, target)

    def remove(self, name: str) -> None:
        self.path_for(name).unlink(missing_ok=True)

    def list_names(self) -> list[str]:
        """Every published file, named the way the feed names it.

        Root files plus everything under ``audio/``; ``text/`` is the editable
        source, not something the feed ever points at.
        """
        if not self.root.is_dir():
            return []
        names = [p.name for p in self.root.iterdir() if p.is_file()]
        audio = self.root / "audio"
        if audio.is_dir():
            names += [f"audio/{p.name}" for p in audio.iterdir() if p.is_file()]
        return sorted(names)

    def finish(self, command: str | None) -> None:
        """Run the user's ``after_publish`` hook, from inside the library."""
        if not command or not command.strip():
            return
        result = subprocess.run(
            command, shell=True, cwd=self.root, env=os.environ.copy(),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            tail = detail[-1] if detail else f"exit {result.returncode}"
            raise PublishError(f"after_publish failed: {shlex.split(command)[0]}: {tail}")


def check_url(url: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Verify a published URL actually serves. Returns (ok, detail)."""
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
            ctype = resp.headers.get("Content-Type", "?")
            length = resp.headers.get("Content-Length", "?")
            return True, f"HTTP {resp.status}, {ctype}, {length} bytes"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
