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

def test_hello_fires_on_splash():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_splash(0.0)
    assert d.poll(0.0) == "hello"
    # Fires once, then is discarded until re-armed.
    assert d.poll(0.0) is None


def test_first_spawn_does_not_arm_hello():
    # hello greets at the splash, not on the first spawn.
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, 0)
    assert d.poll(0.0) is None


def test_hello_re_arms_after_idle():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_splash(0.0)
    assert d.poll(0.0) == "hello"
    d.note_spawn(0.0, 0)
    # A spawn before the idle threshold does NOT re-arm hello.
    d.note_spawn(100.0, 0)
    assert d.poll(100.0) is None
    # A spawn after HELLO_IDLE_S of no spawns re-greets.
    d.note_spawn(100.0 + config.HELLO_IDLE_S, 0)
    assert d.poll(100.0 + config.HELLO_IDLE_S) == "hello"


def test_hello_exempt_from_cooldown_and_chance():
    # default_random 0.9 would FAIL every flip; the single queued 0.1 is spent by
    # screenfull. hello must still fire despite (a) a phrase 10s ago (global
    # cooldown) and (b) no passing flip left — proving it is exempt from both.
    d = PhraseDirector(FakeRNG(randoms=[0.1], default_random=0.9), now=0.0)
    d.note_cap_hit(0.0)
    assert d.poll(0.0) == "screenfull"       # flip 0.1 passes; last_phrase = 0
    d.note_splash(10.0)                       # splash arms hello, within 60s
    assert d.poll(10.0) == "hello"           # fires with no flip and inside cooldown


# ---------------------------------------------------------------------------
# slowdown
# ---------------------------------------------------------------------------

def test_slowdown_arms_on_burst():
    d = PhraseDirector(FakeRNG(), now=0.0)
    # Five rapid drops: not yet a burst.
    for i in range(config.SLOWDOWN_DROPS - 1):
        d.note_drop(i * 0.1)
    last_before = (config.SLOWDOWN_DROPS - 2) * 0.1
    assert d.poll(last_before) is None
    # The SLOWDOWN_DROPS-th drop within the window arms it.
    arm_time = (config.SLOWDOWN_DROPS - 1) * 0.1
    d.note_drop(arm_time)
    assert d.poll(arm_time) == "slowdown"


def test_slowdown_window_expiry():
    d = PhraseDirector(FakeRNG(), now=0.0)
    # Drops one second apart never accumulate SLOWDOWN_DROPS inside a 3s window.
    last_t = 0.0
    for t in range(config.SLOWDOWN_DROPS + 2):
        last_t = float(t)
        d.note_drop(last_t)
    assert d.poll(last_t) is None


# ---------------------------------------------------------------------------
# raccoons
# ---------------------------------------------------------------------------

def test_raccoons_arms_at_pile():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_spawn(0.0, config.RACCOON_PILE_N - 1)  # below the pile
    assert d.poll(0.0) is None
    t1 = config.HELLO_IDLE_S + 1.0
    d.note_spawn(t1, config.RACCOON_PILE_N)  # at the pile
    # hello re-armed by the long idle gap outranks raccoons; drain it.
    assert d.poll(t1) == "hello"
    assert d.poll(t1) is None  # raccoons blocked by hello's fresh global cooldown
    # Past the cooldown, the still-pending raccoons candidate fires.
    t2 = t1 + config.PHRASE_COOLDOWN_S
    d.note_drop(t2)
    assert d.poll(t2) == "raccoons"


# ---------------------------------------------------------------------------
# fun
# ---------------------------------------------------------------------------

def test_fun_arms_at_threshold_and_rearms():
    # First threshold 2, next draw 999 (so it won't re-arm during the test).
    d = PhraseDirector(FakeRNG(randints=[2, 999]), now=0.0)
    d.note_spawn(0.0, 0)          # spawn #1 → fun counter = 1, nothing armed
    assert d.poll(0.0) is None
    d.note_spawn(1.0, 0)          # spawn #2 → counter hits 2 → fun armed + re-draw
    assert d.poll(1.0) == "fun"   # nothing fired yet, so no cooldown in the way


