"""Tests for mashpad.voiceselect — pure logic, no pygame."""

import random
import sys

from mashpad.voiceselect import VoiceSelector


def _rng(seed=0):
    return random.Random(seed)


# 3-male / 3-female set mirroring the real voice packs.
_MF = ["m1", "m2", "m3", "f1", "f2", "f3"]
_MF_GENDERS = {
    "m1": "male", "m2": "male", "m3": "male",
    "f1": "female", "f2": "female", "f3": "female",
}


# ---------------------------------------------------------------------------
# Empty voice list
# ---------------------------------------------------------------------------

def test_empty_voices_current_none():
    sel = VoiceSelector([], "random", {}, _rng())
    assert sel.current() is None
    for _ in range(20):
        sel.on_keystroke()
        assert sel.current() is None


def test_empty_voices_cycle_none():
    sel = VoiceSelector([], "cycle", {}, _rng())
    assert sel.current() is None
    sel.on_keystroke()
    assert sel.current() is None
    sel.on_trigger()
    assert sel.current() is None


# ---------------------------------------------------------------------------
# Fixed voice name
# ---------------------------------------------------------------------------

def test_fixed_voice_always_same():
    sel = VoiceSelector(["a", "b", "c"], "b", {}, _rng())
    assert sel.current() == "b"
    for _ in range(50):
        sel.on_keystroke()
        assert sel.current() == "b"


def test_fixed_voice_ignores_trigger():
    sel = VoiceSelector(["a", "b", "c"], "b", {}, _rng())
    for _ in range(10):
        sel.on_trigger()
        assert sel.current() == "b"


# ---------------------------------------------------------------------------
# Unknown voice name → random fallback
# ---------------------------------------------------------------------------

def test_unknown_voice_falls_back_to_random():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "does-not-exist", {}, _rng(1))
    seen = set()
    for _ in range(300):
        sel.on_keystroke()
        assert sel.current() in voices
        seen.add(sel.current())
    assert len(seen) > 1, "unknown-name fallback should behave randomly, not stick"


# ---------------------------------------------------------------------------
# Random mode
# ---------------------------------------------------------------------------

def test_random_stays_in_list():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "random", {}, _rng(1))
    for _ in range(300):
        sel.on_keystroke()
        assert sel.current() in voices


def test_random_reaches_all_voices():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "random", {}, _rng(1))
    seen = set()
    for _ in range(300):
        sel.on_keystroke()
        seen.add(sel.current())
    assert seen == set(voices)


def test_random_ignores_trigger():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "random", {}, _rng(1))
    before = sel.current()
    sel.on_trigger()
    assert sel.current() == before  # on_trigger is a no-op in random mode


# ---------------------------------------------------------------------------
# Cycle mode — keystrokes no longer advance; triggers do
# ---------------------------------------------------------------------------

def test_cycle_initial_is_first_voice():
    sel = VoiceSelector(["a", "b", "c"], "cycle", {}, _rng())
    assert sel.current() == "a"


def test_cycle_keystrokes_do_not_advance():
    sel = VoiceSelector(["a", "b", "c"], "cycle", _MF_GENDERS, _rng())
    for _ in range(100):
        sel.on_keystroke()
        assert sel.current() == "a"  # the current voice stays put across keys


def test_cycle_single_voice_stays():
    sel = VoiceSelector(["only"], "cycle", {}, _rng())
    assert sel.current() == "only"
    for _ in range(10):
        sel.on_keystroke()
        sel.on_trigger()
        assert sel.current() == "only"


def test_cycle_trigger_alternates_gender():
    sel = VoiceSelector(_MF, "cycle", _MF_GENDERS, _rng())
    assert sel.current() == "m1"  # male
    genders = []
    for _ in range(6):
        sel.on_trigger()
        genders.append(_MF_GENDERS[sel.current()])
    # Every step flips male<->female (starting from a male current).
    assert genders == ["female", "male", "female", "male", "female", "male"]
    # And it lands on real voices from the list each time.
    sel2 = VoiceSelector(_MF, "cycle", _MF_GENDERS, _rng())
    for _ in range(6):
        sel2.on_trigger()
        assert sel2.current() in _MF


def test_cycle_trigger_all_one_gender_round_robin():
    voices = ["a", "b", "c"]
    genders = {"a": "male", "b": "male", "c": "male"}
    sel = VoiceSelector(voices, "cycle", genders, _rng())
    seq = []
    for _ in range(4):
        sel.on_trigger()
        seq.append(sel.current())
    assert seq == ["b", "c", "a", "b"]  # plain round-robin, no gender to alternate


def test_cycle_trigger_no_genders_round_robin():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "cycle", {}, _rng())
    seq = []
    for _ in range(4):
        sel.on_trigger()
        seq.append(sel.current())
    assert seq == ["b", "c", "a", "b"]  # unknown genders → plain round-robin


# ---------------------------------------------------------------------------
# Cycle mode — unknown-gender voice participates in rotation (Fix 3)
# ---------------------------------------------------------------------------

def test_cycle_unknown_gender_selected_within_one_rotation():
    """An unknown-gender voice is accepted as a gender-change candidate and is
    selected within one full rotation through all voices.
    """
    voices = ["m1", "m2", "m3", "f1", "f2", "f3", "unk"]
    genders = {
        "m1": "male",   "m2": "male",   "m3": "male",
        "f1": "female", "f2": "female", "f3": "female",
        # "unk" intentionally absent → gender is None
    }
    sel = VoiceSelector(voices, "cycle", genders, _rng())
    assert sel.current() == "m1"
    selected = []
    for _ in range(len(voices)):
        sel.on_trigger()
        selected.append(sel.current())
    assert "unk" in selected, "unknown-gender voice was never selected in one full rotation"


def test_cycle_known_gender_alternation_unchanged_with_six_voices():
    """The 6-voice all-known male/female alternation is unaffected by the fix."""
    sel = VoiceSelector(_MF, "cycle", _MF_GENDERS, _rng())
    assert sel.current() == "m1"
    genders_seq = []
    for _ in range(6):
        sel.on_trigger()
        genders_seq.append(_MF_GENDERS[sel.current()])
    assert genders_seq == ["female", "male", "female", "male", "female", "male"]


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_voiceselect_no_pygame():
    import mashpad.voiceselect  # noqa: F401
    assert "pygame" not in sys.modules, "voiceselect imported pygame!"
