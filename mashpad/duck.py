# mashpad/duck.py — pure timing for phrase audio ducking.
#
# While a reactive phrase is speaking, every other sound plays quietly so the
# phrase is audible over the letter/effect bed. This module holds only the
# window arithmetic; audio.py applies the factor to mixer channels. Pure — no
# pygame imports (joins the purity test). Time is passed in by the caller.

from __future__ import annotations

from mashpad import config


class DuckWindow:
    """Tracks the interval during which non-phrase audio plays quietly."""

    def __init__(self) -> None:
        self._until = 0.0

    def open(self, now: float, duration: float) -> None:
        """Open (or extend) the window for *duration* seconds plus the tail."""
        self._until = max(self._until, now + duration + config.PHRASE_DUCK_TAIL_S)

    def factor(self, now: float) -> float:
        """Channel volume for non-phrase audio at *now*."""
        return config.PHRASE_DUCK_FACTOR if now < self._until else 1.0
