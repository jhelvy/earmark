"""Command line interface.

The ergonomic goal is that ``earmark paper.pdf`` just works, so before argparse
sees anything we splice in the implicit ``read`` subcommand.
"""

from __future__ import annotations

import argparse
import sys

from earmark import __version__

SUBCOMMANDS = {"read", "text", "voices", "models", "cache", "feed", "config"}

EPILOG = """\
examples:
  earmark paper.pdf                     -> ./paper.mp3
  earmark https://example.com/article   -> ./article-title.mp3
  earmark text paper.pdf                print the cleaned speech text
"""


def _add_clean_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("cleaning")
    g.add_argument(
        "--profile",
        choices=["article", "paper", "book"],
        default=None,
        help="preset bundle of cleaning rules (default: article)",
    )
    g.add_argument(
        "--tables",
        choices=["drop", "describe"],
        default=None,
        help="what to do with tables (default: drop)",
    )
    g.add_argument("--keep-references", action="store_true", help="don't cut the References section")
    g.add_argument("--keep-citations", action="store_true", help="don't strip [12] and (Smith et al., 2020)")
    g.add_argument("--keep-links", action="store_true", help="read URLs aloud (you don't want this)")
    g.add_argument("--say-code", action="store_true", help="say 'Code block omitted' instead of skipping silently")
    g.add_argument("--drop-sections", default=None, metavar="LIST", help="comma-separated extra headings to cut")
    g.add_argument("--skip-front-matter", dest="skip_front_matter", action="store_true", default=None,
                   help="cut everything before the abstract (default in --profile paper)")
    g.add_argument("--keep-front-matter", dest="skip_front_matter", action="store_false",
                   help="narrate the title page, authors and affiliations")


