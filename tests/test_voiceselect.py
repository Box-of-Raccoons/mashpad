"""Tests for mashpad.voiceselect — pure logic, no pygame."""

import random
import sys

from mashpad.voiceselect import VoiceSelector


def _rng(seed=0):
    return random.Random(seed)


# ---------------------------------------------------------------------------
# Empty voice list
# ---------------------------------------------------------------------------

def test_empty_voices_current_none():
    sel = VoiceSelector([], "random", 10, _rng())
    assert sel.current() is None
    for _ in range(20):
        sel.on_keystroke()
        assert sel.current() is None


def test_empty_voices_cycle_none():
    sel = VoiceSelector([], "cycle", 3, _rng())
    assert sel.current() is None
    sel.on_keystroke()
    assert sel.current() is None


# ---------------------------------------------------------------------------
# Fixed voice name
# ---------------------------------------------------------------------------

def test_fixed_voice_always_same():
    sel = VoiceSelector(["a", "b", "c"], "b", 10, _rng())
    assert sel.current() == "b"
    for _ in range(50):
        sel.on_keystroke()
        assert sel.current() == "b"


# ---------------------------------------------------------------------------
# Unknown voice name → random fallback
# ---------------------------------------------------------------------------

def test_unknown_voice_falls_back_to_random():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "does-not-exist", 10, _rng(1))
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
    sel = VoiceSelector(voices, "random", 10, _rng(1))
    for _ in range(300):
        sel.on_keystroke()
        assert sel.current() in voices


def test_random_reaches_all_voices():
    voices = ["a", "b", "c"]
    sel = VoiceSelector(voices, "random", 10, _rng(1))
    seen = set()
    for _ in range(300):
        sel.on_keystroke()
        seen.add(sel.current())
    assert seen == set(voices)


# ---------------------------------------------------------------------------
# Cycle mode — every-N boundary + wrap
# ---------------------------------------------------------------------------

def test_cycle_advances_every_n_and_wraps():
    sel = VoiceSelector(["a", "b", "c"], "cycle", 3, _rng())
    assert sel.current() == "a"  # initial
    seq = []
    for _ in range(9):
        sel.on_keystroke()
        seq.append(sel.current())
    # Switch happens on the 3rd, 6th, 9th keystroke; wraps c → a at #9.
    assert seq == ["a", "a", "b", "b", "b", "c", "c", "c", "a"]


def test_cycle_every_one_switches_each_keystroke():
    sel = VoiceSelector(["a", "b"], "cycle", 1, _rng())
    assert sel.current() == "a"
    seq = []
    for _ in range(4):
        sel.on_keystroke()
        seq.append(sel.current())
    assert seq == ["b", "a", "b", "a"]


def test_cycle_single_voice_stays():
    sel = VoiceSelector(["only"], "cycle", 2, _rng())
    assert sel.current() == "only"
    for _ in range(10):
        sel.on_keystroke()
        assert sel.current() == "only"


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_voiceselect_no_pygame():
    import mashpad.voiceselect  # noqa: F401
    assert "pygame" not in sys.modules, "voiceselect imported pygame!"
