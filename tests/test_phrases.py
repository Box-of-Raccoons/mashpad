"""Tests for mashpad.phrases — pure logic, no pygame.

Time is always passed in via note_* calls (poll() reads the last-seen time), and
a FakeRNG makes the fun-threshold draws and PHRASE_CHANCE coin flips
deterministic so arm/fire/re-arm, cooldowns and priority are all pinned down.
"""

import sys

from mashpad import config
from mashpad.phrases import PhraseDirector


class FakeRNG:
    """Deterministic stand-in: queued randint() draws + queued random() flips."""

    def __init__(self, randints=None, randoms=None, default_random=0.0):
        self._randints = list(randints or [])
        self._randoms = list(randoms or [])
        self._default = default_random

    def randint(self, a, b):
        return self._randints.pop(0) if self._randints else a

    def random(self):
        return self._randoms.pop(0) if self._randoms else self._default


# ---------------------------------------------------------------------------
# hello
# ---------------------------------------------------------------------------

def test_hello_fires_on_first_spawn():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, 0)
    assert d.poll() == "hello"
    # Fires once, then is discarded until re-armed.
    assert d.poll() is None


def test_hello_re_arms_after_idle():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, 0)
    assert d.poll() == "hello"
    # A spawn before the idle threshold does NOT re-arm hello.
    d.note_spawn(100.0, 0)
    assert d.poll() is None
    # A spawn after HELLO_IDLE_S of no spawns re-greets.
    d.note_spawn(100.0 + config.HELLO_IDLE_S, 0)
    assert d.poll() == "hello"


def test_hello_exempt_from_cooldown_and_chance():
    # default_random 0.9 would FAIL every flip; the single queued 0.1 is spent by
    # screenfull. hello must still fire despite (a) a phrase 10s ago (global
    # cooldown) and (b) no passing flip left — proving it is exempt from both.
    d = PhraseDirector(FakeRNG(randoms=[0.1], default_random=0.9), now=0.0)
    d.note_cap_hit(0.0)
    assert d.poll() == "screenfull"          # flip 0.1 passes; last_phrase = 0
    d.note_spawn(10.0, 0)                     # first spawn arms hello, within 60s
    assert d.poll() == "hello"               # fires with no flip and inside cooldown


# ---------------------------------------------------------------------------
# slowdown
# ---------------------------------------------------------------------------

def test_slowdown_arms_on_burst():
    d = PhraseDirector(FakeRNG(), now=0.0)
    # Five rapid drops: not yet a burst.
    for i in range(config.SLOWDOWN_DROPS - 1):
        d.note_drop(i * 0.1)
    assert d.poll() is None
    # The SLOWDOWN_DROPS-th drop within the window arms it.
    d.note_drop((config.SLOWDOWN_DROPS - 1) * 0.1)
    assert d.poll() == "slowdown"


def test_slowdown_window_expiry():
    d = PhraseDirector(FakeRNG(), now=0.0)
    # Drops one second apart never accumulate SLOWDOWN_DROPS inside a 3s window.
    for t in range(config.SLOWDOWN_DROPS + 2):
        d.note_drop(float(t))
    assert d.poll() is None


# ---------------------------------------------------------------------------
# raccoons
# ---------------------------------------------------------------------------

def test_raccoons_arms_at_pile():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, config.RACCOON_PILE_N - 1)  # below the pile
    # (this first spawn also arms hello — drain it so raccoons is isolated)
    assert d.poll() == "hello"
    d.note_spawn(config.HELLO_IDLE_S + 1.0, config.RACCOON_PILE_N)  # at the pile
    # hello re-armed by the long idle gap outranks raccoons; drain it.
    assert d.poll() == "hello"
    assert d.poll() is None  # raccoons blocked by hello's fresh global cooldown
    # Past the cooldown, the still-pending raccoons candidate fires.
    d.note_drop(config.HELLO_IDLE_S + 1.0 + config.PHRASE_COOLDOWN_S)
    assert d.poll() == "raccoons"


# ---------------------------------------------------------------------------
# fun
# ---------------------------------------------------------------------------

