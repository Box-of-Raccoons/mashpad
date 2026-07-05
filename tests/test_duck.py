# DuckWindow — the pure timing logic behind phrase audio ducking.

import sys

from mashpad import config
from mashpad.duck import DuckWindow


def test_closed_window_is_full_volume():
    duck = DuckWindow()
    assert duck.factor(0.0) == 1.0
    assert duck.factor(1000.0) == 1.0


def test_open_window_ducks_until_duration_plus_tail():
    duck = DuckWindow()
    duck.open(10.0, 2.0)  # phrase clip of 2s starting at t=10
    assert duck.factor(10.0) == config.PHRASE_DUCK_FACTOR
    assert duck.factor(11.9) == config.PHRASE_DUCK_FACTOR
    # still inside the tail
    assert duck.factor(12.0 + config.PHRASE_DUCK_TAIL_S - 0.01) == config.PHRASE_DUCK_FACTOR
    # past duration + tail
    assert duck.factor(12.0 + config.PHRASE_DUCK_TAIL_S + 0.01) == 1.0


def test_reopening_extends_the_window():
    duck = DuckWindow()
    duck.open(10.0, 1.0)
    duck.open(10.5, 2.0)  # a second phrase (e.g. exempt 'hello') re-opens
    assert duck.factor(12.4) == config.PHRASE_DUCK_FACTOR


def test_duck_no_pygame():
    import mashpad.duck  # noqa: F401
    assert "pygame" not in sys.modules, "duck imported pygame!"
