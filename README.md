# earmark

<img src="docs/logo.png" align="right" width="160" alt="earmark logo" />

Turn any document or article into an MP3 you can listen to.

```bash
earmark paper.pdf                     # -> ./paper.mp3
earmark https://example.com/article   # -> ./article-title.mp3
earmark paper.pdf --publish           # -> also lands in your podcast feed
```

`earmark` extracts the text from a document (PDF, DOCX, PPTX, EPUB, HTML,
Markdown) or an article URL, rewrites it into something that sounds good read
aloud, narrates it locally with [Kokoro-82M][kokoro], and writes a tagged MP3.
Optionally it publishes to a private podcast feed so the things you meant to
read show up on your phone.

Everything runs on your machine. No API keys, no per-minute cost.

## Status

Under construction, but it makes audio. Milestone 8 of 8, in progress.

| Milestone | What it adds | Done |
|---|---|---|
| M1 | `earmark text FILE` — extraction + cleaning | ✅ |
| M2 | `earmark text URL` — article extraction | ✅ |
| M3 | Kokoro synthesis, MP3 encoding | ✅ |
| M4 | Chunking, pauses, `earmark read` | ✅ |
| M5 | Chunk cache | ✅ |
| M6 | ID3 tags | ✅ |
| M7 | Podcast feed + publishing | ✅ |
| M8 | Config, voices, profiles, polish | in progress |

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

## Caching

Synthesis is cached per chunk, keyed on the text, the voice, the speed and the
model. Re-running a document you have edited re-synthesizes only what changed:
the 22-minute paper above re-renders in **8 seconds** instead of 4 minutes 54.

```bash
earmark cache info
earmark cache clear --older-than 30
```

Cached audio costs about 2.9 MB per minute.

## Speed

Measured on an M-series Mac, `af_heart`, default model: **~4.6x realtime**. The
22-minute "Attention Is All You Need" took 4 minutes 54 seconds to narrate.

The `fp16` and `int8` model variants are smaller on disk but not faster here —
`int8` is 2.6x *slower*, because onnxruntime's CPU provider has no fast
quantized kernels for this graph. Stick with the default unless you are short
on disk.

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
earmark text paper.pdf --profile paper | less   # read it first
earmark paper.pdf --dry-run                     # how long is this?
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
(`--keep-references`, `--tables describe`, `--say-code`, …) override them. A
`[clean.replace]` table in `~/.config/earmark/config.toml` fixes any word the
narrator mispronounces.

## Choosing a voice

Kokoro ships 54 voices. The names encode a language and a gender — `af_heart`
is American female, `bm_george` is British male — and the quality spread is
large, so the list is annotated with Kokoro's own grades:

```bash
earmark voices                    # graded, grouped by language
earmark voices --lang b           # British only
earmark voices --all              # including the ones graded D or worse
earmark paper.pdf --voice af_bella
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

Set a favourite once in `~/.config/earmark/config.toml`:

```toml
voice = "af_bella"
```

Kokoro's [VOICES.md][voices] has the full grade table with training-data
volumes, and the [official demo Space][kokoro-demo] lets you audition voices in
a browser.

## Configuration

Defaults live in `~/.config/earmark/config.toml`. A command-line flag always
wins over the file.

```bash
earmark config init     # write a commented starter file
earmark config edit     # open it in $EDITOR
earmark config show     # what is in effect, and where each value came from
earmark config path
```

```toml
voice = "af_heart"      # see: earmark voices
speed = 1.1
profile = "paper"
output_dir = "~/Audiobooks"

