# earmark — notes for Claude

## What this is

A Python CLI that turns documents and article URLs into a private podcast feed.
Local Kokoro TTS, no API keys, no per-minute cost.

Seven commands: `init`, `config`, `read`, `convert`, `publish`, `feed`,
`voices`. `read`/`convert`/`publish` are one pipeline stopped at three points —
Markdown, MP3, feed — and each is a prefix of the next. Adding an eighth
command should feel expensive; the point of the surface is that it fits in a
paragraph.

## The library is the unit

A **library** is a folder holding `earmark.toml`, `text/*.md`, `audio/*.mp3`,
`feed.xml`, `episodes.json` and `cover.jpg`. It is meant to be a folder served
on the public web, so writing the MP3 *is* publishing it.

**There is no `library` config key and there must never be one.** The library
is the folder the config sits in. That is what makes a library portable (move
the folder, nothing breaks) and multi-library free (`cd` switches). Resolution
order lives in `library.find()`: `--library`, `$EARMARK_LIBRARY`, an
`earmark.toml` in cwd or any parent, then the path in
`~/.config/earmark/default`.

`paths.py` holds only what must *not* sync to a public folder: the 354 MB
model, the chunk cache, and that one-line pointer.

## Front matter is what makes the Markdown step real

`earmark read` writes `earmark: cleaned` into the front matter, and
`pipeline.load` passes such a file through **verbatim**. Without that marker,
`convert` would re-clean a file the user hand-edited and undo the edit with the
same rules that caused it. `frontmatter.py` is deliberately not YAML: every line
is `key: value`, split on the *first* colon so titles may contain one.

An unterminated `---` block is treated as body, not front matter — otherwise a
document that merely opens with a horizontal rule loses its first half.

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

## Publishing is a folder, plus one line of shell

`publish.py` is `Site`: the library viewed as a public web folder. It turns a
name into a URL, copies a file in if it is not already there, and runs the
`after_publish` config hook from inside the library.

There used to be four publishers (folder, rclone, command, github). They are
gone. A GitHub Pages repo, an rclone remote and an rsync target are all one line
of `after_publish`, which is a config key rather than a plugin system and covers
every host without earmark knowing the name of one. **Do not add a publisher
back.** Add a recipe to the README's table.

`feed.py` renders XML from `episodes.json` and never parses XML back.
`feedops.py` combines the two. Keep those three separate.

### Episode filenames follow the slug

`convert` writes `audio/<slug>.mp3` and `publish` must not rename it, or the two
commands would disagree about where a document's audio lives. The content digest
is still computed — it is the feed's `guid`, and how re-publishing replaces an
episode instead of duplicating it — but it is not in the filename.

### Cover art fails silently

`art.py` exists because a non-compliant `<itunes:image>` produces **no error
anywhere** — the app shows its grey placeholder and the feed still validates.
So earmark normalizes rather than validates, on every publish: flatten alpha
onto a solid colour (a transparent PNG renders wrong in Apple Podcasts), pad to
square, scale, and walk the JPEG quality ladder until the file is under 512 KB.
ffmpeg does all of it, so this costs no dependency.

Non-square input is **padded, never cropped**. Cropping silently eats part of a
logo; letterboxing is a cosmetic result the user can see and correct.

`cover` is a file in the library that earmark normalizes; `image` is a URL to
artwork hosted elsewhere that earmark only passes through. `image` disables the
cover pipeline rather than racing it. Whatever writes the cover must also keep
`COVER_NAME` out of `orphans()`, or the next `--prune --orphans` deletes it.

## Config

`config.py` never raises while loading — a broken file must stay inspectable
with `earmark config --show`. Problems are collected into `warnings` (a typo'd
key that was ignored) and `errors` (a value that cannot be used); `Config.check()`
turns errors into a `ConfigError`, and `cli._open_library()` is the single place
that loads, reports warnings and calls `check`.

**Every key in `DEFAULTS` must be one a command actually reads**, and must
appear in `TEMPLATE`. `jobs` sat in `DEFAULTS` for a while doing nothing, which
is a lie told in a documented file; `test_config.py` asserts against both now.

**`[feed]` must stay the last table in `TEMPLATE`.** TOML puts a key appended at
the bottom of a file into whichever table came before it. An unknown key under
`[feed]` warns; an extra entry under `[replace]` looks exactly like a word the
user wanted respoken, and would be silently accepted.

## The model downloads itself

`cli._download_model` prompts on a TTY before pulling 354 MB, then shows a
progress bar. There is no `models` command any more — a one-time download is
not a thing to document. The files live in the data dir, never in the library.

The cache prunes itself too (`cache.autoprune`, after every convert): entries
untouched for 90 days, then LRU eviction above 2 GB.

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
real 325 MB Kokoro model. `conftest.py` redirects `paths.cache_dir`,
`data_dir`, `state_dir` and `pointer_path` at `tmp_path`, and offers a
`library` fixture (an initialized library) and a `backend` fixture (a fake that
produces silence at a plausible speaking rate, so the whole pipeline including a
real ffmpeg encode runs without the model).

`test_cli.py` drives `main()` end to end with that fake backend — init, read,
edit, convert, publish — which is the only place library resolution, front
matter reuse and the feed meet.

## Two argparse traps already hit

- A subcommand's option must never use `dest="command"`: a nested subparser
  copies its whole namespace over the parent's, nulling the subcommand.
- Modules must reach paths through `from earmark import paths` and call
  `paths.cache_dir()`, not `from earmark.paths import cache_dir`. The direct
  import binds the function at import time, which defeats the test fixture and
  makes tests write to the real user cache.

`--library` must work on either side of the verb, and `parents=` cannot deliver
that: parent parsers **share action objects**, so `set_defaults` on the top
parser silently rewrites every subparser's default too, and
`earmark --library X read f.pdf` then acts on the wrong library. Hence
`_add_library()`, which builds a fresh action per parser: `None` on the top
parser to seed the namespace, `SUPPRESS` on each subcommand so an absent flag
leaves the parent's value alone.
