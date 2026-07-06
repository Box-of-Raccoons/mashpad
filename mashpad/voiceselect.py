# mashpad/voiceselect.py — chooses which voice pack speaks each spawn.
#
# Pure — no pygame imports (joins the purity test). The app injects the live
# voice list (from Audio.voices), the mode (from Settings.voice_mode), a
# gender map (from config.VOICE_INFO) and a seeded Random so behaviour is
# reproducible in tests.

from __future__ import annotations

import random as _random

from mashpad import settings as settings_mod


class VoiceSelector:
    """Tracks the active voice-pack name for a given mode.

    Modes:
      * "random" — pick a random voice on every on_keystroke().
      * "cycle"  — the current voice stays put across keystrokes; on_trigger()
                   advances to the next voice, preferring a gender change so the
                   app alternates male/female voices as it comments.
      * a voice name in the list — always that voice.
      * anything else (unknown name) — behaves like "random".
    """

    def __init__(self, voices, mode: str, genders, rng: "_random.Random") -> None:
        self._voices = list(voices)
        self._mode = mode
        # voice name → "male" | "female" | None (unknown packs have None).
        self._genders = dict(genders or {})
        self._rng = rng
        self._cycle_index = 0    # index of the current voice in "cycle" mode
        self._current = self._initial()

    def _effective_mode(self) -> str:
        """Resolve the raw mode to one of: VOICE_MODE_RANDOM, VOICE_MODE_CYCLE, or a voice name."""
        if self._mode in (settings_mod.VOICE_MODE_RANDOM, settings_mod.VOICE_MODE_CYCLE):
            return self._mode
        if self._mode in self._voices:
            return self._mode          # a specific voice
        return settings_mod.VOICE_MODE_RANDOM                # unknown name → random fallback

    def _initial(self):
        """Seed .current() before the first keystroke."""
        if not self._voices:
            return None
        mode = self._effective_mode()
        if mode == settings_mod.VOICE_MODE_CYCLE:
            return self._voices[0]
        if mode == settings_mod.VOICE_MODE_RANDOM:
            return self._rng.choice(self._voices)
        return mode                    # fixed voice

    def current(self):
        """Return the active voice name, or None when there are no voices."""
        return self._current

    def on_keystroke(self) -> None:
        """Advance per-spawn selection state.

        In VOICE_MODE_CYCLE this is a no-op — the current voice only changes on a
        phrase trigger (see on_trigger).
        """
        if not self._voices:
            self._current = None
            return
        mode = self._effective_mode()
        if mode == settings_mod.VOICE_MODE_RANDOM:
            self._current = self._rng.choice(self._voices)
        elif mode == settings_mod.VOICE_MODE_CYCLE:
            return                     # trigger-driven; stays put per keystroke
        else:
            self._current = mode       # fixed voice — never changes

    def on_trigger(self) -> None:
        """Advance the voice when the app speaks a reactive phrase.

        Only VOICE_MODE_CYCLE rotates (no-op for VOICE_MODE_RANDOM / fixed). Rotation is
        round-robin from the current voice but prefers the next voice whose
        gender differs from the current one, so male/female alternate. If no
        voice has a differing known gender (all same, or genders unknown), it
        falls back to plain round-robin.
        """
        if not self._voices:
            self._current = None
            return
        if self._effective_mode() != settings_mod.VOICE_MODE_CYCLE:
            return
        n = len(self._voices)
        cur_gender = self._genders.get(self._current)
        chosen = None
        for step in range(1, n + 1):
            idx = (self._cycle_index + step) % n
            g = self._genders.get(self._voices[idx])
            # Accept when: next voice has unknown gender (it may be a gender change,
            # and excluding it forever is worse), OR the current voice's gender is
            # unknown (any next voice is a valid step), OR genders differ.
            # Reduces to `g != cur_gender` when all genders are known — same
            # alternation as before for the six curated packs.
            if g is None or cur_gender is None or g != cur_gender:
                chosen = idx
                break
        if chosen is None:
            chosen = (self._cycle_index + 1) % n   # plain round-robin fallback
        self._cycle_index = chosen
        self._current = self._voices[chosen]