def _add_meta_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("metadata")
    g.add_argument("--title", default=None, help="override the detected title")
    g.add_argument("--author", default=None, help="override the detected author")
    g.add_argument("--date", default=None, metavar="YYYY-MM-DD", help="override the detected date")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="earmark",
        description="Turn any document or article into an MP3 you can listen to.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"earmark {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    read = sub.add_parser("read", help="make an MP3 (the default; 'read' is optional)")
    read.add_argument("source", metavar="SOURCE", help="a file path or a URL")
    out = read.add_argument_group("output")
    out.add_argument("-o", "--out", default=None, help="output MP3 (default: ./<title-slug>.mp3)")
    out.add_argument("--bitrate", default=None, help="MP3 bitrate (default: 64k)")
    out.add_argument("--sample-rate", type=int, default=None, help="output sample rate (default: 44100)")
    out.add_argument("--no-title-card", dest="title_card", action="store_false",
                     help="don't speak the title and author first")
    voice = read.add_argument_group("voice")
    voice.add_argument("-v", "--voice", default=None, help="see `earmark voices` (default: af_heart)")
    voice.add_argument("-s", "--speed", type=float, default=None, help="0.5-2.0 (default: 1.0)")
    voice.add_argument("--lang", default=None, help="language code (default: en-us)")
    voice.add_argument("--model", choices=["full", "fp16", "int8"], default=None,
                       help="Kokoro model variant (default: full)")
    voice.add_argument("--engine", choices=["kokoro", "say"], default=None,
                       help="speech backend (default: kokoro)")
    _add_meta_args(read)
    _add_clean_args(read)
    behaviour = read.add_argument_group("behaviour")
    behaviour.add_argument("--dry-run", action="store_true",
                           help="report chunk count and estimated duration, synthesize nothing")
    behaviour.add_argument("--play", action="store_true", help="open the file when it is done")
    behaviour.add_argument("-q", "--quiet", action="store_true", help="no progress bar")
    behaviour.add_argument("--no-cache", dest="use_cache", action="store_false",
                           help="ignore and don't write the chunk cache")
    behaviour.add_argument("--refresh", action="store_true",
                           help="re-synthesize everything, then repopulate the cache")
    out.add_argument("--publish", action="store_true", help="also add the episode to your feed")
    out.add_argument("--album", default=None, help="ID3 album (default: earmark)")
    out.add_argument("--cover", default=None, help="cover art JPEG or PNG")

    voices = sub.add_parser("voices", help="list available voices, or hear one")
    voices.add_argument("--engine", choices=["kokoro", "say"], default="kokoro")
    voices.add_argument("--lang", default=None, metavar="CODE",
                        help="only this language, by name prefix: a, b, e, f, h, i, j, p, z")
    voices.add_argument("--all", action="store_true",
                        help="include voices Kokoro grades D or worse")
    voices.add_argument("--try", dest="try_voice", default=None, metavar="VOICE",
                        help="synthesize a sample in this voice and play it")
    voices.add_argument("--text", default=None, help="what --try should say")
    voices.add_argument("-q", "--quiet", action="store_true", help="just the names, one per line")

    models_p = sub.add_parser("models", help="download / locate / remove the Kokoro model files")
    models_sub = models_p.add_subparsers(dest="action", metavar="ACTION")
    dl = models_sub.add_parser("download", help="fetch the model files (~354 MB)")
    dl.add_argument("--model", choices=["full", "fp16", "int8"], default="full")
    models_sub.add_parser("path", help="print where the model files live")
    rm = models_sub.add_parser("remove", help="delete downloaded model files")
    rm.add_argument("--model", choices=["full", "fp16", "int8"], default=None)

    text = sub.add_parser("text", help="print the cleaned speech text and exit")
    text.add_argument("source", metavar="SOURCE", help="a file path or a URL")
    text.add_argument("--blocks", action="store_true", help="show block kinds and levels")
    text.add_argument("--raw", action="store_true", help="print the extracted Markdown, before cleaning")
    _add_meta_args(text)
    _add_clean_args(text)

    cache_p = sub.add_parser("cache", help="inspect or clear the synthesis cache")
    cache_sub = cache_p.add_subparsers(dest="action", metavar="ACTION")
    cache_sub.add_parser("info", help="entry count and size")
    clear = cache_sub.add_parser("clear", help="delete cached chunks")
    clear.add_argument("--older-than", type=float, default=None, metavar="DAYS",
                       help="only delete entries unused for this many days")

    feed_p = sub.add_parser("feed", help="manage your podcast feed")
    feed_sub = feed_p.add_subparsers(dest="action", metavar="ACTION")
    init = feed_sub.add_parser("init", help="write the [feed] section of your config")
    init.add_argument("--publisher", choices=["folder", "rclone", "command", "github"],
                      default="folder", help="how files reach the web (default: folder)")
    init.add_argument("--base-url", required=True, help="the public URL your files appear at")
    init.add_argument("--title", default="earmark", help="podcast title")
    init.add_argument("--author", default=None, help="podcast author")
    init.add_argument("--description", default=None, help="podcast description")
    init.add_argument("--folder", default=None, help="folder publisher: the directory to copy into")
    init.add_argument("--remote", default=None, help="rclone publisher: e.g. r2:my-bucket/earmark")
    # dest must not be "command": that is the top-level subcommand's dest, and a
    # nested subparser copies its whole namespace over the parent's.
    init.add_argument("--command", dest="command_template", default=None,
                      help="command publisher: template using {local} and {name}")
    init.add_argument("--repo", default=None, help="github publisher: path to the local clone")
    cover = feed_sub.add_parser("cover", help="set the show artwork your podcast app displays")
    cover.add_argument("image", nargs="?", default=None,
                       help="a PNG or JPEG; omit to print the current cover URL")
    cover.add_argument("--size", type=int, default=None, metavar="PX",
                       help="square size to produce (default: 3000)")
    cover.add_argument("--background", default=None, metavar="COLOR",
                       help="what to flatten transparency onto (default: white)")
    feed_sub.add_parser("list", help="show published episodes")
    feed_sub.add_parser("rebuild", help="regenerate and re-upload feed.xml")
    feed_sub.add_parser("url", help="print the feed URL to paste into your podcast app")
    feed_sub.add_parser("doctor", help="check that the published URLs actually serve")
    prune = feed_sub.add_parser("prune", help="remove old episodes")
    prune.add_argument("--keep", type=int, default=None, help="keep this many newest episodes")
    prune.add_argument("--max-size", default=None, metavar="SIZE",
                       help="keep newest episodes under this total, e.g. 800MB")
    prune.add_argument("--orphans", action="store_true",
                       help="also delete published files the feed no longer lists")

    config_p = sub.add_parser("config", help="show, create or edit your config file")
    config_sub = config_p.add_subparsers(dest="action", metavar="ACTION")
    config_sub.add_parser("path", help="print the config file path (the default)")
    cfg_init = config_sub.add_parser("init", help="write a commented starter config")
    cfg_init.add_argument("--force", action="store_true", help="overwrite an existing file")
    config_sub.add_parser("edit", help="open the config in $EDITOR")
    config_sub.add_parser("show", help="print the settings in effect, and any problems")
    return parser


def _clean_options(args, cfg=None):
    from earmark import config as config_mod
    from earmark.clean import options_for

    cfg = cfg if cfg is not None else _load_config()
    profile = args.profile or cfg.get("profile")
    drop_sections = tuple(
        s.strip().lower() for s in (args.drop_sections or "").split(",") if s.strip()
    )
    return options_for(
        profile,
        tables=args.tables,
        drop_references=False if args.keep_references else None,
        drop_citations=False if args.keep_citations else None,
        drop_author_year=False if args.keep_citations else None,
        drop_links=False if args.keep_links else None,
        say_code=True if args.say_code else None,
        drop_sections=drop_sections or None,
        skip_front_matter=args.skip_front_matter,
        replace=cfg.replace or None,
    )


def cmd_text(args) -> int:
    from earmark.clean import clean, render
    from earmark.extract import extract

    cfg = _load_config()
    doc = extract(args.source, title=args.title, author=args.author, date=args.date)
    if args.raw:
        print(doc.markdown)
        return 0

    blocks = clean(doc.markdown, _clean_options(args, cfg))
    header = f"# {doc.meta.title}"
    if doc.meta.author:
        header += f"\n# by {doc.meta.author}"
    print(header + "\n", file=sys.stderr)

    if args.blocks:
        for b in blocks:
            tag = f"{b.kind}{b.level or ''}"
            print(f"[{tag:<8}] {b.text}")
    else:
        print(render(blocks))
    return 0


def _load_config():
    """Load the config, report any problems, and refuse to run on a bad value.

    A setting that is silently ignored is the worst outcome: the user edits the
    file, nothing changes, and there is nothing to read. Typos warn; values that
    cannot be used stop the run and name themselves.
    """
    from earmark import config as config_mod

    cfg = config_mod.load()
    _report_config(cfg)
    cfg.check()
    return cfg


def _setting(args, cfg, name, default=None):
    value = getattr(args, name, None)
    return value if value is not None else cfg.get(name, default)


def cmd_read(args) -> int:
    from pathlib import Path

    from earmark import audio, config as config_mod, pipeline
    from earmark.audio import format_duration
    from earmark.chunk import estimated_seconds
    from earmark.source import default_output
    from earmark.tts import get_backend

    cfg = _load_config()
    opts = _clean_options(args, cfg)
    meta_kw = dict(title=args.title, author=args.author, date=args.date)

    if args.dry_run:
        chunks, meta, seconds = pipeline.dry_run(
            args.source, opts, title_card=args.title_card, **meta_kw
        )
        chars = sum(len(c.text) for c in chunks)
        print(f"{meta.title}")
        if meta.author:
            print(f"by {meta.author}")
        print(f"{len(chunks)} chunks, {chars:,} characters, about {format_duration(seconds)}")
        return 0

    audio.require_ffmpeg()
    engine = _setting(args, cfg, "engine", "kokoro")
    backend = get_backend(engine, variant=_setting(args, cfg, "model", "full"))
    voice = _setting(args, cfg, "voice", "af_heart")
    speed = float(_setting(args, cfg, "speed", 1.0))

    out_path = Path(args.out) if args.out else None
    progress = _Progress(quiet=args.quiet)

    def on_start(chunks, meta):
        nonlocal out_path
        if out_path is None:
            out_path = default_output(meta.title, args.source, cfg.get("output_dir"))
        progress.start(chunks, meta, out_path, estimated_seconds(chunks))

    with progress:
        result = pipeline.render(
            args.source,
            out_path or Path("earmark-output.mp3"),
            opts,
            backend,
            voice=voice,
            speed=speed,
            lang=_setting(args, cfg, "lang", "en-us"),
            bitrate=_setting(args, cfg, "bitrate", audio.DEFAULT_BITRATE),
            sample_rate=int(_setting(args, cfg, "sample_rate", audio.DEFAULT_SAMPLE_RATE)),
            on_start=on_start,
            on_chunk=progress.advance,
            use_cache=args.use_cache,
            refresh=args.refresh,
            album=args.album,
            cover=Path(args.cover) if args.cover else None,
            **meta_kw,
        )

    size_mb = result.path.stat().st_size / 1e6
    print(f"{result.path}  ({format_duration(result.seconds)}, {size_mb:.1f} MB)")

    if args.publish:
        from earmark.feedops import Library

        library = Library.open(cfg.feed)
        episode = library.add(
            result.path, result.meta, result.seconds, description=result.excerpt
        )
        url = library.publish_feed()
        library.save()
        print(f"published {episode.filename}")
        print(f"feed: {url}")
    if args.play:
        import subprocess

        subprocess.run(["open", str(result.path)], check=False)
    return 0


class _Progress:
    """Chunk progress with a realtime-factor readout."""

    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self._bar = None
        self._task = None
        self._audio_seconds = 0.0
        self._cached = 0
        self._t0 = None

    def start(self, chunks, meta, out_path, estimate) -> None:
        from earmark.audio import format_duration

        if self.quiet:
            return
        print(f"{meta.title}", file=sys.stderr)
        if meta.author:
            print(f"by {meta.author}", file=sys.stderr)
        print(
            f"{len(chunks)} chunks, about {format_duration(estimate)} -> {out_path}",
            file=sys.stderr,
        )
        import time

        from rich.progress import (
            BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeRemainingColumn,
        )

        self._t0 = time.monotonic()
        self._bar = Progress(
            TextColumn("[bold]synthesizing"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("{task.fields[rtf]}"),
            TimeRemainingColumn(),
            transient=True,
        )
        self._bar.start()
        self._task = self._bar.add_task("", total=len(chunks), rtf="")

    def advance(self, index: int, seconds: float, cached: bool = False) -> None:
        if cached:
            self._cached += 1
        if self._bar is None:
            return
        import time

        self._audio_seconds += seconds
        elapsed = max(time.monotonic() - self._t0, 1e-6)
        label = f"{self._audio_seconds / elapsed:5.1f}x realtime"
        if self._cached:
            label += f"  ({self._cached} cached)"
        self._bar.update(self._task, advance=1, rtf=label)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._bar is not None:
            self._bar.stop()
        return False


# Kokoro's own grades run A to F+; below this the voice is a curiosity, not a
# thing to listen to a paper in.
POOR_GRADES = {"D+", "D", "D-", "F+", "F"}


def cmd_voices(args) -> int:
    from earmark.tts import catalog, get_backend

    backend = get_backend(args.engine)
    available = backend.voices()

    if args.try_voice:
        return _try_voice(backend, args.try_voice, available, args.text)

    if args.lang:
        available = [v for v in available if v.startswith(args.lang.lower()[:1])]
        if not available:
            raise ValueError(f"no voices for language prefix {args.lang!r}")

    if args.quiet:
        for voice in sorted(available, key=catalog.sort_key):
            print(voice)
        return 0

    hidden = 0
    for language, voices in catalog.group(available).items():
        shown = [v for v in voices if args.all or catalog.grade_of(v) not in POOR_GRADES]
        hidden += len(voices) - len(shown)
        if not shown:
            continue
        print(f"\n{language}")
        for voice in shown:
            grade = catalog.grade_of(voice) or "-"
            marks = " (default)" if voice == catalog.DEFAULT_VOICE else ""
            row = f"  {voice:<16}{grade:<4}{catalog.gender_of(voice)}{marks}"
            print(row.rstrip())

    if hidden:
        print(f"\n{hidden} more graded D or worse; --all to see them")
    print("\nGrades are Kokoro's own. Hear one:  earmark voices --try af_bella")
    return 0


def _try_voice(backend, voice: str, available: list[str], text: str | None) -> int:
    """Synthesize a few seconds in one voice and play it.

    Reading the grade table tells you less than three seconds of your own text
    does, and the model is already on disk.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    from earmark import audio
    from earmark.tts import catalog

    if voice not in available:
        raise ValueError(f"unknown voice {voice!r}; see: earmark voices")
    audio.require_ffmpeg()

    said = text or catalog.SAMPLE_TEXT
    out = Path(tempfile.gettempdir()) / f"earmark-sample-{voice}.mp3"
    samples = backend.synth(said, voice=voice, speed=1.0, lang="en-us")
    audio.encode(iter([samples]), out, input_rate=backend.sample_rate)
    print(f"{voice}  {catalog.grade_of(voice) or '-'}  -> {out}")
    subprocess.run(["open", str(out)], check=False)
    return 0


def cmd_models(args) -> int:
    from earmark import models
    from earmark.paths import models_dir

    action = getattr(args, "action", None) or "path"
    if action == "path":
        print(models_dir())
        for variant in models.MODELS:
            path = models.model_path(variant)
            if path.exists():
                print(f"  {path.name}  {path.stat().st_size / 1e6:.0f} MB")
        voices = models.voices_path()
        if voices.exists():
            print(f"  {voices.name}  {voices.stat().st_size / 1e6:.0f} MB")
        return 0
    if action == "remove":
        removed = models.remove(args.model)
        for path in removed:
            print(f"removed {path}")
        if not removed:
            print("nothing to remove")
        return 0

    from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

    with Progress(
        TextColumn("[bold]{task.description}"), BarColumn(), DownloadColumn(), TransferSpeedColumn()
    ) as bar:
        def make(name, total, done):
            task = bar.add_task(name, total=total, completed=done)
            return lambda n: bar.update(task, advance=n)

        model, voices = models.ensure(args.model, progress=make)
    print(f"{model}\n{voices}")
    return 0


def cmd_config(args) -> int:
    import os
    import subprocess

    from earmark import config as config_mod
    from earmark.paths import config_path

    action = getattr(args, "action", None) or "path"
    path = config_path()

    if action == "init":
        path, written = config_mod.init(path, force=args.force)
        if not written:
            print(f"{path} already exists; use --force to overwrite", file=sys.stderr)
            return 1
        print(f"wrote {path}")
        return 0

    if action == "edit":
        if not path.exists():
            config_mod.init(path)
            print(f"created {path}", file=sys.stderr)
        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
        return subprocess.run([*editor.split(), str(path)], check=False).returncode

    if action == "show":
        cfg = config_mod.load(path)
        if not path.exists():
            print(f"{path} does not exist; these are the built-in defaults", file=sys.stderr)
        for key in config_mod.DEFAULTS:
            value = cfg.get(key)
            source = "config" if cfg.values.get(key) != config_mod.DEFAULTS[key] else "default"
            print(f"{key:<12} {value!r:<12} ({source})")
        if cfg.replace:
            print(f"\n[clean.replace] {len(cfg.replace)} replacement(s)")
            for k, v in sorted(cfg.replace.items()):
                print(f"  {k} -> {v}")
        if cfg.feed:
            print(f"\n[feed] publisher = {cfg.feed.get('publisher', 'folder')!r}")
        _report_config(cfg)
        for error in cfg.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1 if cfg.errors else 0

    print(path)
    if not path.exists():
        print("(does not exist yet; run `earmark config init`)", file=sys.stderr)
    return 0


def _report_config(cfg) -> None:
    """Print config warnings. Errors are left to `check`, which raises them."""
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)


def cmd_cache(args) -> int:
    from earmark import cache
    from earmark.paths import cache_dir

    action = getattr(args, "action", None) or "info"
    if action == "clear":
        removed, freed = cache.clear(args.older_than)
        print(f"removed {removed} entries, freed {freed / 1e6:.1f} MB")
        return 0
    stats = cache.info()
    print(cache_dir())
    print(f"{stats['count']} chunks, {stats['bytes'] / 1e6:.1f} MB")
    return 0


# config key -> argparse dest
FEED_INIT_KEYS = {
    "folder": "folder",
    "remote": "remote",
    "command": "command_template",
    "repo": "repo",
}


def cmd_feed(args) -> int:
    import tomllib
    from pathlib import Path

    from earmark import config as config_mod
    from earmark.feedops import Library, parse_size
    from earmark.paths import config_path

    action = getattr(args, "action", None) or "url"

    if action == "init":
        required = {"folder": "folder", "rclone": "remote", "command": "command", "github": "repo"}
        need = required[args.publisher]
        if not getattr(args, FEED_INIT_KEYS[need], None):
            raise ValueError(f"--{need} is required for the {args.publisher!r} publisher")
        lines = [
            "[feed]",
            f'publisher = "{args.publisher}"',
            f'base_url = "{args.base_url.rstrip("/")}"',
            f'title = "{args.title}"',
        ]
        if args.author:
            lines.append(f'author = "{args.author}"')
        if args.description:
            lines.append(f'description = "{args.description}"')
        for key, dest in FEED_INIT_KEYS.items():
            value = getattr(args, dest, None)
            if value:
                lines.append(f'{key} = "{value}"')
        block = "\n".join(lines) + "\n"

        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        # Parse rather than search for "[feed]": the starter config written by
        # `earmark config init` carries a commented-out [feed] example, and a
        # substring test would treat that as an existing section forever.
        try:
            already = bool(tomllib.loads(existing).get("feed"))
        except tomllib.TOMLDecodeError:
            already = False
        if already:
            print(f"a [feed] section already exists in {path}; edit it directly:\n\n{block}")
            return 1
        with path.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write("\n" + block)
        print(f"wrote [feed] to {path}")
        print(f"feed URL: {args.base_url.rstrip('/')}/feed.xml")
        print("Publish something with:  earmark <source> --publish")
        return 0

    cfg = _load_config()
    if not cfg.feed:
        raise RuntimeError("no [feed] configured; run: earmark feed init --help")
    library = Library.open(cfg.feed)

    if action == "url":
        print(library.url)
        return 0
    if action == "cover":
        if not args.image:
            current = library.state.config.image
            print(current or "no cover set; add one with: earmark feed cover IMAGE")
            return 0 if current else 1
        from earmark import art

        source = Path(args.image).expanduser()
        dims = art.dimensions(source)
        if dims and dims[0] != dims[1]:
            print(f"note: {source.name} is {dims[0]}x{dims[1]}; it will be padded to a "
                  f"square rather than cropped")
        url, detail = library.set_cover(
            source, size=args.size, background=args.background
        )
        library.publish_feed()
        library.save()
        print(f"cover published ({detail})\n{url}")
        print("Podcast apps cache artwork; it can take a while to appear.")
        return 0
    if action == "list":
        episodes = sorted(library.state.episodes, key=lambda e: e.published, reverse=True)
        if not episodes:
            print("no episodes published yet")
            return 0
        from earmark.audio import format_duration

        for e in episodes:
            print(f"{e.published}  {format_duration(e.seconds):>8}  {e.bytes / 1e6:6.1f} MB  {e.title}")
        total = sum(e.seconds for e in episodes)
        print(
            f"\n{len(episodes)} episode{'s' if len(episodes) != 1 else ''}, "
            f"{format_duration(total)}, {library.total_bytes() / 1e6:.1f} MB"
        )
        return 0
    if action == "rebuild":
        print(library.publish_feed())
        library.save()
        return 0
    if action == "prune":
        from earmark.audio import format_duration

        max_bytes = parse_size(args.max_size) if args.max_size else None
        if args.keep is None and max_bytes is None and not args.orphans:
            raise ValueError("give --keep, --max-size or --orphans")
        if args.keep is not None or max_bytes is not None:
            for e in library.prune(keep=args.keep, max_bytes=max_bytes):
                print(f"removed {e.filename}")
        if args.orphans:
            for name in library.drop_orphans():
                print(f"removed orphan {name}")
        library.publish_feed()
        library.save()
        remaining = library.state.episodes
        total = sum(e.seconds for e in remaining)
        print(
            f"{len(remaining)} episode{'s' if len(remaining) != 1 else ''} "
            f"{'remain' if len(remaining) != 1 else 'remains'}, "
            f"{format_duration(total)}, {library.total_bytes() / 1e6:.1f} MB"
        )
        return 0
    if action == "doctor":
        failures = 0
        for url, ok, detail in library.check():
            print(f"{'ok  ' if ok else 'FAIL'}  {url}  ({detail})")
            failures += not ok
        orphans = library.orphans()
        if orphans:
            print(f"\n{len(orphans)} published file(s) the feed no longer lists:")
            for name in orphans[:10]:
                print(f"  {name}")
            print("Remove them with:  earmark feed prune --orphans")
        elif orphans is None:
            print("\n(this publisher cannot list what it holds, so orphans can't be checked)")
        if failures:
            print(
                "\nSomething published is not reachable. Check that base_url points at the "
                "same place your publisher writes to, and that the files are public.",
                file=sys.stderr,
            )
        return 1 if failures else 0
    raise ValueError(f"unknown feed action {action!r}")


HANDLERS = {
    "text": cmd_text,
    "read": cmd_read,
    "config": cmd_config,
    "voices": cmd_voices,
    "models": cmd_models,
    "cache": cmd_cache,
    "feed": cmd_feed,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # "earmark paper.pdf" means "earmark read paper.pdf".
    if argv and argv[0] not in SUBCOMMANDS and not argv[0].startswith("-"):
        argv.insert(0, "read")

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    from earmark.config import ConfigError

    try:
        return HANDLERS[args.command](args)
    except (FileNotFoundError, RuntimeError, ValueError, ConfigError) as exc:
        print(f"earmark: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
