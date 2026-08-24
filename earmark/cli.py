"""Command line interface.

Seven commands, and three of them are the same pipeline stopped at a different
point: ``read`` makes the Markdown, ``convert`` makes the MP3, ``publish`` puts
it on the feed. Everything lands in the library.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from earmark import __version__

EPILOG = """\
examples:
  earmark init ~/pCloud/public/audio --base-url https://filedn.com/XXXX/audio
  earmark config                        edit this library's settings
  earmark read paper.pdf                -> text/paper-title.md, to edit by hand
  earmark convert paper.pdf             -> audio/paper-title.mp3
  earmark publish https://.../article   make it and put it on your feed
  earmark feed                          what is published, and the feed URL
"""


LIBRARY_HELP = "the library to act on (default: the one you are in)"


def _add_library(p: argparse.ArgumentParser, *, default) -> None:
    """Add ``--library`` so it works on either side of the verb.

    Every parser gets its *own* action rather than sharing one through
    ``parents=``: a subparser writes its defaults over the namespace the parent
    already filled in, so a shared action would make
    ``earmark --library X read f.pdf`` parse fine and then act on the wrong
    library. The top parser's ``None`` seeds the namespace; each subcommand's
    ``SUPPRESS`` means "leave it alone unless the flag was actually given".
    """
    p.add_argument("--library", default=default, metavar="PATH", help=LIBRARY_HELP)


def _sub(sub, name: str, **kw) -> argparse.ArgumentParser:
    p = sub.add_parser(name, **kw)
    _add_library(p, default=argparse.SUPPRESS)
    return p


def _add_meta_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("metadata")
    g.add_argument("--title", default=None, help="override the detected title")
    g.add_argument("--author", default=None, help="override the detected author")
    g.add_argument("--date", default=None, help="override the detected date (YYYY-MM-DD)")


def _add_clean_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("cleaning")
    g.add_argument("--profile", choices=["article", "paper", "book"], default=None,
                   help="preset bundle of cleaning rules (default: article)")
    g.add_argument("--tables", choices=["drop", "describe"], default=None,
                   help="what to do with tables (default: drop)")
    g.add_argument("--keep-references", action="store_true", help="don't cut the References section")
    g.add_argument("--keep-citations", action="store_true",
                   help="don't strip [12] and (Smith et al., 2020)")
    g.add_argument("--keep-links", action="store_true", help="read URLs aloud (you don't want this)")
    g.add_argument("--say-code", action="store_true",
                   help="say 'Code block omitted' instead of skipping silently")
    g.add_argument("--drop-sections", default=None, metavar="LIST",
                   help="comma-separated extra headings to cut")
    g.add_argument("--skip-front-matter", dest="skip_front_matter", action="store_true", default=None,
                   help="cut everything before the abstract (default in --profile paper)")
    g.add_argument("--keep-front-matter", dest="skip_front_matter", action="store_false",
                   help="narrate the title page, authors and affiliations")


def _add_voice_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("voice")
    g.add_argument("-v", "--voice", default=None, help="see `earmark voices` (default: af_heart)")
    g.add_argument("-s", "--speed", type=float, default=None, help="0.5-2.0 (default: 1.0)")
    g.add_argument("--lang", default=None, help="language code (default: en-us)")
    g.add_argument("--model", choices=["full", "fp16", "int8"], default=None,
                   help="Kokoro model variant (default: full)")
    g.add_argument("--engine", choices=["kokoro", "say"], default=None,
                   help="speech backend (default: kokoro)")


def _add_audio_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("audio")
    g.add_argument("--bitrate", default=None, help="MP3 bitrate (default: 64k)")
    g.add_argument("--sample-rate", type=int, default=None, help="output sample rate (default: 44100)")
    g.add_argument("--no-title-card", dest="title_card", action="store_false",
                   help="don't speak the title and author first")
    b = p.add_argument_group("behaviour")
    b.add_argument("--dry-run", action="store_true",
                   help="report chunk count and estimated duration, synthesize nothing")
    b.add_argument("--play", action="store_true", help="open the file when it is done")
    b.add_argument("-q", "--quiet", action="store_true", help="no progress bar")
    b.add_argument("--no-cache", dest="use_cache", action="store_false",
                   help="ignore and don't write the chunk cache")
    b.add_argument("--refresh", action="store_true",
                   help="re-extract and re-synthesize, ignoring what is already in the library")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="earmark",
        description="Turn documents and articles into a podcast feed of your own.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_library(parser, default=None)
    parser.add_argument("--version", action="version", version=f"earmark {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    init = _sub(sub, "init", help="create a library folder")
    init.add_argument("path", nargs="?", default=None, metavar="PATH",
                      help="where the library lives (default: the current folder)")
    init.add_argument("--base-url", default=None,
                      help="the public URL this folder is served at")
    init.add_argument("--title", default="earmark", help="podcast title")
    init.add_argument("--no-default", dest="set_default", action="store_false",
                      help="don't make this the library used outside any library folder")
    init.add_argument("--force", action="store_true", help="overwrite an existing earmark.toml")

    cfg = _sub(sub, "config", help="edit this library's settings")
    cfg.add_argument("--show", action="store_true", help="print the settings in effect and every path")
    cfg.add_argument("--path", dest="show_path", action="store_true", help="print the config file path")

    read = _sub(sub, "read", help="turn a source into Markdown in the library")
    read.add_argument("source", metavar="SOURCE", help="a file path or a URL")
    read.add_argument("--stdout", action="store_true", help="print it instead of writing a file")
    read.add_argument("--raw", action="store_true", help="the extracted Markdown, before cleaning")
    read.add_argument("--force", action="store_true", help="overwrite an existing Markdown file")
    _add_meta_args(read)
    _add_clean_args(read)

    convert = _sub(sub, "convert",
                   help="turn a source or a Markdown file into an MP3 in the library")
    convert.add_argument("source", metavar="SOURCE", help="a file path, a Markdown file, or a URL")
    _add_voice_args(convert)
    _add_audio_args(convert)
    _add_meta_args(convert)
    _add_clean_args(convert)

    pub = _sub(sub, "publish", help="put a source, a Markdown file or an MP3 on your feed")
    pub.add_argument("source", metavar="SOURCE", help="a file path, a Markdown file, an MP3, or a URL")
    _add_voice_args(pub)
    _add_audio_args(pub)
    _add_meta_args(pub)
    _add_clean_args(pub)

    feed = _sub(sub, "feed", help="show, rebuild or trim your feed")
    feed.add_argument("--rebuild", action="store_true",
                      help="rewrite feed.xml and the cover from the current settings")
    feed.add_argument("--check", action="store_true", help="prove the published URLs actually serve")
    feed.add_argument("--prune", action="store_true", help="remove episodes; needs --keep or --max-size")
    feed.add_argument("--keep", type=int, default=None, metavar="N", help="keep this many newest")
    feed.add_argument("--max-size", default=None, metavar="SIZE",
                      help="keep newest episodes under this total, e.g. 800MB")
    feed.add_argument("--orphans", action="store_true",
                      help="with --prune, also delete library files the feed no longer lists")

    voices = _sub(sub, "voices", help="list available voices, or hear one")
    voices.add_argument("--engine", choices=["kokoro", "say"], default="kokoro")
    voices.add_argument("--lang", default=None, metavar="CODE",
                        help="only this language, by name prefix: a, b, e, f, h, i, j, p, z")
    voices.add_argument("--all", action="store_true", help="include voices Kokoro grades D or worse")
    voices.add_argument("--try", dest="try_voice", default=None, metavar="VOICE",
                        help="synthesize a sample in this voice and play it")
    voices.add_argument("--text", default=None, help="what --try should say")
    voices.add_argument("-q", "--quiet", action="store_true", help="just the names, one per line")
    return parser


# ---------------------------------------------------------------- helpers


def _open_library(args, *, must_exist: bool = True):
    """Resolve the library and load its config, reporting any problems."""
    from earmark.config import load
    from earmark.library import Library

    lib = Library.resolve(args.library, must_exist=must_exist)
    cfg = load(lib.config_path)
    for warning in cfg.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    cfg.check()
    return lib, cfg


def _setting(args, cfg, name, default=None):
    value = getattr(args, name, None)
    return value if value is not None else cfg.get(name, default)


def _clean_options(args, cfg):
    from earmark.clean import options_for

    drop = tuple(
        s.strip().lower() for s in (getattr(args, "drop_sections", None) or "").split(",") if s.strip()
    )
    return options_for(
        args.profile or cfg.get("profile"),
        tables=args.tables,
        drop_references=False if args.keep_references else None,
        drop_citations=False if args.keep_citations else None,
        drop_author_year=False if args.keep_citations else None,
        drop_links=False if args.keep_links else None,
        say_code=True if args.say_code else None,
        drop_sections=drop or None,
        skip_front_matter=args.skip_front_matter,
        replace=cfg.replace or None,
    )


def _backend(args, cfg):
    """Build the speech backend, downloading the model if it is not here yet."""
    from earmark import models
    from earmark.tts import get_backend

    engine = _setting(args, cfg, "engine", "kokoro")
    variant = _setting(args, cfg, "model", "full")
    if engine == "kokoro" and not models.is_downloaded(variant):
        _download_model(variant)
    return get_backend(engine, variant=variant)


def _download_model(variant: str) -> None:
    """Confirm and fetch the Kokoro files. They are large and this is the once."""
    from earmark import models

    size = "354 MB" if variant == "full" else "about 100 MB"
    if sys.stdin.isatty() and sys.stderr.isatty():
        print(f"The Kokoro {variant} model is not downloaded yet ({size}).", file=sys.stderr)
        answer = input("Download it now? [Y/n] ").strip().lower()
        if answer and not answer.startswith("y"):
            raise RuntimeError("cannot synthesize without the model")
    else:
        print(f"downloading the Kokoro {variant} model ({size})...", file=sys.stderr)

    from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

    with Progress(
        TextColumn("[bold]{task.description}"), BarColumn(), DownloadColumn(), TransferSpeedColumn()
    ) as bar:
        def make(name, total, done):
            task = bar.add_task(name, total=total, completed=done)
            return lambda n: bar.update(task, advance=n)

        models.ensure(variant, progress=make)


def _load_document(args, cfg, lib):
    from earmark import pipeline

    return pipeline.load(
        args.source,
        _clean_options(args, cfg),
        title=args.title,
        author=args.author,
        date=args.date,
    )


def _slug_for(meta, source: str) -> str:
    from earmark.source import slugify

    return slugify(meta.title) if meta.title and meta.title != "Untitled" else slugify(Path(source).stem)


def _is_audio(source: str) -> bool:
    from earmark.source import is_url

    return not is_url(source) and Path(source).suffix.lower() in {".mp3", ".m4a", ".wav"}


# ---------------------------------------------------------------- commands


def cmd_init(args) -> int:
    from earmark import config as config_mod
    from earmark.library import Library, write_default

    root = Path(args.path).expanduser() if args.path else Path.cwd()
    lib = Library.at(root)
    lib.ensure_dirs()
    path, written = config_mod.init(
        lib.config_path, base_url=args.base_url or "", title=args.title, force=args.force
    )
    if not written:
        print(f"{path} already exists; --force to overwrite", file=sys.stderr)
        return 1

    print(f"library: {lib.root}")
    print(f"  {config_mod.TEMPLATE.splitlines()[0].lstrip('# ')}: {path}")
    if args.set_default:
        write_default(lib.root)
        print("  set as your default library")
    if not args.base_url:
        print("\nNo base_url yet. Publishing needs the public URL this folder is served at:")
        print("  earmark config")
    return 0


def cmd_config(args) -> int:
    import os
    import subprocess

    from earmark import config as config_mod
    from earmark.library import Library

    lib = Library.resolve(args.library, must_exist=not args.show_path)
    if args.show_path:
        print(lib.config_path)
        return 0

    if args.show:
        from earmark import paths

        cfg = config_mod.load(lib.config_path)
        print(f"library      {lib.root}")
        print(f"config       {lib.config_path}")
        print(f"text         {lib.text_dir}")
        print(f"feed         {lib.feed_path}")
        print(f"episodes     {lib.state_path}")
        print(f"models       {paths.models_dir()}")
        print(f"cache        {paths.chunk_cache_dir()}")
        print()
        for key, fallback in config_mod.DEFAULTS.items():
            value = cfg.get(key)
            origin = "config" if cfg.values.get(key) != fallback else "default"
            print(f"{key:<14} {value!r:<14} ({origin})")
        if cfg.feed:
            print()
            for key in config_mod.FEED_KEYS:
                if cfg.feed.get(key):
                    print(f"feed.{key:<9} {cfg.feed[key]!r}")
        if cfg.replace:
            print(f"\n[replace] {len(cfg.replace)} replacement(s)")
            for k, v in sorted(cfg.replace.items()):
                print(f"  {k} -> {v}")
        for warning in cfg.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        for error in cfg.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1 if cfg.errors else 0

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "nano"
    return subprocess.run([*editor.split(), str(lib.config_path)], check=False).returncode


def cmd_read(args) -> int:
    from earmark import pipeline
    from earmark.extract import extract

    lib, cfg = _open_library(args)

    if args.raw:
        doc = extract(args.source, title=args.title, author=args.author, date=args.date)
        print(doc.markdown)
        return 0

    doc = _load_document(args, cfg, lib)
    if args.stdout:
        print(doc.text)
        return 0

    out = lib.markdown_path(_slug_for(doc.meta, args.source))
    if out.exists() and not args.force and not doc.reused:
        print(f"{out} already exists; --force to overwrite", file=sys.stderr)
        return 1
    pipeline.write_markdown(doc, out)
    words = len(doc.text.split())
    print(f"{out}  ({words:,} words)")
    return 0


def _convert(args, cfg, lib, *, quiet: bool = False):
    """Produce (or reuse) the MP3 for a source. Shared by convert and publish."""
    from earmark import audio, cache, pipeline
    from earmark.audio import format_duration

    doc = _load_document(args, cfg, lib)
    slug = _slug_for(doc.meta, args.source)
    out_path = lib.audio_path(slug)

    if args.dry_run:
        chunks, seconds = pipeline.estimate(doc, source=args.source, title_card=args.title_card)
        chars = sum(len(c.text) for c in chunks)
        print(doc.meta.title)
        if doc.meta.author:
            print(f"by {doc.meta.author}")
        print(f"{len(chunks)} chunks, {chars:,} characters, about {format_duration(seconds)}")
        print(f"-> {out_path}")
        return None, doc

    # Keep the Markdown beside the audio, so the next run can reuse or you can edit it.
    md_path = lib.markdown_path(slug)
    if not doc.reused and (args.refresh or not md_path.exists()):
        pipeline.write_markdown(doc, md_path)

    audio.require_ffmpeg()
    backend = _backend(args, cfg)
    progress = _Progress(quiet=quiet or args.quiet)

    def on_start(chunks, meta):
        from earmark.chunk import estimated_seconds

        progress.start(chunks, meta, out_path, estimated_seconds(chunks))

    with progress:
        result = pipeline.render_audio(
            doc,
            out_path,
            backend,
            source=args.source,
            voice=_setting(args, cfg, "voice", "af_heart"),
            speed=float(_setting(args, cfg, "speed", 1.0)),
            lang=_setting(args, cfg, "lang", "en-us"),
            bitrate=_setting(args, cfg, "bitrate", audio.DEFAULT_BITRATE),
            sample_rate=int(_setting(args, cfg, "sample_rate", audio.DEFAULT_SAMPLE_RATE)),
            title_card=args.title_card,
            on_start=on_start,
            on_chunk=progress.advance,
            use_cache=args.use_cache,
            refresh=args.refresh,
            album=cfg.feed.get("title") or "earmark",
            cover=_cover_path(lib, cfg),
        )
    if args.use_cache:
        cache.autoprune()
    return result, doc


def _cover_path(lib, cfg) -> Path | None:
    name = cfg.feed.get("cover")
    if not name:
        return None
    path = Path(name).expanduser()
    if not path.is_absolute():
        path = lib.root / path
    return path if path.is_file() else None


def cmd_convert(args) -> int:
    from earmark.audio import format_duration

    lib, cfg = _open_library(args)
    result, _ = _convert(args, cfg, lib)
    if result is None:
        return 0
    size_mb = result.path.stat().st_size / 1e6
    print(f"{result.path}  ({format_duration(result.seconds)}, {size_mb:.1f} MB)")
    if args.play:
        import subprocess

        subprocess.run(["open", str(result.path)], check=False)
    return 0


def cmd_publish(args) -> int:
    from earmark.audio import format_duration
    from earmark.feedops import Feed

    lib, cfg = _open_library(args)
    cfg.require_base_url()

    if _is_audio(args.source):
        mp3, meta, seconds, description = _adopt_audio(args, lib)
    else:
        result, _ = _convert(args, cfg, lib)
        if result is None:
            return 0
        mp3, meta = result.path, result.meta
        seconds, description = result.seconds, result.excerpt
        size_mb = mp3.stat().st_size / 1e6
        print(f"{mp3}  ({format_duration(seconds)}, {size_mb:.1f} MB)")

    feed = Feed.open(lib, cfg)
    cover = feed.refresh_cover()
    episode = feed.add(mp3, meta, seconds, description=description)
    url = feed.write()
    print(f"published {episode.filename}")
    if cover:
        print(f"cover     {cover[1]}")
    print(f"feed      {url}")
    return 0


def _adopt_audio(args, lib):
    """Take an MP3 that already exists onto the feed, with no synthesis."""
    from earmark import audio, tag
    from earmark.extract.meta import Metadata

    path = Path(args.source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"no such file: {path}")
    existing = tag.summary(path)
    meta = Metadata(
        title=args.title or existing.get("title") or path.stem.replace("-", " "),
        author=args.author or existing.get("author"),
        date=args.date or existing.get("date"),
        source=str(path),
    )
    seconds = audio.probe_duration(path)
    return path, meta, seconds, ""


def cmd_feed(args) -> int:
    from earmark.audio import format_duration
    from earmark.feedops import Feed, parse_size

    lib, cfg = _open_library(args)
    feed = Feed.open(lib, cfg)

    if args.prune:
        if args.keep is None and args.max_size is None and not args.orphans:
            raise ValueError("--prune needs --keep, --max-size or --orphans")
        dropped = feed.prune(args.keep, parse_size(args.max_size) if args.max_size else None)
        for episode in dropped:
            print(f"removed {episode.filename}")
        if args.orphans:
            for name in feed.drop_orphans():
                print(f"removed orphan {name}")
        feed.refresh_cover()
        print(f"feed      {feed.write()}")
        return 0

    if args.rebuild:
        cover = feed.refresh_cover()
        if cover:
            print(f"cover     {cover[1]}")
        print(f"feed      {feed.write()}")
        return 0

    if args.check:
        failures = 0
        for url, ok, detail in feed.check():
            print(f"{'ok  ' if ok else 'FAIL'}  {url}  ({detail})")
            failures += not ok
        orphans = feed.orphans()
        if orphans:
            print(f"\n{len(orphans)} file(s) the feed no longer lists:")
            for name in orphans[:10]:
                print(f"  {name}")
            print("Remove them with:  earmark feed --prune --orphans")
        if failures:
            print(
                "\nSomething published is not reachable. Check that base_url points at the "
                "same place this folder is served from, and that the files are public.",
                file=sys.stderr,
            )
        return 1 if failures else 0

    episodes = sorted(feed.state.episodes, key=lambda e: e.published, reverse=True)
    if not episodes:
        print("nothing published yet.  earmark publish paper.pdf")
    for episode in episodes:
        print(f"{episode.published}  {format_duration(episode.seconds):>8}  "
              f"{episode.bytes / 1e6:6.1f} MB  {episode.title}")
    if episodes:
        print(f"\n{len(episodes)} episode(s), {feed.total_bytes() / 1e6:.0f} MB total")
    print(f"feed      {feed.url}")
    return 0


# Kokoro's own grades run A to F+; below this the voice is a curiosity, not a
# thing to listen to a paper in.
POOR_GRADES = {"D+", "D", "D-", "F+", "F"}


def cmd_voices(args) -> int:
    from earmark.tts import catalog

    class _Args:
        engine = args.engine
        model = "full"

    class _Cfg:
        def get(self, key, default=None):
            return default

    backend = _backend(_Args(), _Cfg())
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
            print(f"  {voice:<16}{grade:<4}{catalog.gender_of(voice)}{marks}".rstrip())

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
        print(f"{len(chunks)} chunks, about {format_duration(estimate)} -> {out_path}",
              file=sys.stderr)
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


HANDLERS = {
    "init": cmd_init,
    "config": cmd_config,
    "read": cmd_read,
    "convert": cmd_convert,
    "publish": cmd_publish,
    "feed": cmd_feed,
    "voices": cmd_voices,
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    from earmark.config import ConfigError
    from earmark.library import LibraryError
    from earmark.publish import PublishError

    try:
        return HANDLERS[args.command](args)
    except (FileNotFoundError, RuntimeError, ValueError, ConfigError,
            LibraryError, PublishError) as exc:
        print(f"earmark: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
