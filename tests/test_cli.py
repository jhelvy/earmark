"""The command surface: seven verbs, one library, and where files land."""

from __future__ import annotations

import pytest

from conftest import needs_ffmpeg

from earmark.cli import build_parser, main
from earmark.library import Library, LibraryError


def parse(argv):
    return build_parser().parse_args(argv)


COMMANDS = ["init", "config", "text", "audio", "publish", "feed", "voices"]


NEEDS_SOURCE = ("text", "audio", "publish")


@pytest.mark.parametrize("name", COMMANDS)
def test_every_command_parses(name):
    argv = [name] + (["x.pdf"] if name in NEEDS_SOURCE else [])
    assert parse(argv).command == name


@pytest.mark.parametrize("name", ["text", "audio", "publish"])
def test_the_pipeline_commands_take_a_source(name):
    assert parse([name, "paper.pdf"]).source == "paper.pdf"


@pytest.mark.parametrize("name", COMMANDS)
def test_every_command_takes_library(name):
    args = parse([name, "--library", "/tmp/lib"] + (["x.pdf"] if name in NEEDS_SOURCE else []))
    assert args.library == "/tmp/lib"


def test_cleaning_flags_reach_audio():
    args = parse(["audio", "paper.pdf", "--profile", "paper", "-s", "1.2"])
    assert (args.profile, args.speed) == ("paper", 1.2)


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "earmark" in capsys.readouterr().out


# -- library resolution ---------------------------------------------------


def test_init_creates_a_library(tmp_path, capsys):
    root = tmp_path / "audio"
    assert main(["init", str(root), "--base-url", "https://example.com/a"]) == 0
    lib = Library.at(root)
    assert lib.config_path.is_file()
    assert lib.text_dir.is_dir() and lib.audio_dir.is_dir()
    assert "https://example.com/a" in lib.config_path.read_text()


def test_init_refuses_to_clobber(tmp_path, capsys):
    main(["init", str(tmp_path / "a")])
    assert main(["init", str(tmp_path / "a")]) == 1
    assert "already exists" in capsys.readouterr().err


def test_init_records_the_default_library(tmp_path, monkeypatch):
    from earmark import library as library_mod

    root = tmp_path / "audio"
    main(["init", str(root)])
    monkeypatch.chdir(tmp_path)
    assert library_mod.find() == root.resolve()


def test_no_default_leaves_the_pointer_alone(tmp_path, monkeypatch):
    from earmark import library as library_mod

    main(["init", str(tmp_path / "audio"), "--no-default"])
    monkeypatch.chdir(tmp_path)
    with pytest.raises(LibraryError, match="no library found"):
        library_mod.find()


def test_being_inside_a_library_beats_the_default(tmp_path, monkeypatch):
    from earmark import library as library_mod

    main(["init", str(tmp_path / "default")])
    main(["init", str(tmp_path / "other"), "--no-default"])
    monkeypatch.chdir(tmp_path / "other")
    assert library_mod.find() == (tmp_path / "other").resolve()


def test_a_subfolder_of_a_library_still_finds_it(tmp_path, monkeypatch):
    from earmark import library as library_mod

    main(["init", str(tmp_path / "lib"), "--no-default"])
    monkeypatch.chdir(tmp_path / "lib" / "text")
    assert library_mod.find() == (tmp_path / "lib").resolve()


def test_the_env_var_beats_the_working_directory(tmp_path, monkeypatch):
    from earmark import library as library_mod

    main(["init", str(tmp_path / "a"), "--no-default"])
    main(["init", str(tmp_path / "b"), "--no-default"])
    monkeypatch.chdir(tmp_path / "a")
    monkeypatch.setenv("EARMARK_LIBRARY", str(tmp_path / "b"))
    assert library_mod.find() == (tmp_path / "b").resolve()


def test_commands_outside_any_library_say_so(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["feed"]) == 1
    assert "no library found" in capsys.readouterr().err


def test_a_folder_without_a_config_is_not_a_library(tmp_path, capsys):
    assert main(["feed", "--library", str(tmp_path)]) == 1
    assert "is not a library" in capsys.readouterr().err


# -- config ---------------------------------------------------------------


def test_config_path_prints_the_file(tmp_path, capsys):
    main(["init", str(tmp_path / "lib")])
    main(["config", "--path", "--library", str(tmp_path / "lib")])
    assert capsys.readouterr().out.strip().endswith("earmark.toml")


def test_config_show_lists_settings_and_paths(tmp_path, capsys):
    main(["init", str(tmp_path / "lib"), "--base-url", "https://example.com/a"])
    assert main(["config", "--show", "--library", str(tmp_path / "lib")]) == 0
    out = capsys.readouterr().out
    assert "library" in out and "voice" in out and "af_heart" in out


