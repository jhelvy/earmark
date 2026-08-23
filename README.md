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

Under construction. Milestone 1 of 8 — extraction and speech cleaning work;
audio synthesis is not wired up yet.

| Milestone | What it adds | Done |
|---|---|---|
| M1 | `earmark text FILE` — extraction + cleaning | ✅ |
| M2 | `earmark text URL` — article extraction | ✅ |
| M3 | Kokoro synthesis, MP3 encoding | |
| M4 | Chunking, pauses, `earmark read` | |
| M5 | Chunk cache | |
| M6 | ID3 tags | |
| M7 | Podcast feed + pCloud publishing | |
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
earmark text paper.pdf --profile paper | less
```

Profiles (`article`, `paper`, `book`) preset the rules; individual flags
(`--keep-references`, `--tables describe`, `--say-code`, …) override them. A
`[clean.replace]` table in `~/.config/earmark/config.toml` fixes any word the
narrator mispronounces.

## License

MIT © John Paul Helveston

[kokoro]: https://huggingface.co/hexgrad/Kokoro-82M
[uv]: https://docs.astral.sh/uv/
