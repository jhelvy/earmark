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
    read.add_argument("-o", "--out", default=None, help="output MP3 (default: ./<title-slug>.mp3)")
    _add_meta_args(read)
    _add_clean_args(read)

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


def cmd_read(args) -> int:
    print(
        "earmark: audio synthesis is not wired up yet (milestone 3).\n"
        "For now, check the text that will be spoken:\n"
        f"    earmark text {args.source}",
        file=sys.stderr,
    )
    return 1


def cmd_config(args) -> int:
    from earmark.paths import config_path

    path = config_path()
    print(path)
    if not path.exists():
        print("(does not exist yet; defaults are in use)", file=sys.stderr)
    return 0


HANDLERS = {"text": cmd_text, "read": cmd_read, "config": cmd_config}


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
