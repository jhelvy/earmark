# earmark — notes for Claude

## What this is

A Python CLI that turns a document or an article URL into an MP3, and
optionally publishes it to a personal podcast feed. Local Kokoro TTS, no API
keys, no per-minute cost.

## Non-obvious constraints

- **Python 3.11 or 3.12 only.** `kokoro` and `misaki` cap at `<3.13`; the repo
  pins `>=3.11,<3.13` so `misaki[en]` stays installable as an extra. The
  machine's system Python is 3.14 and cannot run this. Always
  `uv venv --python 3.12`.
- **`kokoro-onnx`, never `kokoro`.** The torch build pulls torch, transformers
  and spacy. `kokoro-onnx` needs only onnxruntime.
- **`ffmpeg` is a runtime prerequisite**, not a Python dependency.
- **PDFs go through `pypdf`, not markitdown.** markitdown routes PDFs to
  pdfminer with default layout parameters, which drops inter-word spaces
  entirely on many LaTeX PDFs (arXiv especially): "Thedominantsequence". pypdf
  spaces the same files correctly and is already a dependency for metadata.
  markitdown still handles DOCX, PPTX, EPUB and HTML.
- **URLs go through `trafilatura`, not markitdown.** markitdown's HTML path is
  a markdownify wrapper with no boilerplate removal, so it yields nav rails and
  cookie banners.

## PDF page furniture is stripped before cleaning

`earmark/extract/pages.py` runs inside `_via_pypdf`, while page boundaries still
exist — by the time `clean.py` sees the text they are just blank lines. It
removes footnotes, page numbers, running heads and publication stamps.

Every rule is **positional**, never semantic: a footnote may only start in the
last 45% of a page and may not span more than 30 lines, so a false positive
cannot swallow an argument mid-page. Two discriminators are load-bearing and
easy to break:

- `*Equal` is a footnote, `* item` is a bullet. **The absence of a space is the
  only difference.**
- `4To illustrate` is a footnote, `4 Why Self-Attention` is a heading. Same rule.

An inline superscript (`gradients 4.`) is only stripped when a footnote with
that number was actually cut from the same page, and never after a word like
"Table" or "Figure". That is what keeps "see Table 4." intact.

## Where the quality lives

`earmark/clean.py`. It is an ordered pipeline of small named `str -> str`
functions; order is load-bearing and documented inline. Two rules in particular:

1. **Code fences are stripped first**, so no later regex can reach inside one.
2. **Abbreviations are expanded before anything splits sentences.** Expanding
   `e.g.` and `et al.` removes the main cause of bogus sentence breaks, which is
   why there is no `pysbd`/`nltk` dependency.

When markup is removed, replace it with a **space**, not `""` — otherwise words
on either side fuse ("As of 2026<a>electric" becomes "2026electric"). `_tidy`
collapses the extra whitespace afterwards.

`CLEAN_SCHEMA_VERSION` is part of the synthesis cache key. Bump it whenever a
transform changes what comes out of the module, or stale audio will be replayed.

## Testing

`tests/test_clean.py` is the bulk of the suite and the regression net for every
extraction bug found in the wild. When a real document reveals a defect, add the
minimal reproducing pair to `CASES` or a named test before fixing it.

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

`-m 'not slow'` is the default; the `slow` marker is for tests that load the
real 325 MB Kokoro model.

## Publishing is deliberately host-agnostic

`publish.py` knows how to put bytes somewhere and how to build a URL. It knows
nothing about pCloud, Dropbox or GitHub specifically. Four publishers cover
essentially everything:

- `folder` — copy into a directory something else syncs to the web
- `rclone` — shell out to rclone (S3, R2, B2, Drive, WebDAV, SFTP, ...)
- `command` — a user-supplied command template
- `github` — commit into a Pages repo, squashed to one commit per push

**Supporting a new service should mean adding a recipe to the README, not a
publisher here.** Only add a publisher if a service cannot be reached by any of
the four.

`feed.py` renders XML from `episodes.json` and never parses XML back. `feedops.py`
combines the two. Keep those three separate.

`list_names()` is optional on a publisher; it is what lets `feed doctor` spot
files the manifest no longer references. Return `None` if the backend cannot
enumerate.

## Config

`config.py` never raises while loading — a broken file must stay inspectable
with `earmark config show`. Problems are collected into `warnings` (a typo'd key
that was ignored) and `errors` (a value that cannot be used); `Config.check()`
turns errors into a `ConfigError`, and `cli._load_config()` is the single place
that loads, reports warnings and calls `check`.

**Every key in `DEFAULTS` must be one a command actually reads.** `jobs` sat
there for a while doing nothing, which is a lie told in a documented file;
`test_config.py` now asserts against it. Add the key when `--jobs` lands, not
before.

Config lives in `~/.config/earmark`, not platformdirs: on macOS
`user_config_dir` and `user_data_dir` are the *same* path, so `config.toml`
would sit inside the directory holding a 354 MB `models/`. `EARMARK_CONFIG_DIR`
overrides it.

`feed init` must check for an existing `[feed]` by **parsing** the TOML, not by
searching for the string `"[feed]"` — the starter config carries a commented-out
`# [feed]` example, and a substring test treats that as already-configured
forever.

## Two argparse traps already hit

- A subcommand's option must never use `dest="command"`: a nested subparser
  copies its whole namespace over the parent's, nulling the subcommand. This is
  why `feed init --command` uses `dest="command_template"`.
- Modules must reach paths through `from earmark import paths` and call
  `paths.cache_dir()`, not `from earmark.paths import cache_dir`. The direct
  import binds the function at import time, which defeats the test fixture and
  makes tests write to the real user cache.

## Milestones

M1 extract + clean ✅ · M2 URLs ✅ · M3 synthesis ✅ · M4 chunking + `read` ✅ ·
M5 cache ✅ · M6 ID3 tags ✅ · M7 feed + publishing ✅ · M8 polish (config ✅,
voice catalog ✅; `--jobs` and cache auto-pruning remaining).

`tts/catalog.py` is data only — voice grades transcribed from Kokoro's
VOICES.md. Only English voices are graded there, and grades for the rest must
stay absent rather than invented.

Each milestone must be independently runnable.
