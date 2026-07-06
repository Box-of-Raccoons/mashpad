# mashpad/phrases.py — decides WHEN the app speaks a reactive phrase.
#
# Pure — no pygame imports (joins the purity test). All time is passed in from
# the caller; the module never reads the clock. main.py feeds it drops, spawns
# and cap hits, then calls poll() once per frame; audio.py plays the clip.
#
# Triggers: hello always wins; the rest take turns — the armed trigger heard
# least recently fires first (never-heard beats everything), so a busy session
# can't let slowdown/screenfull starve raccoons. Ties fall back to the order
# below.
#   * hello     — the startup splash displaying, or the first spawn after
#                 HELLO_IDLE_S idle. EXEMPT from the chance flip and the global
#                 cooldown: it should reliably greet.
#   * slowdown  — SLOWDOWN_DROPS rate-limiter drops within SLOWDOWN_WINDOW_S.
#   * screenfull— the item field force-faded because the MAX_ITEMS cap was hit.
#   * raccoons  — RACCOON_PILE_N or more image items live on screen.
#   * fun       — the spawn counter passed a random FUN_EVERY_SPAWNS threshold.

from __future__ import annotations

from mashpad import config

# Tie-break order for candidates that have never fired (hello always first).
_PRIORITY = ("hello", "slowdown", "screenfull", "raccoons", "fun")


class PhraseDirector:
    """Arms and fires phrase triggers, honouring cooldowns and a chance flip."""

    def __init__(self, rng, now: float) -> None:  # now param kept for call-site compat; not stored
        self._rng = rng
        # Armed triggers: {trigger: armed_time}.  Re-arming refreshes the time.
        self._pending: dict[str, float] = {}
        self._last_phrase_time = None      # global: last time ANY phrase fired
        self._last_fired: dict[str, float] = {}   # per-trigger last-fired time
        # slowdown: recent rate-limiter drop timestamps, trimmed to the window.
        self._drop_times: list[float] = []
        # fun: spawn counter + the random threshold it must pass to arm.
        self._spawn_count = 0
        self._fun_threshold = self._draw_fun()
        # hello: when did the last spawn happen (drives the idle re-greet).
        self._last_spawn_time = None

    def _draw_fun(self) -> int:
        lo, hi = config.FUN_EVERY_SPAWNS
        return self._rng.randint(lo, hi)

    # ---------------------------------------------------------------- feed-ins

    def note_drop(self, now: float) -> None:
        """Record a dropped (rate-limited) spawn; arm 'slowdown' on a burst."""
        cutoff = now - config.SLOWDOWN_WINDOW_S
        self._drop_times = [t for t in self._drop_times if t >= cutoff]
        self._drop_times.append(now)
        if len(self._drop_times) >= config.SLOWDOWN_DROPS:
            self._pending["slowdown"] = now

    def note_splash(self, now: float) -> None:
        """Record the startup splash displaying; arm 'hello' to greet."""
        self._pending["hello"] = now

    def note_spawn(self, now: float, raccoons_on_screen: int) -> None:
        """Record a successful spawn; drives hello / fun / raccoons."""
        # hello: first spawn after a long idle gap re-greets.
        if (self._last_spawn_time is not None
                and now - self._last_spawn_time >= config.HELLO_IDLE_S):
            self._pending["hello"] = now
        self._last_spawn_time = now
        # fun: arm when the counter passes its threshold, then re-draw.
        self._spawn_count += 1
        if self._spawn_count >= self._fun_threshold:
            self._pending["fun"] = now
            self._spawn_count = 0
            self._fun_threshold = self._draw_fun()
        # raccoons: a pile of image items on screen.
        if raccoons_on_screen >= config.RACCOON_PILE_N:
            self._pending["raccoons"] = now

    def note_cap_hit(self, now: float) -> None:
        """Record that the MAX_ITEMS cap force-faded an item; arm 'screenfull'."""
        self._pending["screenfull"] = now

    # -------------------------------------------------------------------- poll

    def poll(self, now: float) -> "str | None":
        """Return one trigger to speak, or None. At most one per call.

        hello is considered first and is exempt from the flip, the global
        cooldown, and arm expiry. The remaining armed candidates are considered
        least-recently-fired first (never-fired first of all, in _PRIORITY
        order), so variety self-balances. A non-hello candidate whose
        armed_time is more than PHRASE_ARM_TTL_S ago is silently expired and
        removed. A candidate blocked by a cooldown is skipped (stays armed for
        later). An eligible candidate must win a PHRASE_CHANCE coin flip; a
        lost flip discards that candidacy until it re-arms, and consideration
        falls through to the next candidate.
        """
        order = sorted(
            (t for t in _PRIORITY if t != "hello"),
            key=lambda t: (self._last_fired.get(t, float("-inf")), _PRIORITY.index(t)),
        )
        for trigger in ("hello", *order):
            if trigger not in self._pending:
                continue
            # Armed triggers expire after PHRASE_ARM_TTL_S — hello is exempt.
            if trigger != "hello":
                if now - self._pending[trigger] > config.PHRASE_ARM_TTL_S:
                    self._pending.pop(trigger)
                    continue
            # Per-trigger cooldown: 3× the global minimum.
            last_t = self._last_fired.get(trigger)
            if last_t is not None and now - last_t < 3 * config.PHRASE_COOLDOWN_S:
                continue
            if trigger == "hello":
                self._fire(trigger, now)
                return trigger
            # Global cooldown since the last phrase of any kind.
            if (self._last_phrase_time is not None
                    and now - self._last_phrase_time < config.PHRASE_COOLDOWN_S):
                continue
            # Chance flip — a failure discards this candidacy until re-armed.
            if self._rng.random() < config.PHRASE_CHANCE:
                self._fire(trigger, now)
                return trigger
            self._discard(trigger)
        return None

    def _fire(self, trigger: str, now: float) -> None:
        self._pending.pop(trigger, None)
        self._last_fired[trigger] = now
        self._last_phrase_time = now
        if trigger == "slowdown":
            self._drop_times = []          # require a fresh burst to re-arm

    def _discard(self, trigger: str) -> None:
        self._pending.pop(trigger, None)
        if trigger == "slowdown":
            self._drop_times = []