# Fix a mispronunciation once instead of every time.
[clean.replace]
BEV = "battery electric vehicle"
```

A misspelled setting warns instead of vanishing silently, and a value that
cannot be used (`speed = 9.0`) stops the run and names itself rather than
failing somewhere deep in the synthesizer. `earmark config show` still works on
a file with mistakes in it, which is the point.

## Publishing to a podcast feed

This is what turns a folder of MP3s into something you actually listen to.
`earmark` builds a standard podcast RSS feed; you subscribe to it once in
Overcast, Pocket Casts, AntennaPod or anything else that takes a feed URL, and
every document you convert shows up on your phone with playback-position sync.

**earmark does not host anything.** It needs two things from you: somewhere to
put files, and the public URL those files appear at. That keeps you in control
of where your audio lives, and means any host works — including one earmark has
never heard of.

### The four publishers

| Publisher | Use it when | Needs |
|---|---|---|
| `folder` | Anything that syncs a local directory to the web | `folder`, `base_url` |
| `rclone` | Any object store — S3, R2, B2, Drive, WebDAV, SFTP, 70+ others | `remote`, `base_url` |
| `command` | You have your own way of shipping a file | `command`, `base_url` |
| `github` | You have no storage, but you do have GitHub | `repo`, `base_url` |

`folder` is the general one and covers most services without a line of code:
whatever already turns a directory into URLs does the work. Adding a new host
usually means adding a recipe below, not a publisher.

### Recipes

**pCloud** (Public Folder is a Premium feature; enable it once at my.pcloud.com):

```bash
earmark feed init \
  --publisher folder \
  --folder "~/pCloud Drive/public/earmark" \
  --base-url "https://filedn.com/YOUR-ID/earmark" \
  --title "My Reading Pile"
```

**Dropbox / iCloud Drive / Syncthing / any synced folder** — identical, with the
folder and the public base URL that service gives you.

**Cloudflare R2, Backblaze B2, S3, Google Drive, WebDAV, SFTP** — configure the
remote once with `rclone config`, then:

```bash
earmark feed init --publisher rclone \
  --remote "r2:my-bucket/earmark" \
  --base-url "https://media.example.com/earmark"
```

**Your own server:**

```bash
earmark feed init --publisher command \
  --command "scp {local} me@example.com:/srv/earmark/{name}" \
  --base-url "https://example.com/earmark"
```

**GitHub Pages** — free, but a published site is capped at 1 GB (~35 hours of
audio) with a 100 MB per-file limit. Because git keeps deleted blobs forever,
earmark rewrites the branch as a single commit on each push so the repo tracks
the size of the current feed rather than its whole history:

```bash
earmark feed init --publisher github \
  --repo ~/gh/my-feed \
  --base-url "https://you.github.io/my-feed"
```

### Using it

```bash
earmark paper.pdf --publish     # convert, then add to the feed
earmark feed url                # paste this into your podcast app
earmark feed list               # what's published, and how much space it uses
earmark feed doctor             # prove the URLs actually serve
earmark feed prune --keep 40    # drop the oldest episodes
earmark feed prune --orphans    # drop files the feed no longer lists
```

`earmark feed doctor` is the one to run first. Whatever host you picked, it
fetches the feed and the newest episodes over HTTP and tells you whether a
podcast app would actually be able to download them — which catches the usual
mistake of a `base_url` that does not point at the same place your publisher
writes to.

`episodes.json` is the source of truth and `feed.xml` is rebuilt from it every
time, so retitling, re-hosting and pruning are all safe. A copy is published
alongside the feed so it survives losing your laptop.

> **Anything you publish is readable by anyone with the URL.** These links are
> unguessable, not private. That is fine for open-access papers, preprints and
> public articles; think before publishing paywalled or copyrighted material.
> Publishing is never automatic — it takes an explicit `--publish`.

### Subscribing on your phone

`earmark feed url` prints the URL. Then:

| App | How |
|---|---|
| **Castbox** | Paste the URL into the **search bar** and hit search; the show comes back as a result, then tap Subscribe |
| **Overcast** | Search → **Add URL** |
| **Pocket Casts** | Profile → **Add RSS feed** |
| **Apple Podcasts** | Library → Edit → *Add a Show by URL* — works, but unreliably; don't design around it |

The feed needs no authentication, so nothing else is required. If you ever move
to a host behind HTTP basic auth, Castbox and Overcast both accept credentials
inlined as `https://user:pass@host/path`.

## License

MIT © John Paul Helveston

[kokoro]: https://huggingface.co/hexgrad/Kokoro-82M
[voices]: https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md
[kokoro-demo]: https://huggingface.co/spaces/hexgrad/Kokoro-TTS
[uv]: https://docs.astral.sh/uv/
