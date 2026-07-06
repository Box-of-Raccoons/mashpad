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
    assert s.phrases is True
    assert s.sound_mode == "piano"


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
    s = Settings(voice_mode="puck", volume=50, letter_case="lower",
                 raccoon_amount="lots", phrases=False, sound_mode="dings")
    save(s, p)
    assert load(p) == s


def test_save_writes_all_keys(tmp_path):
    p = tmp_path / "settings.json"
    save(Settings(), p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data) == {
        "voice_mode", "volume", "letter_case", "raccoon_amount", "phrases",
        "sound_mode",
    }


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
# phrases — strict bool
# ---------------------------------------------------------------------------

def test_phrases_bool_accepted(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"phrases": False}), encoding="utf-8")
    assert load(p).phrases is False
    p.write_text(json.dumps({"phrases": True}), encoding="utf-8")
    assert load(p).phrases is True


def test_phrases_non_bool_rejected(tmp_path):
    # Non-bool values (int, string) fall back to the default True.
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"phrases": 0}), encoding="utf-8")
    assert load(p).phrases is True
    p.write_text(json.dumps({"phrases": "off"}), encoding="utf-8")
    assert load(p).phrases is True


# ---------------------------------------------------------------------------
# sound_mode — piano | dings, else default
# ---------------------------------------------------------------------------

def test_sound_mode_accepted(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"sound_mode": "dings"}), encoding="utf-8")
    assert load(p).sound_mode == "dings"
    p.write_text(json.dumps({"sound_mode": "piano"}), encoding="utf-8")
    assert load(p).sound_mode == "piano"


def test_sound_mode_invalid_defaults_to_piano(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"sound_mode": "kazoo"}), encoding="utf-8")
    assert load(p).sound_mode == "piano"


def test_sound_mode_missing_defaults_to_piano(tmp_path):
    # An older settings file written before this field existed → default piano.
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"volume": 50}), encoding="utf-8")
    assert load(p).sound_mode == "piano"


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_settings_no_pygame():
    import mashpad.settings  # noqa: F401
    assert "pygame" not in sys.modules, "settings imported pygame!"


# ---------------------------------------------------------------------------
# save() error handling — OSError must not propagate; tmp cleaned up
# ---------------------------------------------------------------------------

def test_save_returns_false_when_parent_is_file(tmp_path):
    """save() returns False (does not raise) when the target dir is a file."""
    # Write a regular file at a path we then use as a "directory" — any open()
    # inside save() will fail with NotADirectoryError (an OSError subclass).
    bad_dir = tmp_path / "f"
    bad_dir.write_text("not a directory", encoding="utf-8")
    result = save(Settings(), bad_dir / "settings.json")
    assert result is False


def test_save_no_orphan_tmp_on_failure(tmp_path):
    """save() cleans up the tmp file (if any) when it fails to write."""
    bad_dir = tmp_path / "f"
    bad_dir.write_text("not a directory", encoding="utf-8")
    target = bad_dir / "settings.json"
    save(Settings(), target)
    # The tmp file lives alongside the target; neither should exist after failure.
    assert not (bad_dir / "settings.json.tmp").exists()


def test_save_returns_true_on_success(tmp_path):
    """save() returns True when the write succeeds."""
    result = save(Settings(), tmp_path / "settings.json")
    assert result is True
