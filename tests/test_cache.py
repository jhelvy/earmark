import numpy as np

from earmark import cache


def test_key_changes_with_every_input():
    base = dict(text="hello", fingerprint="fp/1", voice="af_heart", speed=1.0, lang="en-us")
    baseline = cache.key(**base)
    assert cache.key(**{**base, "text": "hello!"}) != baseline
    assert cache.key(**{**base, "fingerprint": "fp/2"}) != baseline
    assert cache.key(**{**base, "voice": "af_bella"}) != baseline
    assert cache.key(**{**base, "speed": 1.1}) != baseline
    assert cache.key(**{**base, "lang": "en-gb"}) != baseline
    assert cache.key(**base) == baseline


def test_key_includes_the_clean_schema_version(monkeypatch):
    base = dict(text="hi", fingerprint="f", voice="v", speed=1.0, lang="en-us")
    before = cache.key(**base)
    monkeypatch.setattr(cache, "CLEAN_SCHEMA_VERSION", "999")
    assert cache.key(**base) != before


def test_round_trip():
    samples = np.linspace(-1, 1, 500, dtype=np.float32)
    key = cache.key("t", "f", "v", 1.0, "en-us")
    assert cache.get(key) is None
    cache.put(key, samples)
    # 16-bit quantization: transparent, but not bit-exact.
    np.testing.assert_allclose(cache.get(key), samples, atol=1 / 32767)


def test_info_and_clear():
    for i in range(3):
        cache.put(cache.key(f"t{i}", "f", "v", 1.0, "en-us"), np.zeros(100, dtype=np.float32))
    assert cache.info()["count"] == 3
    removed, freed = cache.clear()
    assert removed == 3 and freed == 3 * 200
    assert cache.info()["count"] == 0


def test_clear_respects_age():
    cache.put(cache.key("fresh", "f", "v", 1.0, "en-us"), np.zeros(10, dtype=np.float32))
    removed, _ = cache.clear(older_than_days=30)
    assert removed == 0
    assert cache.info()["count"] == 1


def test_legacy_float32_entries_are_still_cleanable():
    key = cache.key("old", "f", "v", 1.0, "en-us")
    legacy = cache.path_for(key).with_suffix(".f32")
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_bytes(b"\x00" * 400)
    assert cache.info()["count"] == 1
    removed, _ = cache.clear()
    assert removed == 1
