"""Tests for mashpad.codelayout — pure layout core, no pygame."""

import sys

import pytest

from mashpad.codelayout import LayoutBuffer, bounce_scale


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_codelayout_no_pygame():
    import mashpad.codelayout  # noqa: F401
    assert "pygame" not in sys.modules, "codelayout imported pygame!"


# ---------------------------------------------------------------------------
# bounce_scale
# ---------------------------------------------------------------------------

def test_bounce_scale_zero_at_start():
    """age=0: sin(pi*0) == 0, so scale is exactly 0."""
    assert bounce_scale(0, 0.3, 1.15) == pytest.approx(0.0, abs=1e-9)


def test_bounce_scale_one_at_dur():
    """age == dur: exact clamp to 1.0."""
    assert bounce_scale(0.3, 0.3, 1.15) == 1.0


def test_bounce_scale_clamped_after_dur():
    """age > dur: still exactly 1.0 (no float drift)."""
    assert bounce_scale(1.0, 0.3, 1.15) == 1.0


def test_bounce_scale_peak_exceeds_one():
    """At the midpoint p=0.5 the scale equals overshoot (> 1.0)."""
    peak = bounce_scale(0.15, 0.3, 1.15)
    assert peak > 1.0
    # Verify it is the expected overshoot value exactly.
    assert peak == pytest.approx(1.15, abs=1e-9)


def test_bounce_scale_negative_age_is_zero():
    """age < 0 clamps to 0.0."""
    assert bounce_scale(-0.1, 0.3, 1.15) == 0.0


# ---------------------------------------------------------------------------
# LayoutBuffer — cursor advance (same line)
# ---------------------------------------------------------------------------

def test_layout_cursor_advance_same_line():
    """Second token on the same line lands at first_x + width1 + space_width."""
    space_width = 5
    buf = LayoutBuffer(width=1000, height=1000, line_height=20, space_width=space_width)

    width1 = 40
    width2 = 60
    buf.append("keyword", "if", width1, starts_new_line=False)
    buf.append("name", "foo", width2, starts_new_line=False)

    placed = buf.placed
    assert len(placed) == 2
    assert placed[1].x == placed[0].x + width1 + space_width


# ---------------------------------------------------------------------------
# LayoutBuffer — soft-wrap
# ---------------------------------------------------------------------------

def test_layout_soft_wrap():
    """A token that would overflow the right edge wraps to the next line."""
    line_height = 20
    buf = LayoutBuffer(width=100, height=1000, line_height=line_height, space_width=5)

    # First token: fits (0 + 90 <= 100).
    buf.append("keyword", "if", 90, starts_new_line=False)
    # Second token: cursor_x=95; 95+20=115 > 100 → wraps.
    buf.append("name", "x", 20, starts_new_line=False)

    placed = buf.placed
    assert len(placed) == 2
    assert placed[1].y == placed[0].y + line_height
    assert placed[1].x == 0  # back to left_margin=0


# ---------------------------------------------------------------------------
# LayoutBuffer — scroll keeps newest visible
# ---------------------------------------------------------------------------

def test_layout_scroll_newest_visible():
    """After overflow, scroll_offset > 0 and newest.y <= height - line_height."""
    line_height = 20
    height = line_height * 2  # room for exactly two visible lines

    buf = LayoutBuffer(width=1000, height=height, line_height=line_height, space_width=5)

    # Append four tokens, each on its own new line.
    for i in range(4):
        buf.append("name", f"x{i}", 30, starts_new_line=(i > 0))

    assert buf.scroll_offset > 0

    newest = buf.newest
    assert newest is not None
    assert newest.y <= height - line_height


# ---------------------------------------------------------------------------
# LayoutBuffer — first-token edge cases
# ---------------------------------------------------------------------------

def test_layout_first_token_starts_new_line_no_advance():
    """starts_new_line=True on the very first token must NOT advance the cursor."""
    buf = LayoutBuffer(width=1000, height=1000, line_height=20, space_width=5)
    buf.append("keyword", "def", 40, starts_new_line=True)

    placed = buf.placed
    assert len(placed) == 1
    # Should land at the origin (left_margin=0, top_margin=0), not one line down.
    assert placed[0].x == 0
    assert placed[0].y == 0


def test_layout_second_token_starts_new_line_does_advance():
    """starts_new_line=True on the second token advances to the next line."""
    line_height = 20
    buf = LayoutBuffer(width=1000, height=1000, line_height=line_height, space_width=5)
    buf.append("keyword", "def", 40, starts_new_line=False)
    buf.append("name", "foo", 30, starts_new_line=True)

    placed = buf.placed
    assert placed[1].y == placed[0].y + line_height
