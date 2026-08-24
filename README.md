# earmark

<img src="docs/logo.png" align="right" width="160" alt="earmark logo" />

Turn the things you meant to read into a private podcast feed.

```bash
earmark init ~/pCloud\ Drive/public/audio --base-url https://filedn.com/XXXX/audio
earmark publish paper.pdf
```

`earmark` extracts the text from a document (PDF, DOCX, PPTX, EPUB, HTML,
Markdown) or an article URL, rewrites it into something that sounds good read
aloud, narrates it locally with [Kokoro-82M][kokoro], and puts the MP3 on a
podcast feed your phone can subscribe to.

Everything runs on your machine. No API keys, no per-minute cost.

**[Documentation →](https://jhelvy.github.io/earmark)**

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

## The commands

```bash
earmark text    SOURCE   ->  text/<name>.md      look at it, fix it
earmark audio   SOURCE   ->  audio/<name>.mp3    narrate it
earmark publish SOURCE   ->  feed.xml            all of the above
```

`publish` runs the whole chain, so `earmark publish paper.pdf` is all you ever
need to type. The other four commands are setup and housekeeping: `init`,
`config`, `feed`, `voices`.

Everything earmark makes lands in one folder you choose, your **library**,
which is meant to be a folder served on the public web. There is no `library`
setting anywhere, because the library is the folder its `earmark.toml` sits in.

## Documentation

| | |
|---|---|
| [Installation](https://jhelvy.github.io/earmark/user-guide/installation.html) | uv, ffmpeg, and the Python version constraint |
| [Quickstart](https://jhelvy.github.io/earmark/user-guide/quickstart.html) | empty folder to something playing on your phone |
| [The library](https://jhelvy.github.io/earmark/user-guide/the-library.html) | why a library is a folder |
| [The pipeline](https://jhelvy.github.io/earmark/user-guide/the-pipeline.html) | `text`, `audio`, `publish`, and editing in between |
| [Text cleaning](https://jhelvy.github.io/earmark/user-guide/text-cleaning.html) | what gets rewritten before anything is spoken |
| [Choosing a voice](https://jhelvy.github.io/earmark/user-guide/voices.html) | 54 voices and how to pick one |
| [Publishing anywhere](https://jhelvy.github.io/earmark/user-guide/publishing.html) | GitHub Pages, rclone, rsync - one line each |
| [Subscribing on your phone](https://jhelvy.github.io/earmark/user-guide/subscribing.html) | where the feed URL goes in each app |
| [Reference](https://jhelvy.github.io/earmark/reference/) | every command, flag and config key |

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

The docs site is built with [great-docs](https://github.com/posit-dev/great-docs):

```bash
uv tool install great-docs
great-docs preview
```

## License

MIT © John Paul Helveston

[kokoro]: https://huggingface.co/hexgrad/Kokoro-82M
[uv]: https://docs.astral.sh/uv/
