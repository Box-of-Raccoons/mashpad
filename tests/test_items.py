"""Tests for mashpad.items — lifecycle, scale, alpha, ItemField cap."""

import math
import random

import pytest

from mashpad import config
from mashpad.items import (
    ALIVE, DEAD, FADING, SPAWNING,
    Item, ItemField,
)
from mashpad.keymap import ItemSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
B  = config.BOUNCE_S   # 0.3
L  = config.LINGER_S   # 4.0
F  = config.FADE_S     # 1.5
OV = config.BOUNCE_OVERSHOOT  # 1.15

SPAWN = 100.0  # arbitrary absolute spawn time


def make_item(spawn_time: float = SPAWN) -> Item:
    spec = ItemSpec(kind="letter", name="a", color=(255, 0, 0))
    return Item(spec=spec, pos=(400.0, 300.0), spawn_time=spawn_time)


# ---------------------------------------------------------------------------
# State transitions at exact boundaries
# ---------------------------------------------------------------------------

def test_state_spawning_just_after_birth():
    item = make_item()
    assert item.state(SPAWN + 0.0) == SPAWNING
    assert item.state(SPAWN + B / 2) == SPAWNING


def test_state_spawning_just_before_bounce_end():
    item = make_item()
    # age = 0.29 < BOUNCE_S (0.30) → SPAWNING
    assert item.state(SPAWN + 0.29) == SPAWNING


def test_state_alive_at_bounce_end():
    item = make_item()
    # age = BOUNCE_S exactly → ALIVE
    assert item.state(SPAWN + B) == ALIVE


def test_state_alive_mid_linger():
    item = make_item()
    assert item.state(SPAWN + B + L / 2) == ALIVE


def test_state_alive_just_before_fade():
    item = make_item()
    # age = B + L - epsilon → ALIVE
    assert item.state(SPAWN + B + L - 0.01) == ALIVE


def test_state_fading_at_fade_start():
    item = make_item()
    # age = B + L exactly → FADING
    assert item.state(SPAWN + B + L) == FADING


def test_state_fading_mid_fade():
    item = make_item()
    assert item.state(SPAWN + B + L + F / 2) == FADING


def test_state_fading_just_before_dead():
    item = make_item()
    # just before full fade completes
    assert item.state(SPAWN + B + L + F - 0.01) == FADING


def test_state_dead_at_fade_end():
    item = make_item()
    assert item.state(SPAWN + B + L + F) == DEAD


def test_state_dead_after_fade_end():
    item = make_item()
    assert item.state(SPAWN + B + L + F + 10) == DEAD


# ---------------------------------------------------------------------------
# Scale — bounce curve
# ---------------------------------------------------------------------------

def test_scale_zero_at_birth():
    item = make_item()
    assert item.scale(SPAWN) == pytest.approx(0.0, abs=1e-9)


def test_scale_peaks_near_overshoot():
    item = make_item()
    # At p=0.5 (age = BOUNCE_S/2) we expect exactly BOUNCE_OVERSHOOT
    peak = item.scale(SPAWN + B / 2)
    assert peak == pytest.approx(OV, abs=1e-6)


def test_scale_exactly_one_at_bounce_end():
    item = make_item()
    # Must be EXACTLY 1.0 (clamped)
    assert item.scale(SPAWN + B) == 1.0


def test_scale_one_after_bounce():
    item = make_item()
    assert item.scale(SPAWN + B + 1.0) == 1.0
    assert item.scale(SPAWN + B + L + F / 2) == 1.0


def test_scale_monotone_rising_first_half():
    item = make_item()
    times = [SPAWN + B * t for t in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)]
    scales = [item.scale(t) for t in times]
    for a, b in zip(scales, scales[1:]):
        assert b > a, f"Scale not rising: {a} -> {b}"


def test_scale_positive_during_bounce():
    item = make_item()
    # Scale should stay > 0 after the very start
    for frac in (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99):
        assert item.scale(SPAWN + B * frac) > 0


# ---------------------------------------------------------------------------
# Alpha — fade
# ---------------------------------------------------------------------------

def test_alpha_255_before_fade():
    item = make_item()
    assert item.alpha(SPAWN) == 255
    assert item.alpha(SPAWN + B) == 255
    assert item.alpha(SPAWN + B + L - 0.001) == 255


def test_alpha_255_at_fade_start():
    item = make_item()
    # At the very instant fade begins, alpha is 255 (elapsed=0 → fraction=0)
    assert item.alpha(SPAWN + B + L) == 255


def test_alpha_half_mid_fade():
    item = make_item()
    mid = SPAWN + B + L + F / 2
    a = item.alpha(mid)
    assert 120 <= a <= 135  # approx 127 (half of 255)


def test_alpha_zero_at_fade_end():
    item = make_item()
    assert item.alpha(SPAWN + B + L + F) == 0


def test_alpha_zero_after_fade_end():
    item = make_item()
    assert item.alpha(SPAWN + B + L + F + 5) == 0


def test_alpha_monotone_during_fade():
    item = make_item()
    fade_start = SPAWN + B + L
    steps = [fade_start + F * t for t in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)]
    alphas = [item.alpha(t) for t in steps]
    for a, b in zip(alphas, alphas[1:]):
        assert b <= a, f"Alpha not monotonically decreasing: {a} -> {b}"


