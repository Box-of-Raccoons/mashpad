# mashpad/duck.py — pure timing/volume envelope for phrase audio ducking.
#
# While a reactive phrase is speaking, every other sound plays quietly so the
# phrase is audible over the letter/effect bed. The envelope avoids sharp
# volume steps and gives the bed time to get out of the way BEFORE the phrase
# starts:
#
#   open(t0) → bed fades 1.0 → FACTOR over FADE_DOWN_S
#            → phrase starts at t0 + PHRASE_LEAD_S (returned to the caller)
#            → bed holds at FACTOR until phrase end + TAIL_S
#            → bed fades back to 1.0 over FADE_UP_S
#
# This module holds only the arithmetic; audio.py applies factor() to mixer
# channels once per frame. Pure — no pygame imports (joins the purity test).
# Time is passed in by the caller.

from __future__ import annotations

from mashpad import config


class DuckWindow:
    """Volume envelope for the non-phrase bed around a spoken phrase."""

    def __init__(self) -> None:
        self._fade_start: float | None = None  # None → no window ever opened
        self._hold_end = 0.0                   # phrase end + tail

    def open(self, now: float, duration: float) -> float:
        """Open (or extend) the envelope for a phrase of *duration* seconds.

        Returns the time the phrase should start speaking (now + lead). A
        window opened while one is still active keeps the original fade-down
        anchor so the bed volume never pops back up between phrases.
        """
        if self._fade_start is None or now >= self._hold_end + config.PHRASE_DUCK_FADE_UP_S:
            self._fade_start = now
        start = now + config.PHRASE_LEAD_S
        self._hold_end = max(self._hold_end, start + duration + config.PHRASE_DUCK_TAIL_S)
        return start

    def release(self, now: float) -> None:
        """End the hold at *now* so the fade-up starts immediately.

        Cancelling an utterance stops the speech but leaves _hold_end at the dead
        utterance's precomputed end — for a long ask that would mute the bed for
        tens of seconds after the round already changed. _fade_start is left
        alone so factor() still ramps over FADE_UP_S instead of snapping to 1.0.
        """
        if self._fade_start is None:
            return                 # nothing ever opened — nothing to release
        self._hold_end = min(self._hold_end, now)

    def factor(self, now: float) -> float:
        """Bed (non-phrase) channel volume at *now*, in [FACTOR, 1.0]."""
        if self._fade_start is None or now < self._fade_start:
            return 1.0
        low = config.PHRASE_DUCK_FACTOR
        down_end = self._fade_start + config.PHRASE_DUCK_FADE_DOWN_S
        if now < down_end:
            frac = (now - self._fade_start) / config.PHRASE_DUCK_FADE_DOWN_S
            return 1.0 - (1.0 - low) * frac
        if now < self._hold_end:
            return low
        up_end = self._hold_end + config.PHRASE_DUCK_FADE_UP_S
        if now < up_end:
            frac = (now - self._hold_end) / config.PHRASE_DUCK_FADE_UP_S
            return low + (1.0 - low) * frac
        return 1.0
