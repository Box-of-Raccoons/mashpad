"""Tests for mashpad.trail — Trail deque, expiry, age fractions, hue cycle."""

import math
import pytest

from mashpad import config
from mashpad.trail import Trail


F = config.TRAIL_FADE_S   # 0.6
M = config.TRAIL_MAX_POINTS  # 64


# ---------------------------------------------------------------------------
# Basic add and points
# ---------------------------------------------------------------------------

def test_empty_trail_yields_nothing():
    t = Trail()
    assert list(t.points(0.0)) == []


def test_single_point_visible_immediately():
    trail = Trail()
    trail.add((100.0, 200.0), now=0.0)
    pts = list(trail.points(0.0))
    assert len(pts) == 1
    pos, age_frac = pts[0]
    assert pos == (100.0, 200.0)
    assert age_frac == pytest.approx(0.0, abs=1e-9)


def test_point_at_half_fade_age():
    trail = Trail()
    trail.add((0.0, 0.0), now=0.0)
    pts = list(trail.points(F / 2))
    assert len(pts) == 1
    _, age_frac = pts[0]
    assert age_frac == pytest.approx(0.5, abs=1e-9)


def test_point_expired_at_fade_s():
    """A point added at t=0 should NOT appear in points(TRAIL_FADE_S)."""
    trail = Trail()
    trail.add((0.0, 0.0), now=0.0)
    # At exactly TRAIL_FADE_S the point is at or past expiry (age_frac=1.0)
    pts = list(trail.points(F))
    # age = F, cutoff = F → F < F is False, so point is skipped
    assert len(pts) == 0


def test_point_expires_past_fade_s():
    trail = Trail()
    trail.add((0.0, 0.0), now=0.0)
    pts = list(trail.points(F + 0.01))
    assert len(pts) == 0


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------

def test_prune_removes_expired():
    trail = Trail()
    trail.add((1.0, 1.0), now=0.0)
    trail.add((2.0, 2.0), now=0.3)
    trail.prune(F + 0.01)  # first point expired, second still alive
    pts = list(trail.points(F + 0.01))
    assert len(pts) == 1
    assert pts[0][0] == (2.0, 2.0)


def test_prune_removes_all_when_all_old():
    trail = Trail()
    for i in range(5):
        trail.add((float(i), 0.0), now=0.0)
    trail.prune(F + 1.0)
    assert list(trail.points(F + 1.0)) == []


# ---------------------------------------------------------------------------
# Capacity cap (oldest evicted)
# ---------------------------------------------------------------------------

def test_capacity_evicts_oldest():
    trail = Trail()
    # Add TRAIL_MAX_POINTS + 1 points
    for i in range(M + 1):
        trail.add((float(i), 0.0), now=float(i) * 0.001)

    # All should still be "fresh" (we used tiny timestamps and check at the last)
    now = float(M) * 0.001
    visible = list(trail.points(now))
    # At most M points returned (oldest evicted by deque maxlen)
    positions = [p for p, _ in visible]
    assert (1.0, 0.0) in positions  # the second-oldest should be present
    assert (0.0, 0.0) not in positions  # the first should have been evicted


# ---------------------------------------------------------------------------
# Age fractions are monotonically increasing oldest→newest
# ---------------------------------------------------------------------------

def test_age_fractions_monotone():
    trail = Trail()
    now = 10.0
    for i in range(5):
        trail.add((float(i), 0.0), now=now - (F * 0.9) + i * 0.1)
    pts = list(trail.points(now))
    fracs = [f for _, f in pts]
    # Oldest points have higher age fractions
    for a, b in zip(fracs, fracs[1:]):
        assert a > b, f"Age fractions not descending oldest→newest: {fracs}"


# ---------------------------------------------------------------------------
# hue_for cycles 0..1 over HUE_CYCLE_S
# ---------------------------------------------------------------------------

def test_hue_for_zero_at_origin():
    trail = Trail()
    assert trail.hue_for(0.0) == pytest.approx(0.0, abs=1e-9)


def test_hue_for_half_at_half_cycle():
    trail = Trail()
    assert trail.hue_for(Trail.HUE_CYCLE_S / 2) == pytest.approx(0.5, abs=1e-9)


def test_hue_for_wraps_at_cycle():
    trail = Trail()
    assert trail.hue_for(Trail.HUE_CYCLE_S) == pytest.approx(0.0, abs=1e-9)


def test_hue_for_monotone_within_cycle():
    trail = Trail()
    cycle = Trail.HUE_CYCLE_S
    hues = [trail.hue_for(cycle * t) for t in (0.0, 0.2, 0.4, 0.6, 0.8)]
    for a, b in zip(hues, hues[1:]):
        assert b > a


def test_hue_for_returns_float_in_range():
    trail = Trail()
    for t in (0.0, 1.0, 3.0, 7.5, 100.0):
        h = trail.hue_for(t)
        assert 0.0 <= h < 1.0, f"hue_for({t}) = {h} out of range"