# ---------------------------------------------------------------------------
# global cooldown
# ---------------------------------------------------------------------------

def test_global_cooldown_blocks_until_elapsed():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_splash(0.0)                        # arms hello
    d.note_spawn(0.0, config.RACCOON_PILE_N)  # arms raccoons
    assert d.poll(0.0) == "hello"             # last_phrase = 0
    # raccoons stays pending but is blocked while < PHRASE_COOLDOWN_S has passed.
    t_almost = config.PHRASE_COOLDOWN_S - 1.0
    d.note_drop(t_almost)
    assert d.poll(t_almost) is None
    t_clear = config.PHRASE_COOLDOWN_S
    d.note_drop(t_clear)
    assert d.poll(t_clear) == "raccoons"


# ---------------------------------------------------------------------------
# per-trigger cooldown (3× global)
# ---------------------------------------------------------------------------

def test_per_trigger_cooldown():
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_splash(0.0)                        # hello
    d.note_spawn(0.0, config.RACCOON_PILE_N)  # raccoons
    assert d.poll(0.0) == "hello"
    # Fire raccoons once the global cooldown clears.
    t1 = config.PHRASE_COOLDOWN_S
    d.note_spawn(t1, config.RACCOON_PILE_N)   # re-arms raccoons
    assert d.poll(t1) == "raccoons"           # raccoons last_fired = t1
    # Re-arm; global cooldown has cleared but the 3× per-trigger one has not.
    t2 = config.PHRASE_COOLDOWN_S + 70.0
    d.note_spawn(t2, config.RACCOON_PILE_N)
    assert d.poll(t2) is None
    # Past 3× the global cooldown, raccoons fires again.
    t3 = config.PHRASE_COOLDOWN_S + 3 * config.PHRASE_COOLDOWN_S + 1.0
    d.note_spawn(t3, config.RACCOON_PILE_N)
    assert d.poll(t3) == "raccoons"


# ---------------------------------------------------------------------------
# chance flip
# ---------------------------------------------------------------------------

def test_failed_flip_discards_until_rearm():
    # First flip 0.9 fails (>= 0.5); afterwards the default 0.1 passes.
    d = PhraseDirector(FakeRNG(randoms=[0.9], default_random=0.1), now=0.0)
    d.note_cap_hit(0.0)
    assert d.poll(0.0) is None         # flip failed → candidacy discarded
    assert d.poll(0.0) is None         # still discarded (not re-armed)
    d.note_cap_hit(0.0)                # re-arm
    assert d.poll(0.0) == "screenfull" # flip now passes


# ---------------------------------------------------------------------------
# priority
# ---------------------------------------------------------------------------

def test_least_recently_fired_beats_fresh_rearm():
    # screenfull fires once; later BOTH screenfull and raccoons are armed and
    # past every cooldown. Never-heard raccoons must win the slot even though
    # screenfull sits higher in the tie-break order.
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_cap_hit(0.0)
    assert d.poll(0.0) == "screenfull"
    later = 3 * config.PHRASE_COOLDOWN_S + 1.0   # clear per-trigger cooldown too
    d.note_cap_hit(later)                         # re-arm screenfull
    d.note_spawn(later, config.RACCOON_PILE_N)    # arm raccoons
    assert d.poll(later) == "raccoons"
    # next slot (past the global cooldown) goes back to screenfull
    t_next = later + config.PHRASE_COOLDOWN_S
    d.note_drop(t_next)
    assert d.poll(t_next) == "screenfull"


