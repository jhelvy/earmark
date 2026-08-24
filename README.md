# earmark

<img src="docs/logo.png" align="right" width="160" alt="earmark logo" />

Turn the things you meant to read into a private podcast feed.

```bash
earmark init ~/pCloud/public/audio --base-url https://filedn.com/XXXX/audio
earmark publish paper.pdf
```

`earmark` extracts the text from a document (PDF, DOCX, PPTX, EPUB, HTML,
Markdown) or an article URL, rewrites it into something that sounds good read
aloud, narrates it locally with [Kokoro-82M][kokoro], and puts the MP3 on a
podcast feed your phone can subscribe to.

Everything runs on your machine. No API keys, no per-minute cost.

## The library

Everything earmark makes lives in one folder you choose — your **library**.

```
~/pCloud Drive/public/audio/     <- the library
  earmark.toml                   its settings
  feed.xml   episodes.json       the feed
  cover.jpg
  text/
    attention-is-all-you-need.md   the words, yours to edit
  audio/
    attention-is-all-you-need.mp3  the narration
```

Two things to know about it:

1. **It should be a folder that is served on the public web.** Anything works:
   a pCloud or Dropbox public folder, an nginx docroot, a synced WebDAV share,
   a GitHub Pages repo. Podcast apps need a URL they can fetch without logging
   in; earmark writes files, and your folder does the rest.
2. **`earmark.toml` lives inside it**, so a library is self-contained. There is
   no `library =` setting anywhere, because the library is the folder its config
   sits in. Move the folder and nothing breaks.

Nothing else is stored outside the library except the model download, the
synthesis cache, and one line naming your default library.

## Install

Requires [uv][uv] and `ffmpeg`.

```bash
brew install ffmpeg
git clone https://github.com/jhelvy/earmark.git
cd earmark
uv tool install --python 3.12 -e .
```

Python 3.11 or 3.12 specifically: the Kokoro toolchain does not yet support
3.13 or newer, and `uv` will fetch a suitable interpreter for you.

`uv tool install` puts `earmark` on your `PATH` in an environment of its own —
you never activate anything to use it. `-e` makes that install track the repo,
so a `git pull` takes effect immediately. The `.venv/` in the repo is for
running the tests, not for running the tool.

## The seven commands

```bash
earmark init [PATH]     create a library
earmark config          edit its settings in $EDITOR
earmark read SOURCE     source          -> text/<slug>.md
earmark convert SOURCE  source or .md   -> audio/<slug>.mp3
earmark publish SOURCE  source, .md or .mp3 -> the feed
earmark feed            what is published, and the feed URL
earmark voices          list the voices, or hear one
```

`read`, `convert` and `publish` are the same pipeline stopped at three
different points. Any of them takes any source: a file, a URL, a Markdown file
you edited, or — for `publish` — an MP3 that already exists.

### Getting started

```bash
earmark init ~/pCloud\ Drive/public/audio --base-url https://filedn.com/XXXX/audio
earmark publish https://example.com/some-long-article
earmark feed                          # paste this URL into your podcast app
```

`init` records that library as your default, so the commands work from
anywhere. To use a different one, `cd` into it or pass `--library PATH`.

### Editing before you listen

Extraction is good, not perfect — a mangled equation, a stray caption, a
section you don't care about. So the Markdown is a real stopping point:

```bash
earmark read paper.pdf                # -> text/some-paper.md
$EDITOR library/text/some-paper.md    # fix it, cut things, add a note
earmark publish library/text/some-paper.md
```

Files earmark wrote carry `earmark: cleaned` in their front matter, and are
narrated **exactly as they stand** — your edits are never re-cleaned. Markdown
from anywhere else goes through the cleaner like any other source.

`convert` and `publish` write the Markdown too, so you can always go back and
fix something without re-extracting.

## Multiple libraries

A library is a folder with an `earmark.toml` in it, and earmark finds the one
you mean by looking, in order, at:

1. `--library PATH`
2. `$EARMARK_LIBRARY`
3. an `earmark.toml` in the working directory or any parent
4. the default recorded by `earmark init`

So separate feeds — papers, fiction, things for the commute — need no
configuration beyond making them:

