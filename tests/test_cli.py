"""The two convenience spellings on the command line.

`earmark SOURCE` and `earmark publish SOURCE` are the whole point of the tool
being pleasant to use, so they get a test rather than being folded into main()
where nothing can reach them.
"""

from __future__ import annotations

import pytest

from earmark.cli import build_parser, normalize


def parse(argv):
    return build_parser().parse_args(normalize(argv))


def test_a_bare_source_means_read():
    assert normalize(["paper.pdf"]) == ["read", "paper.pdf"]


def test_publish_is_read_with_the_flag():
    args = parse(["publish", "https://example.com/a"])
    assert args.command == "read"
    assert args.source == "https://example.com/a"
    assert args.publish is True


def test_publish_keeps_the_rest_of_the_options():
    args = parse(["publish", "paper.pdf", "--profile", "paper", "-s", "1.2"])
    assert (args.profile, args.speed, args.publish) == ("paper", 1.2, True)


def test_publish_tolerates_the_flag_being_passed_too():
    assert parse(["publish", "paper.pdf", "--publish"]).publish is True


@pytest.mark.parametrize("name", ["text", "voices", "models", "cache", "feed", "config"])
def test_real_subcommands_are_left_alone(name):
    assert normalize([name])[0] == name


def test_an_option_first_is_not_mistaken_for_a_source():
    assert normalize(["--version"]) == ["--version"]