def test_config_show_reports_a_broken_value(tmp_path, capsys):
    main(["init", str(tmp_path / "lib")])
    lib = Library.at(tmp_path / "lib")
    lib.config_path.write_text("speed = 9.0\n", encoding="utf-8")
    assert main(["config", "--show", "--library", str(lib.root)]) == 1
    assert "speed" in capsys.readouterr().err


def test_a_broken_config_stops_a_command_by_name(tmp_path, capsys):
    main(["init", str(tmp_path / "lib")])
    lib = Library.at(tmp_path / "lib")
    lib.config_path.write_text('voice = ""\n', encoding="utf-8")
    assert main(["feed", "--library", str(lib.root)]) == 1
    assert "voice" in capsys.readouterr().err


def test_publishing_without_a_base_url_says_what_to_do(tmp_path, capsys):
    main(["init", str(tmp_path / "lib")])
    assert main(["publish", "x.pdf", "--library", str(tmp_path / "lib")]) == 1
    assert "base_url" in capsys.readouterr().err


# -- the pipeline, end to end --------------------------------------------


@pytest.fixture
def lib(tmp_path, monkeypatch, backend):
    """An initialized library, with synthesis faked out."""
    import earmark.cli as cli_mod

    root = tmp_path / "library"
    main(["init", str(root), "--base-url", "https://example.com/audio"])
    monkeypatch.setattr(cli_mod, "_backend", lambda args, cfg: backend)
    return Library.at(root)


@pytest.fixture
def paper(tmp_path):
    path = tmp_path / "a-paper.md"
    path.write_text(
        "# On Reading Things\n\n"
        "This is the first paragraph of the paper.\n\n"
        "## Method\n\nWe did the thing, and then we wrote about it.\n",
        encoding="utf-8",
    )
    return path


def test_text_writes_markdown_into_the_library(lib, paper, capsys):
    assert main(["text", str(paper), "--library", str(lib.root)]) == 0
    out = lib.markdown_path("on-reading-things")
    assert out.is_file()
    assert "earmark: cleaned" in out.read_text()
    assert out.name in capsys.readouterr().out


def test_text_refuses_to_clobber_your_edits(lib, paper, capsys):
    main(["text", str(paper), "--library", str(lib.root)])
    lib.markdown_path("on-reading-things").write_text("mine", encoding="utf-8")
    assert main(["text", str(paper), "--library", str(lib.root)]) == 1
    assert lib.markdown_path("on-reading-things").read_text() == "mine"
    assert "--force" in capsys.readouterr().err


def test_text_stdout_writes_no_file(lib, paper, capsys):
    assert main(["text", str(paper), "--stdout", "--library", str(lib.root)]) == 0
    assert not lib.markdown_path("on-reading-things").exists()
    assert "first paragraph" in capsys.readouterr().out


@needs_ffmpeg
def test_audio_writes_audio_and_keeps_the_markdown(lib, paper):
    assert main(["audio", str(paper), "-q", "--library", str(lib.root)]) == 0
    assert lib.audio_path("on-reading-things").is_file()
    assert lib.markdown_path("on-reading-things").is_file()


@needs_ffmpeg
def test_audio_reuses_edited_markdown_verbatim(lib, paper, backend):
    """Edit the Markdown, convert it, and hear what you typed."""
    main(["text", str(paper), "--library", str(lib.root)])
    md = lib.markdown_path("on-reading-things")
    md.write_text(md.read_text().replace("We did the thing", "We did something else"),
                  encoding="utf-8")

    backend.calls.clear()
    assert main(["audio", str(md), "-q", "--library", str(lib.root)]) == 0
    spoken = " ".join(backend.calls)
    assert "We did something else" in spoken
    assert "We did the thing" not in spoken


def test_dry_run_synthesizes_nothing(lib, paper, backend, capsys):
    assert main(["audio", str(paper), "--dry-run", "--library", str(lib.root)]) == 0
    assert backend.calls == []
    assert not lib.audio_path("on-reading-things").exists()
    assert "chunks" in capsys.readouterr().out


@needs_ffmpeg
def test_publish_puts_it_on_the_feed(lib, paper, capsys):
    assert main(["publish", str(paper), "-q", "--library", str(lib.root)]) == 0
    assert lib.feed_path.is_file()
    assert lib.state_path.is_file()
    assert lib.audio_path("on-reading-things").is_file()
    xml = lib.feed_path.read_text()
    assert "https://example.com/audio/audio/on-reading-things.mp3" in xml
    assert "https://example.com/audio/feed.xml" in capsys.readouterr().out


@needs_ffmpeg
def test_publish_an_mp3_synthesizes_nothing(lib, paper, backend, capsys):
    main(["audio", str(paper), "-q", "--library", str(lib.root)])
    made = lib.audio_path("on-reading-things")
    backend.calls.clear()

    assert main(["publish", str(made), "--title", "A Talk", "-q",
                 "--library", str(lib.root)]) == 0
    assert backend.calls == []
    assert "A Talk" in lib.feed_path.read_text()


