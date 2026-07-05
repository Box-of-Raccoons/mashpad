# DuckWindow — the pure envelope behind phrase audio ducking.

import sys

from mashpad import config
from mashpad.duck import DuckWindow

F = config.PHRASE_DUCK_FACTOR
LEAD = config.PHRASE_LEAD_S
DOWN = config.PHRASE_DUCK_FADE_DOWN_S
UP = config.PHRASE_DUCK_FADE_UP_S
TAIL = config.PHRASE_DUCK_TAIL_S


def test_no_window_is_full_volume():
    duck = DuckWindow()
    assert duck.factor(0.0) == 1.0
    assert duck.factor(1000.0) == 1.0


def test_open_returns_phrase_start_after_lead():
    duck = DuckWindow()
    assert duck.open(10.0, 2.0) == 10.0 + LEAD


def test_envelope_shape():
    duck = DuckWindow()
    start = duck.open(10.0, 2.0)          # phrase speaks [10+LEAD, 12+LEAD]
    hold_end = start + 2.0 + TAIL
    # fade down: halfway through the fade sits halfway between 1.0 and F
    assert duck.factor(10.0) == 1.0
    mid = duck.factor(10.0 + DOWN / 2)
    assert abs(mid - (1.0 + F) / 2) < 1e-9
    # fully ducked through the lead, the phrase, and the tail
    assert duck.factor(10.0 + DOWN) == F
    assert duck.factor(start + 1.0) == F
    assert duck.factor(hold_end - 0.01) == F
    # fade up: halfway back at half the fade-up time
    mid_up = duck.factor(hold_end + UP / 2)
    assert abs(mid_up - (1.0 + F) / 2) < 1e-9
    assert duck.factor(hold_end + UP + 0.01) == 1.0


def test_reopening_extends_without_popping():
    duck = DuckWindow()
    start1 = duck.open(10.0, 1.0)
    # a second phrase (e.g. exempt 'hello') opens while still ducked
    t2 = start1 + 0.5
    duck.open(t2, 2.0)
    # no fade-down restart: still fully ducked right after the second open
    assert duck.factor(t2 + 0.01) == F
    # and the hold now extends past the second phrase's end
    assert duck.factor(t2 + LEAD + 1.9) == F


def test_duck_no_pygame():
    import mashpad.duck  # noqa: F401
    assert "pygame" not in sys.modules, "duck imported pygame!"
