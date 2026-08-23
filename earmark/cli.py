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

    voices = sub.add_parser("voices", help="list available voices")
    voices.add_argument("--engine", choices=["kokoro", "say"], default="kokoro")

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

    sub.add_parser("config", help="show the config file path")
    return parser


def _clean_options(args):
    from earmark import config as config_mod
    from earmark.clean import options_for

    cfg = config_mod.load()
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

    doc = extract(args.source, title=args.title, author=args.author, date=args.date)
    if args.raw:
        print(doc.markdown)
        return 0

    blocks = clean(doc.markdown, _clean_options(args))
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

    cfg = config_mod.load()
    opts = _clean_options(args)
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
            **meta_kw,
        )

    size_mb = result.path.stat().st_size / 1e6
    print(f"{result.path}  ({format_duration(result.seconds)}, {size_mb:.1f} MB)")
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

    def advance(self, index: int, seconds: float) -> None:
        if self._bar is None:
            return
        import time

        self._audio_seconds += seconds
        elapsed = max(time.monotonic() - self._t0, 1e-6)
        self._bar.update(
            self._task, advance=1, rtf=f"{self._audio_seconds / elapsed:5.1f}x realtime"
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self._bar is not None:
            self._bar.stop()
        return False


def cmd_voices(args) -> int:
    from earmark.tts import get_backend

    for voice in get_backend(args.engine).voices():
        print(voice)
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
    from earmark.paths import config_path

    path = config_path()
    print(path)
    if not path.exists():
        print("(does not exist yet; defaults are in use)", file=sys.stderr)
    return 0


HANDLERS = {
    "text": cmd_text,
    "read": cmd_read,
    "config": cmd_config,
    "voices": cmd_voices,
    "models": cmd_models,
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

    try:
        return HANDLERS[args.command](args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"earmark: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