```bash
earmark init ~/public/papers  --base-url https://example.com/papers
earmark init ~/public/fiction --base-url https://example.com/fiction --no-default

cd ~/public/fiction && earmark publish a-novel.epub    # goes to the fiction feed
```

## Configuration

`earmark config` opens the library's `earmark.toml` in `$EDITOR`. A
command-line flag always wins over the file.

```toml
voice = "af_bella"
speed = 1.1
profile = "paper"

# Run after every publish, from inside the library. Only needed if your
# library is not already a folder that syncs to the web.
# after_publish = "git add -A && git commit -m 'earmark' && git push"

# Fix a mispronunciation once instead of every time.
[replace]
BEV = "battery electric vehicle"

[feed]
base_url = "https://filedn.com/XXXX/audio"
title = "John's Reading Pile"
author = "John Helveston"
description = "Things I meant to read."
cover = "cover.jpg"
```

`earmark config --show` prints every setting in effect, where it came from, and
every path earmark is using.

`[feed]` is deliberately the last table in the file. TOML puts a key you add at
the bottom into whichever table came before it, and an unknown key under
`[feed]` warns loudly, where an extra entry under `[replace]` would look like a
word you wanted respoken.

## Publishing anywhere

If your library folder is already on the web, publishing is finished the moment
the file is written — there is nothing to upload.

If it isn't, `after_publish` is one line of shell that runs inside the library
once the feed is written:

| Host | `after_publish` |
|---|---|
| **GitHub Pages** | `git add -A && git commit -m earmark && git push` |
| **S3 / R2 / B2 / Drive** | `rclone sync . r2:my-bucket/audio` |
| **Your own server** | `rsync -a --delete . me@host:/var/www/audio/` |

Set `base_url` to wherever those end up, and `earmark feed --check` will HEAD
the feed, the cover and the newest episodes to prove the URLs really serve.

## Cover art

Put an image in the library and name it:

```toml
[feed]
cover = "cover.jpg"
```

Every publish re-normalizes it: transparency flattened onto white (a
transparent PNG renders wrong in Apple Podcasts), padded to square, scaled, and
compressed until it is under Apple's 512 KB ceiling. Non-square art is
**padded, never cropped** — cropping silently eats part of a logo.

This matters more than it sounds like it should, because a non-compliant
`<itunes:image>` produces no error anywhere: the app just shows its grey
placeholder and the feed still validates.

Already have artwork hosted somewhere? Use `image = "https://..."` instead and
earmark will pass the URL straight through.

## Why the text cleaning matters

Most text-to-speech pipelines read a document exactly as written, which means
you sit through URLs, bracketed citations, table cells, and ten minutes of
bibliography. `earmark` rewrites first:

| Written | Spoken |
|---|---|
| `Many tools, e.g. pandas, exist.` | Many tools, for example pandas, exist. |
| `Shown in [12] and [3, 4].` | Shown in and. |
| `Read [the paper](https://…).` | Read the paper. |
| `Adoption hit 42%.` | Adoption hit 42 percent. |
| `A 60 kWh pack.` | A 60 kilowatt hours pack. |
| `## References` … | *(cut entirely)* |

Check what will be spoken before spending the compute:

```bash
earmark read paper.pdf --profile paper --stdout | less
earmark convert paper.pdf --dry-run            # how long is this?
```

The `paper` profile also cuts the title page, authors and affiliations, so the
audio opens at the abstract. For arXiv URLs, earmark asks the arXiv API for the
real title and authors, since a PDF's own metadata is usually empty.

PDFs get a pass of their own first. A PDF has no idea what a paragraph is, so
the extracted text arrives with footnotes, page numbers and running heads
spliced into the prose — an abstract that runs straight on into "Equal
contribution. Listing order is random", or a paragraph interrupted by the
footnote hanging off its last line. Those are removed before anything else
looks at the text, using position on the page rather than guesses about
meaning: a rule that can only fire in the last 45% of a page cannot eat an
argument in the middle of one.

Profiles (`article`, `paper`, `book`) preset the rules; individual flags
(`--keep-references`, `--tables describe`, `--say-code`, …) override them.

