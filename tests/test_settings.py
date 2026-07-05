"""Tests for mashpad.settings — pure logic, no pygame."""

import json
import sys

from mashpad.settings import Settings, load, save


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

def test_defaults():
    s = Settings()
    assert s.voice_mode == "random"
    assert s.volume == 80
    assert s.letter_case == "upper"
    assert s.raccoon_amount == "normal"


# ---------------------------------------------------------------------------
# load — missing / malformed input → defaults
# ---------------------------------------------------------------------------

def test_missing_file_returns_defaults(tmp_path):
    assert load(tmp_path / "nope.json") == Settings()


def test_bad_json_returns_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{ this is not json", encoding="utf-8")
    assert load(p) == Settings()


def test_non_dict_json_returns_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("[1, 2, 3]", encoding="utf-8")
    assert load(p) == Settings()


# ---------------------------------------------------------------------------
# Roundtrip
# ---------------------------------------------------------------------------

def test_roundtrip(tmp_path):
    p = tmp_path / "settings.json"
    s = Settings(voice_mode="puck", volume=50, letter_case="lower", raccoon_amount="lots")
    save(s, p)
    assert load(p) == s


def test_save_writes_four_keys(tmp_path):
    p = tmp_path / "settings.json"
    save(Settings(), p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data) == {"voice_mode", "volume", "letter_case", "raccoon_amount"}


def test_save_atomic_leaves_no_tmp(tmp_path):
    p = tmp_path / "settings.json"
    save(Settings(), p)
    assert p.exists()
    assert not (tmp_path / "settings.json.tmp").exists()


# ---------------------------------------------------------------------------
# Field-wise validation — one bad field never discards the valid siblings
# ---------------------------------------------------------------------------

def test_fieldwise_invalid_defaults_only_bad_fields(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({
        "voice_mode": "puck",       # valid → kept
        "volume": 999,              # out of range → default 80
        "letter_case": "sideways",  # invalid → default "upper"
        "raccoon_amount": "lots",   # valid → kept
    }), encoding="utf-8")
    s = load(p)
    assert s.voice_mode == "puck"
    assert s.volume == 80
    assert s.letter_case == "upper"
    assert s.raccoon_amount == "lots"


def test_volume_bool_rejected(tmp_path):
    # JSON true decodes to Python bool (an int subclass) — must be rejected.
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"volume": True}), encoding="utf-8")
    assert load(p).volume == 80


def test_volume_wrong_type_rejected(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"volume": "loud"}), encoding="utf-8")
    assert load(p).volume == 80


def test_volume_boundaries_accepted(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"volume": 0}), encoding="utf-8")
    assert load(p).volume == 0
    p.write_text(json.dumps({"volume": 100}), encoding="utf-8")
    assert load(p).volume == 100


def test_empty_voice_mode_rejected(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"voice_mode": ""}), encoding="utf-8")
    assert load(p).voice_mode == "random"


def test_empty_dict_gives_defaults(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{}", encoding="utf-8")
    assert load(p) == Settings()


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_settings_no_pygame():
    import mashpad.settings  # noqa: F401
    assert "pygame" not in sys.modules, "settings imported pygame!"
