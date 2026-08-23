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
M5 cache ✅ · M6 ID3 tags ✅ · M7 feed + publishing ✅ · M8 polish.

Each milestone must be independently runnable.
