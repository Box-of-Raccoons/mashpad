# mashpad/voiceselect.py — chooses which voice pack speaks each spawn.
#
# Pure — no pygame imports (joins the purity test). The app injects the live
# voice list (from Audio.voices), the mode (from Settings.voice_mode) and a seeded
# Random so behaviour is reproducible in tests.

from __future__ import annotations

import random as _random


class VoiceSelector:
    """Tracks the active voice-pack name across keystrokes for a given mode.

    Modes:
      * "random" — pick a random voice on every on_keystroke().
      * "cycle"  — advance to the next voice (wrapping, list order) every
                   ``cycle_every`` keystrokes.
      * a voice name in the list — always that voice.
      * anything else (unknown name) — behaves like "random".
    """

    def __init__(self, voices, mode: str, cycle_every: int, rng: "_random.Random") -> None:
        self._voices = list(voices)
        self._mode = mode
        self._cycle_every = max(1, int(cycle_every))
        self._rng = rng
        self._count = 0          # keystrokes since the last cycle switch
        self._cycle_index = 0    # index of the current voice in "cycle" mode
        self._current = self._initial()

    def _effective_mode(self) -> str:
        """Resolve the raw mode to one of: 'random', 'cycle', or a voice name."""
        if self._mode in ("random", "cycle"):
            return self._mode
        if self._mode in self._voices:
            return self._mode          # a specific voice
        return "random"                # unknown name → random fallback

    def _initial(self):
        """Seed .current() before the first keystroke."""
        if not self._voices:
            return None
        mode = self._effective_mode()
        if mode == "cycle":
            return self._voices[0]
        if mode == "random":
            return self._rng.choice(self._voices)
        return mode                    # fixed voice

    def current(self):
        """Return the active voice name, or None when there are no voices."""
        return self._current

    def on_keystroke(self) -> None:
        """Advance selection state for one spawn."""
        if not self._voices:
            self._current = None
            return
        mode = self._effective_mode()
        if mode == "cycle":
            self._count += 1
            if self._count >= self._cycle_every:
                self._count = 0
                self._cycle_index = (self._cycle_index + 1) % len(self._voices)
                self._current = self._voices[self._cycle_index]
        elif mode == "random":
            self._current = self._rng.choice(self._voices)
        else:
            self._current = mode       # fixed voice — never changes