@needs_ffmpeg
def test_publishing_twice_does_not_duplicate_the_episode(lib, paper):
    from earmark.feed import FeedState

    for _ in range(2):
        main(["publish", str(paper), "-q", "--library", str(lib.root)])
    state = FeedState.from_json(lib.state_path.read_text())
    assert len(state.episodes) == 1


@needs_ffmpeg
def test_the_after_publish_hook_runs_in_the_library(lib, paper):
    lib.config_path.write_text(
        'after_publish = "pwd > ran.txt"\n' + lib.config_path.read_text(), encoding="utf-8"
    )
    assert main(["publish", str(paper), "-q", "--library", str(lib.root)]) == 0
    assert (lib.root / "ran.txt").read_text().strip() == str(lib.root)


@needs_ffmpeg
def test_feed_lists_what_is_published(lib, paper, capsys):
    main(["publish", str(paper), "-q", "--library", str(lib.root)])
    capsys.readouterr()
    assert main(["feed", "--library", str(lib.root)]) == 0
    out = capsys.readouterr().out
    assert "On Reading Things" in out
    assert "https://example.com/audio/feed.xml" in out


def test_feed_is_honest_about_an_empty_library(lib, capsys):
    assert main(["feed", "--library", str(lib.root)]) == 0
    assert "nothing published yet" in capsys.readouterr().out


def test_a_setting_appended_to_the_config_warns_rather_than_vanishing(lib, capsys):
    """TOML puts a trailing key inside the last table, so the last table has to
    be one whose unknown keys are reported."""
    lib.config_path.write_text(
        lib.config_path.read_text() + '\nafter_publish = "true"\n', encoding="utf-8"
    )
    main(["feed", "--library", str(lib.root)])
    assert "feed.after_publish" in capsys.readouterr().err


def test_prune_needs_to_be_told_what_to_keep(lib, capsys):
    assert main(["feed", "--prune", "--library", str(lib.root)]) == 1
    assert "--keep" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["text", "x.pdf", "--library", "/tmp/L"],
    ["--library", "/tmp/L", "text", "x.pdf"],
])
def test_library_works_on_either_side_of_the_verb(argv):
    """A subparser writes its defaults over the parent's namespace, so the
    global flag before the verb is the one that silently goes missing."""
    assert parse(argv).library == "/tmp/L"


def test_library_defaults_to_none():
    assert parse(["text", "x.pdf"]).library is None


# -- signposting ----------------------------------------------------------


def test_help_shows_the_pipeline_in_order(capsys):
    main([])
    out = capsys.readouterr().out
    assert out.index("earmark text") < out.index("earmark audio") < out.index("earmark publish")
    assert "all of the above" in out


def test_help_says_publish_runs_the_whole_chain(capsys):
    main([])
    assert "publish runs the whole chain" in capsys.readouterr().out


def test_text_points_at_the_next_step(lib, paper, capsys):
    main(["text", str(paper), "--library", str(lib.root)])
    err = capsys.readouterr().err
    assert "earmark publish" in err
    assert lib.markdown_path("on-reading-things").name in err


@needs_ffmpeg
def test_audio_points_at_the_next_step(lib, paper, capsys):
    main(["audio", str(paper), "-q", "--library", str(lib.root)])
    assert "earmark publish" in capsys.readouterr().err


def test_the_hint_stays_off_stdout(lib, paper, capsys):
    """`earmark text x.pdf | pbcopy` has to stay clean."""
    main(["text", str(paper), "--library", str(lib.root)])
    captured = capsys.readouterr()
    assert "earmark publish" not in captured.out
    assert captured.out.strip().endswith("words)")


@needs_ffmpeg
def test_publish_needs_no_earlier_step(lib, paper):
    """Handed only a source, publish does all three steps itself."""
    assert main(["publish", str(paper), "-q", "--library", str(lib.root)]) == 0
    assert lib.markdown_path("on-reading-things").is_file()
    assert lib.audio_path("on-reading-things").is_file()
    assert lib.feed_path.is_file()


def test_the_command_names_are_the_folder_names(lib):
    """`ls` should teach the pipeline as well as --help does."""
    assert lib.text_dir.name == "text"
    assert lib.audio_dir.name == "audio"


def test_paths_print_relative_to_where_you_are(lib, paper, monkeypatch, capsys):
    """Inside the library, `text/a-paper.md` is both shorter and what you type."""
    monkeypatch.chdir(lib.root)
    main(["text", str(paper)])
    out = capsys.readouterr().out
    assert out.startswith("text/on-reading-things.md")


def test_a_path_outside_the_working_directory_stays_absolute(lib, paper, monkeypatch,
                                                             tmp_path, capsys):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    main(["text", str(paper), "--library", str(lib.root)])
    assert str(lib.markdown_path("on-reading-things")) in capsys.readouterr().out
