"""The config file: precedence, validation, and refusing to fail silently."""

from __future__ import annotations

import pytest

from earmark import config as config_mod
from earmark.config import Config, ConfigError, DEFAULTS, load


def write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_gives_defaults(tmp_path):
    cfg = load(tmp_path / "nope.toml")
    assert cfg.get("voice") == DEFAULTS["voice"]
    assert cfg.errors == [] and cfg.warnings == []


def test_scalars_override_defaults(tmp_path):
    cfg = load(write(tmp_path, 'voice = "am_michael"\nspeed = 1.25\n'))
    assert cfg.get("voice") == "am_michael"
    assert cfg.get("speed") == 1.25
    assert cfg.get("lang") == DEFAULTS["lang"]


def test_profile_accepted_at_top_level_or_under_clean(tmp_path):
    assert load(write(tmp_path, 'profile = "paper"\n')).get("profile") == "paper"
    assert load(write(tmp_path, '[clean]\nprofile = "book"\n')).get("profile") == "book"


def test_clean_replace_table(tmp_path):
    cfg = load(write(tmp_path, '[clean.replace]\nBEV = "battery electric vehicle"\n'))
    assert cfg.replace == {"BEV": "battery electric vehicle"}


def test_feed_section_passed_through(tmp_path):
    cfg = load(write(tmp_path, '[feed]\npublisher = "folder"\nbase_url = "https://x/y"\n'))
    assert cfg.feed["publisher"] == "folder"


def test_unknown_key_warns_rather_than_vanishing(tmp_path):
    """The failure this guards against: a typo'd setting changes nothing and
    says nothing, so the user has no way to find out why."""
    cfg = load(write(tmp_path, 'vioce = "af_bella"\n'))
    assert any("vioce" in w for w in cfg.warnings)
    assert cfg.errors == []


def test_unknown_section_warns(tmp_path):
    cfg = load(write(tmp_path, '[voices]\nfavourite = "af_heart"\n'))
    assert any("[voices]" in w for w in cfg.warnings)


def test_unknown_clean_key_warns(tmp_path):
    cfg = load(write(tmp_path, '[clean]\nkeep_tables = true\n'))
    assert any("clean.keep_tables" in w for w in cfg.warnings)


@pytest.mark.parametrize(
    "body,key",
    [
        ("speed = 3.0", "speed"),
        ("speed = 0.1", "speed"),
        ('speed = "fast"', "speed"),
        ('profile = "thesis"', "profile"),
        ('model = "tiny"', "model"),
        ('engine = "espeak"', "engine"),
        ('voice = ""', "voice"),
        ("sample_rate = 0", "sample_rate"),
        ("sample_rate = 44100.5", "sample_rate"),
    ],
)
def test_bad_values_are_errors(tmp_path, body, key):
    cfg = load(write(tmp_path, body + "\n"))
    assert any(key in e for e in cfg.errors), cfg.errors


def test_check_raises_naming_the_file(tmp_path):
    path = write(tmp_path, "speed = 9.0\n")
    cfg = load(path)
    with pytest.raises(ConfigError) as exc:
        cfg.check()
    assert str(path) in str(exc.value)
    assert "speed" in str(exc.value)


def test_check_is_silent_when_valid(tmp_path):
    load(write(tmp_path, 'voice = "af_bella"\n')).check()


def test_malformed_toml_is_an_error_not_a_crash(tmp_path):
    """A broken file must stay inspectable with `earmark config show`."""
    cfg = load(write(tmp_path, "voice = \n"))
    assert cfg.errors and "TOML" in cfg.errors[0]
    assert cfg.get("voice") == DEFAULTS["voice"]


def test_speed_bool_rejected(tmp_path):
    assert load(write(tmp_path, "speed = true\n")).errors


def test_replace_must_be_a_table(tmp_path):
    cfg = load(write(tmp_path, '[clean]\nreplace = "BEV"\n'))
    assert cfg.replace == {}
    assert cfg.warnings


def test_init_writes_a_parsable_template(tmp_path):
    path, written = config_mod.init(tmp_path / "config.toml")
    assert written
    cfg = load(path)
    assert cfg.errors == [] and cfg.warnings == []
    assert cfg.get("voice") == DEFAULTS["voice"]


def test_init_refuses_to_clobber(tmp_path):
    path = write(tmp_path, 'voice = "am_michael"\n')
    _, written = config_mod.init(path)
    assert not written
    assert load(path).get("voice") == "am_michael"
    _, written = config_mod.init(path, force=True)
    assert written
    assert load(path).get("voice") == DEFAULTS["voice"]


def test_no_setting_is_promised_without_being_read():
    """Every key in DEFAULTS must be one a command actually consults; `jobs`
    lived here for a while doing nothing."""
    import earmark.cli as cli

    source = cli.__file__
    text = open(source, encoding="utf-8").read()
    for key in DEFAULTS:
        assert f'"{key}"' in text, f"{key} is offered in config but never read"