def test_fun_arms_at_threshold_and_rearms():
    # First threshold 2, next draw 999 (so it won't re-arm during the test).
    d = PhraseDirector(FakeRNG(randints=[2, 999]), now=0.0)
    d.note_spawn(0.0, 0)          # spawn #1 → arms hello, fun counter = 1
    assert d.poll() == "hello"
    d.note_spawn(1.0, 0)          # spawn #2 → counter hits 2 → fun armed + re-draw
    assert d.poll() is None       # blocked by hello's global cooldown
    d.note_spawn(1.0 + config.PHRASE_COOLDOWN_S + 1.0, 0)  # advance past cooldown
    assert d.poll() == "fun"


# ---------------------------------------------------------------------------
# global cooldown
# ---------------------------------------------------------------------------

def test_global_cooldown_blocks_until_elapsed():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, config.RACCOON_PILE_N)  # arms hello + raccoons
    assert d.poll() == "hello"                # last_phrase = 0
    # raccoons stays pending but is blocked while < PHRASE_COOLDOWN_S has passed.
    d.note_drop(config.PHRASE_COOLDOWN_S - 1.0)
    assert d.poll() is None
    d.note_drop(config.PHRASE_COOLDOWN_S)
    assert d.poll() == "raccoons"


# ---------------------------------------------------------------------------
# per-trigger cooldown (3× global)
# ---------------------------------------------------------------------------

def test_per_trigger_cooldown():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, config.RACCOON_PILE_N)  # hello + raccoons
    assert d.poll() == "hello"
    # Fire raccoons once the global cooldown clears.
    d.note_spawn(config.PHRASE_COOLDOWN_S, config.RACCOON_PILE_N)
    assert d.poll() == "raccoons"             # raccoons last_fired = 60
    # Re-arm; global cooldown has cleared but the 3× per-trigger one has not.
    d.note_spawn(config.PHRASE_COOLDOWN_S + 70.0, config.RACCOON_PILE_N)
    assert d.poll() is None
    # Past 3× the global cooldown, raccoons fires again.
    d.note_spawn(config.PHRASE_COOLDOWN_S + 3 * config.PHRASE_COOLDOWN_S + 1.0,
                 config.RACCOON_PILE_N)
    assert d.poll() == "raccoons"


# ---------------------------------------------------------------------------
# chance flip
# ---------------------------------------------------------------------------

def test_failed_flip_discards_until_rearm():
    # First flip 0.9 fails (>= 0.5); afterwards the default 0.1 passes.
    d = PhraseDirector(FakeRNG(randoms=[0.9], default_random=0.1), now=0.0)
    d.note_cap_hit(0.0)
    assert d.poll() is None            # flip failed → candidacy discarded
    assert d.poll() is None            # still discarded (not re-armed)
    d.note_cap_hit(0.0)                # re-arm
    assert d.poll() == "screenfull"    # flip now passes


# ---------------------------------------------------------------------------
# priority
# ---------------------------------------------------------------------------

def test_priority_hello_slowdown_screenfull_raccoons_fun():
    # fun threshold 1 so a single spawn arms it; re-draw 999 after.
    d = PhraseDirector(FakeRNG(randints=[1, 999]), now=0.0)
    for i in range(config.SLOWDOWN_DROPS):     # arm slowdown
        d.note_drop(i * 0.05)
    d.note_cap_hit(0.5)                         # arm screenfull
    d.note_spawn(0.5, config.RACCOON_PILE_N)    # arm hello + raccoons + fun
    # All five pending; each poll returns the highest still-eligible one. Advance
    # time between polls (single far-apart drops) to clear the global cooldown.
    assert d.poll() == "hello"
    d.note_drop(61.0)
    assert d.poll() == "slowdown"
    d.note_drop(122.0)
    assert d.poll() == "screenfull"
    d.note_drop(183.0)
    assert d.poll() == "raccoons"
    d.note_drop(244.0)
    assert d.poll() == "fun"


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_phrases_no_pygame():
    import mashpad.phrases  # noqa: F401
    assert "pygame" not in sys.modules, "phrases imported pygame!"