def test_priority_hello_slowdown_screenfull_raccoons_fun():
    # fun threshold=1 so each single spawn re-arms it (every draw returns 1).
    d = PhraseDirector(FakeRNG(randints=[1, 1, 1, 1, 1]), now=0.0)
    for i in range(config.SLOWDOWN_DROPS):     # arm slowdown at t≈0
        d.note_drop(i * 0.05)
    d.note_cap_hit(0.5)                         # arm screenfull
    d.note_splash(0.5)                          # arm hello
    d.note_spawn(0.5, config.RACCOON_PILE_N)    # arm raccoons + fun (threshold=1)
    # hello is always first and exempt from cooldown/chance.
    assert d.poll(0.5) == "hello"               # last_phrase=0.5
    # Re-arm all remaining triggers at t=31 (past 30s global cooldown) to keep
    # them fresh (PHRASE_ARM_TTL_S=45s; triggers armed at t≈0 would expire by
    # the later polls without re-arming).  Priority ordering is still exercised:
    # within each pair of armed triggers, the one with lower LRF fires first.
    t1 = 31.0
    for i in range(config.SLOWDOWN_DROPS):      # re-arm slowdown
        d.note_drop(t1 + i * 0.01)
    d.note_cap_hit(t1)                           # re-arm screenfull
    d.note_spawn(t1, config.RACCOON_PILE_N)      # re-arm raccoons + fun (count=1>=1)
    assert d.poll(t1 + 0.1) == "slowdown"       # last_phrase=t1+0.1

    t2 = t1 + 0.1 + config.PHRASE_COOLDOWN_S + 1.0   # ≈62.1
    d.note_cap_hit(t2)
    d.note_spawn(t2, config.RACCOON_PILE_N)      # re-arm raccoons + fun
    assert d.poll(t2) == "screenfull"            # never-fired; beats raccoons(#4)

    t3 = t2 + config.PHRASE_COOLDOWN_S + 1.0    # ≈93.1
    d.note_spawn(t3, config.RACCOON_PILE_N)      # re-arm raccoons + fun
    assert d.poll(t3) == "raccoons"              # never-fired; beats fun(#5)

    t4 = t3 + config.PHRASE_COOLDOWN_S + 1.0    # ≈124.1
    d.note_spawn(t4, config.RACCOON_PILE_N)      # re-arm fun
    assert d.poll(t4) == "fun"


# ---------------------------------------------------------------------------
# Arm TTL expiry
# ---------------------------------------------------------------------------

def test_arm_ttl_expires_stale_trigger():
    """A trigger armed once and never re-armed silently expires after PHRASE_ARM_TTL_S."""
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_cap_hit(0.0)                        # screenfull armed at t=0
    stale = config.PHRASE_ARM_TTL_S + 1.0
    assert d.poll(stale) is None               # expired; not fired


def test_arm_ttl_hello_exempt_from_expiry():
    """hello never expires even far past PHRASE_ARM_TTL_S."""
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_splash(0.0)
    far_future = config.PHRASE_ARM_TTL_S * 10
    assert d.poll(far_future) == "hello"


def test_arm_ttl_rearmed_trigger_survives():
    """A trigger re-armed before expiry keeps a fresh armed_time and fires."""
    d = PhraseDirector(FakeRNG(), now=0.0)
    d.note_cap_hit(0.0)                        # armed at t=0
    # Re-arm just before the original TTL would expire.
    fresh = config.PHRASE_ARM_TTL_S - 5.0      # t=40
    d.note_cap_hit(fresh)                      # armed_time refreshed to 40
    # Poll at global-cooldown-clear time from the re-arm moment.
    fire_time = fresh + config.PHRASE_COOLDOWN_S + 1.0   # 71
    # TTL: fire_time - fresh = 31 < 45 → not expired; cooldown: 71 - 0 = 71 > 30 ✓
    assert d.poll(fire_time) == "screenfull"


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_phrases_no_pygame():
    import mashpad.phrases  # noqa: F401
    assert "pygame" not in sys.modules, "phrases imported pygame!"
