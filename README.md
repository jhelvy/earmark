# earmark

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

Under construction, but it makes audio. Milestone 4 of 8.

| Milestone | What it adds | Done |
|---|---|---|
| M1 | `earmark text FILE` — extraction + cleaning | ✅ |
| M2 | `earmark text URL` — article extraction | ✅ |
| M3 | Kokoro synthesis, MP3 encoding | ✅ |
| M4 | Chunking, pauses, `earmark read` | ✅ |
| M5 | Chunk cache | ✅ |
| M6 | ID3 tags | ✅ |
| M7 | Podcast feed + publishing | ✅ |
| M8 | Config, profiles, polish | |

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

Profiles (`article`, `paper`, `book`) preset the rules; individual flags
(`--keep-references`, `--tables describe`, `--say-code`, …) override them. A
`[clean.replace]` table in `~/.config/earmark/config.toml` fixes any word the
narrator mispronounces.

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
  --folder "~/pCloud Drive/Public Folder/earmark" \
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

## License

MIT © John Paul Helveston

[kokoro]: https://huggingface.co/hexgrad/Kokoro-82M
[uv]: https://docs.astral.sh/uv/
