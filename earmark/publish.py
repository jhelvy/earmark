"""Getting files to a URL a podcast app can fetch.

A podcast feed needs exactly two things from a host: somewhere to put bytes,
and a public URL for those bytes. Everything else -- accounts, sync clients,
buckets, git -- is a detail of one particular service, so it stays out of the
code and lives in the README instead.

That gives four publishers, and between them there is very little you cannot
publish to:

``folder``   copy into a directory. Whatever syncs that directory to the web
             does the rest: pCloud, Dropbox, iCloud Drive, Syncthing, a mounted
             WebDAV share, an nginx docroot on your own box.
``rclone``   shell out to rclone, which speaks S3, Cloudflare R2, Backblaze B2,
             Google Drive, Dropbox, WebDAV, SFTP and sixty-odd others.
``command``  run a command template of your own. scp, aws-cli, a shell script.
``github``   commit and push to a repo published with GitHub Pages, for people
             who have no storage but do have a GitHub account.

Adding a service almost never means adding code here. It means adding a recipe
to the README.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote


@runtime_checkable
class Publisher(Protocol):
    name: str

    def put(self, local: Path, name: str) -> None: ...

    def remove(self, name: str) -> None: ...

    def url_for(self, name: str) -> str: ...

    # Optional. Publishers that can enumerate what they hold implement this so
    # `earmark feed doctor` can spot files the manifest no longer references --
    # those would otherwise sit there consuming quota forever.
    def list_names(self) -> list[str] | None: ...


def _join(base_url: str, name: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(name)}"


@dataclass
class FolderPublisher:
    """Copy into a directory that something else makes public.

    The generic one. Any sync client or web server that turns a local directory
    into URLs works with this and needs no code of its own.
    """

    folder: Path
    base_url: str
    name: str = "folder"

    def __post_init__(self) -> None:
        self.folder = Path(self.folder).expanduser()

    def put(self, local: Path, name: str) -> None:
        target = self.folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, target)

    def remove(self, name: str) -> None:
        (self.folder / name).unlink(missing_ok=True)

    def url_for(self, name: str) -> str:
        return _join(self.base_url, name)

    def list_names(self) -> list[str] | None:
        if not self.folder.exists():
            return []
        return sorted(
            str(p.relative_to(self.folder))
            for p in self.folder.rglob("*")
            if p.is_file()
        )


@dataclass
class RclonePublisher:
    """Upload with rclone, which already speaks every object store worth using."""

    remote: str
    base_url: str
    name: str = "rclone"
    exe: str = "rclone"
    extra_args: tuple[str, ...] = ()

    def _run(self, *args: str) -> None:
        exe = shutil.which(self.exe)
        if not exe:
            raise RuntimeError(
                "rclone is required for the 'rclone' publisher but was not found; "
                "install it with: brew install rclone"
            )
        result = subprocess.run(
            [exe, *args, *self.extra_args], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"rclone failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else result.returncode}")

    def put(self, local: Path, name: str) -> None:
        self._run("copyto", str(local), f"{self.remote.rstrip('/')}/{name}")

    def remove(self, name: str) -> None:
        self._run("deletefile", f"{self.remote.rstrip('/')}/{name}")

    def url_for(self, name: str) -> str:
        return _join(self.base_url, name)

    def list_names(self) -> list[str] | None:
        exe = shutil.which(self.exe)
        if not exe:
            return None
        result = subprocess.run(
            [exe, "lsf", "-R", "--files-only", self.remote],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        return sorted(line for line in result.stdout.splitlines() if line.strip())


@dataclass
class CommandPublisher:
    """Run a command of your own. The escape hatch for anything else.

    ``{local}`` and ``{name}`` are substituted. Example::

        command = "scp {local} me@example.com:/srv/earmark/{name}"
    """

    command: str
    base_url: str
    name: str = "command"
    remove_command: str | None = None

    def _run(self, template: str, **fields) -> None:
        import shlex

        argv = [part.format(**fields) for part in shlex.split(template)]
        result = subprocess.run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"publish command failed ({' '.join(argv)}): {result.stderr.strip()}"
            )

    def put(self, local: Path, name: str) -> None:
        self._run(self.command, local=str(local), name=name)

    def remove(self, name: str) -> None:
        if self.remove_command:
            self._run(self.remove_command, name=name, local="")

    def url_for(self, name: str) -> str:
        return _join(self.base_url, name)

    def list_names(self) -> list[str] | None:
        # An arbitrary command cannot be asked what it holds.
        return None


@dataclass
class GitHubPagesPublisher:
    """Commit into a repo served by GitHub Pages.

    Free and needs no storage account, at the cost of a 1 GB published-site
    limit and a 100 MiB per-file hard limit. Because git keeps deleted blobs
    forever, ``squash`` rewrites the branch as a single commit on every push so
    the repo tracks the size of the current site rather than its whole history.
    """

    repo: Path
    base_url: str
    branch: str = "main"
    subdir: str = "docs"
    squash: bool = True
    name: str = "github"

    MAX_FILE_BYTES = 95 * 1024 * 1024

    def __post_init__(self) -> None:
        self.repo = Path(self.repo).expanduser()

    @property
    def root(self) -> Path:
        return self.repo / self.subdir if self.subdir else self.repo

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args], capture_output=True, text=True
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result

    def put(self, local: Path, name: str) -> None:
        size = local.stat().st_size
        if size > self.MAX_FILE_BYTES:
            raise RuntimeError(
                f"{name} is {size / 1e6:.0f} MB; GitHub rejects files over 100 MB. "
                "Split it, lower --bitrate, or use a different publisher."
            )
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local, target)

    def remove(self, name: str) -> None:
        (self.root / name).unlink(missing_ok=True)

    def url_for(self, name: str) -> str:
        return _join(self.base_url, name)

    def list_names(self) -> list[str] | None:
        if not self.root.exists():
            return []
        return sorted(
            str(p.relative_to(self.root))
            for p in self.root.rglob("*")
            if p.is_file() and ".git" not in p.parts
        )

    def finish(self, message: str = "earmark: publish") -> None:
        """Commit and push. Called once after a batch of puts and removes."""
        self._git("add", "-A")
        if not self._git("status", "--porcelain").stdout.strip():
            return
        if self.squash:
            # An orphan commit each time: the repo stays the size of the site.
            self._git("checkout", "--orphan", "_earmark_tmp")
            self._git("add", "-A")
            self._git("commit", "-q", "-m", message)
            self._git("branch", "-M", self.branch)
            self._git("push", "-q", "--force", "origin", self.branch)
        else:
            self._git("commit", "-q", "-m", message)
            self._git("push", "-q", "origin", self.branch)


def from_config(feed: dict) -> Publisher:
    """Build the configured publisher from the ``[feed]`` config table."""
    kind = feed.get("publisher", "folder")
    base_url = feed.get("base_url")
    if not base_url:
        raise ValueError(
            "feed.base_url is not set; it is the public URL your files appear at. "
            "Run: earmark feed init --help"
        )

    if kind == "folder":
        folder = feed.get("folder")
        if not folder:
            raise ValueError("feed.folder is required for the 'folder' publisher")
        return FolderPublisher(folder=Path(folder), base_url=base_url)
    if kind == "rclone":
        remote = feed.get("remote")
        if not remote:
            raise ValueError("feed.remote is required for the 'rclone' publisher")
        return RclonePublisher(
            remote=remote, base_url=base_url,
            extra_args=tuple(feed.get("rclone_args", [])),
        )
    if kind == "command":
        command = feed.get("command")
        if not command:
            raise ValueError("feed.command is required for the 'command' publisher")
        return CommandPublisher(
            command=command, base_url=base_url,
            remove_command=feed.get("remove_command"),
        )
    if kind == "github":
        repo = feed.get("repo")
        if not repo:
            raise ValueError("feed.repo is required for the 'github' publisher")
        return GitHubPagesPublisher(
            repo=Path(repo), base_url=base_url,
            branch=feed.get("branch", "main"),
            subdir=feed.get("subdir", "docs"),
            squash=bool(feed.get("squash", True)),
        )
    raise ValueError(
        f"unknown publisher {kind!r}; expected folder, rclone, command or github"
    )


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