## Choosing a voice

Kokoro ships 54 voices. The names encode a language and a gender — `af_heart`
is American female, `bm_george` is British male — and the quality spread is
large, so the list is annotated with Kokoro's own grades:

```bash
earmark voices                    # graded, grouped by language
earmark voices --lang b           # British only
earmark voices --all              # including the ones graded D or worse
earmark convert paper.pdf --voice af_bella
```

```
American English
  af_heart        A   female   (default)
  af_bella        A-  female
  af_nicole       B-  female
  am_michael      C+  male
  am_puck         C+  male

British English
  bf_emma         B-  female
```

Only two voices are graded A. `af_heart` is the default; `af_bella` is the
runner-up; `am_michael` or `am_puck` are the best male voices, and `bf_emma`
the best British one. Everything below B- is noticeably worse on a long listen.

Reading a grade table tells you less than three seconds of your own text does,
and the model is already on disk, so you can just hear it:

```bash
earmark voices --try af_bella
earmark voices --try bf_emma --text "Whatever you like."
```

Set a favourite once with `earmark config`.

Kokoro's [VOICES.md][voices] has the full grade table with training-data
volumes, and the [official demo Space][kokoro-demo] lets you audition voices in
a browser.

The 354 MB model downloads itself the first time you convert something, after
asking. It lives with your application data, not in the library — you do not
want it syncing to a public folder.

## Speed and caching

Synthesis runs at roughly **4.6x realtime** on an M-series Mac with `af_heart`.

It is also cached per chunk, keyed on the text, the voice, the speed and the
model, so re-running a document you edited re-synthesizes only what changed: a
22-minute paper re-renders in **8 seconds** instead of 4 minutes 54. The cache
trims itself — entries untouched for 90 days go, and the least recently used go
after that if it passes 2 GB.

## Subscribing on your phone

This is the part that isn't obvious, because a private feed is not in any
podcast directory — you can't find it by searching for its name. You subscribe
by handing the app the URL itself.

**1. Get the URL, on the computer:**

```bash
$ earmark feed
2026-08-23   0:22:14    10.4 MB  Attention Is All You Need

1 episode(s), 10 MB total
feed      https://filedn.com/XXXX/audio/feed.xml
```

**2. Get that string onto your phone.** Text it to yourself, email it, or put it
in a note. Then copy it.

**3. Paste it into the app.** The exact place differs:

| App | Where the URL goes |
|---|---|
| **Castbox** | The **search bar** at the top — the same one you'd search a show's name in. Paste the URL, hit search, and the show comes back as the only result; tap it, then **Subscribe**. |
| **Overcast** | **+** → **Add URL** |
| **Pocket Casts** | **Profile** → **Add RSS feed** |
| **AntennaPod** | **+** → **Add podcast by RSS address** |
| **Apple Podcasts** | **Library** → **Edit** → *Add a Show by URL* — works, but unreliably; don't design around it |

Castbox is the one worth spelling out, because pasting a URL into a *search
box* looks wrong. It isn't: Castbox detects that what you pasted is a feed
rather than a search term and fetches it directly.

**4. Publish something and pull to refresh.**

```bash
earmark publish paper.pdf
```

New episodes appear on the next refresh. Artwork and show titles are cached
aggressively by every app, so a cover you add later can take hours to show up —
force-refresh the show, or unsubscribe and re-subscribe, if you're impatient.

The feed needs no authentication, so nothing else is required. If you ever move
to a host behind HTTP basic auth, Castbox and Overcast both accept credentials
inlined as `https://user:pass@host/path`.

## Housekeeping

```bash
earmark feed --check                  # do the published URLs actually serve?
earmark feed --rebuild                # rewrite feed.xml and the cover
earmark feed --prune --keep 20        # drop all but the newest 20
earmark feed --prune --max-size 800MB
earmark feed --prune --orphans        # delete files the feed no longer lists
```

## License

MIT © John Paul Helveston

[kokoro]: https://huggingface.co/hexgrad/Kokoro-82M
[voices]: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
[kokoro-demo]: https://huggingface.co/spaces/hexgrad/Kokoro-TTS
[uv]: https://docs.astral.sh/uv/
