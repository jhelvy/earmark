# earmark


<!-- README.md is generated from README.qmd by `quarto render README.qmd`.
     The body below is assets/_common.qmd, shared with the docs landing page:
     edit that file, not README.md. -->

<img src="docs/logo.png" align="right" width="160" alt="earmark logo" />

Turn articles into narrated audio, then publish to a public podcast feed

**[Documentation →](https://jhelvy.github.io/earmark/)**

`earmark` is a python CLI tool that extracts the text from an article
URL or a document (PDF, DOCX, PPTX, EPUB, HTML, Markdown), rewrites it
into something that sounds good read aloud, narrates it locally with
[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), and puts the
MP3 on a public podcast feed you can subscribe to on your phone.

Everything runs on your machine. No API keys, no per-minute cost.

## Install

You need [uv](https://docs.astral.sh/uv/), `ffmpeg`, and Python 3.11 or
3.12 (`uv` will fetch it for you). macOS, Linux and Windows are all
covered in
[Installation](https://jhelvy.github.io/earmark/user-guide/installation.html).

## Main commands

``` bash
earmark text    SOURCE   ->  text/<name>.md      look at it, fix it
earmark audio   SOURCE   ->  audio/<name>.mp3    narrate it
earmark publish SOURCE   ->  feed.xml            all of the above
```

`publish` runs the whole chain, so `earmark publish paper.pdf` is all
you ever need to type. The other four commands are setup and
housekeeping: `init`, `config`, `feed`, `voices`.

Everything earmark makes lands in one folder you choose (your
**library**), which is meant to be a folder served on the public web.
There is no `library` setting anywhere, because the library is the
folder its `earmark.toml` sits in.

## Start here

|  |  |
|----|----|
| [Installation](https://jhelvy.github.io/earmark/user-guide/installation.html) | uv, ffmpeg, and the Python version that matters |
| [Quickstart](https://jhelvy.github.io/earmark/user-guide/quickstart.html) | empty folder to something playing on your phone |
| [The library](https://jhelvy.github.io/earmark/user-guide/the-library.html) | why a library is a folder |
| [The pipeline](https://jhelvy.github.io/earmark/user-guide/the-pipeline.html) | `text`, `audio`, `publish`, and editing in between |
| [Text cleaning](https://jhelvy.github.io/earmark/user-guide/text-cleaning.html) | what gets rewritten before anything is spoken |
| [Choosing a voice](https://jhelvy.github.io/earmark/user-guide/voices.html) | 54 voices and how to pick one |
| [Publishing anywhere](https://jhelvy.github.io/earmark/user-guide/publishing.html) | GitHub Pages, rclone, rsync: one line each |
| [Subscribing on your phone](https://jhelvy.github.io/earmark/user-guide/subscribing.html) | where the feed URL goes in each app |
| [Reference](https://jhelvy.github.io/earmark/reference/) | every command, flag and config key |

## Development

``` bash
uv venv --python 3.12
uv pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

The docs site is built with
[great-docs](https://github.com/posit-dev/great-docs):

``` bash
uv tool install great-docs
great-docs preview
```

## License

MIT © John Paul Helveston