# ---------------------------------------------------------------------------
# force_fade
# ---------------------------------------------------------------------------

def test_force_fade_transitions_to_fading():
    item = make_item()
    now = SPAWN + 0.5  # mid-linger
    assert item.state(now) == ALIVE
    item.force_fade(now)
    assert item.state(now) == FADING


def test_force_fade_idempotent():
    item = make_item()
    now = SPAWN + 0.5
    item.force_fade(now)
    item.force_fade(now + 0.1)  # second call — should not change fade start
    # First call set fade_start=now; item should become DEAD at now+FADE_S
    assert item.state(now + F) == DEAD
    assert item.state(now + F - 0.01) == FADING


def test_force_fade_no_effect_if_already_fading_naturally():
    item = make_item()
    # Advance past natural fade start
    natural_fade = SPAWN + B + L
    later = natural_fade + 0.2
    item.force_fade(later)  # already fading — should have no effect
    # State should still be FADING, not altered
    assert item.state(later) == FADING


# ---------------------------------------------------------------------------
# ItemField — cap enforcement
# ---------------------------------------------------------------------------

def test_field_spawn_and_iterate():
    field = ItemField()
    spec = ItemSpec(kind="letter", name="a", color=(255, 0, 0))
    field.spawn(spec, (0, 0), SPAWN)
    assert len(field.items) == 1


def test_field_cap_forces_oldest_to_fading():
    field = ItemField()
    spec = ItemSpec(kind="shape", name="circle", color=(0, 255, 0))
    now = 0.0

    # Spawn MAX_ITEMS items
    for i in range(config.MAX_ITEMS):
        field.spawn(spec, (i, 0), now)

    oldest = field.items[0]
    assert oldest.state(now) != FADING

    # Spawn one more — should force-fade the oldest
    field.spawn(spec, (99, 0), now)
    assert oldest.state(now) == FADING


def test_field_cap_only_forces_non_fading():
    """If oldest is already fading, the next non-fading item gets force-faded."""
    field = ItemField()
    spec = ItemSpec(kind="shape", name="circle", color=(0, 0, 255))
    now = 0.0

    for i in range(config.MAX_ITEMS):
        field.spawn(spec, (i, 0), now)

    # Manually force-fade the oldest
    oldest = field.items[0]
    oldest.force_fade(now)
    second_oldest = field.items[1]
    assert second_oldest.state(now) != FADING

    # Spawn one more — oldest already fading, so second_oldest should be faded
    field.spawn(spec, (99, 0), now)
    assert second_oldest.state(now) == FADING


def test_field_update_drops_dead_items():
    field = ItemField()
    spec = ItemSpec(kind="letter", name="b", color=(255, 255, 0))
    now = 0.0
    field.spawn(spec, (0, 0), now)
    assert len(field.items) == 1

    # Advance time past full lifetime
    dead_time = now + B + L + F + 1
    field.update(dead_time)
    assert len(field.items) == 0


def test_field_items_ordered_oldest_to_newest():
    field = ItemField()
    spec = ItemSpec(kind="digit", name="1", color=(0, 255, 255))
    t = 0.0
    for _ in range(5):
        field.spawn(spec, (0, 0), t)
        t += 0.01

    spawn_times = [i.spawn_time for i in field.items]
    assert spawn_times == sorted(spawn_times)


# ---------------------------------------------------------------------------
# surface slot exists and defaults to None
# ---------------------------------------------------------------------------
def test_item_surface_slot():
    item = make_item()
    assert item.surface is None
    item.surface = "dummy"
    assert item.surface == "dummy"


# ---------------------------------------------------------------------------
# spawn() return value — forced_fade flag (Fix 2)
# ---------------------------------------------------------------------------

def test_spawn_reports_forced_fade_when_cap_hit():
    """spawn returns forced_fade=True when it force-fades the oldest item."""
    field = ItemField()
    spec = ItemSpec(kind="shape", name="circle", color=(0, 255, 0))
    now = 0.0
    for i in range(config.MAX_ITEMS):
        field.spawn(spec, (i, 0), now)
    _, forced = field.spawn(spec, (99, 0), now)
    assert forced is True


def test_spawn_no_force_fade_when_all_items_already_fading():
    """When all live items are already fading, spawn does not force-fade any
    and reports forced_fade=False."""
    field = ItemField()
    spec = ItemSpec(kind="shape", name="circle", color=(0, 255, 0))
    now = 0.0
    for i in range(config.MAX_ITEMS):
        field.spawn(spec, (i, 0), now)
    # Force-fade every item so none are eligible for a cap-triggered fade.
    for item in field.items:
        item.force_fade(now)
    # All MAX_ITEMS items are live (FADING), so the cap condition triggers —
    # but the inner scan finds no non-fading candidate.
    _, forced = field.spawn(spec, (99, 0), now)
    assert forced is False


def test_spawn_no_force_fade_below_cap():
    """spawn returns forced_fade=False when the field is below MAX_ITEMS."""
    field = ItemField()
    spec = ItemSpec(kind="shape", name="circle", color=(0, 255, 0))
    now = 0.0
    for i in range(config.MAX_ITEMS - 1):
        field.spawn(spec, (i, 0), now)
    _, forced = field.spawn(spec, (99, 0), now)
    assert forced is False
