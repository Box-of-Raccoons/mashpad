"""Tests for mashpad.keymap — pure logic, no pygame."""

import random
import sys

import pytest

from mashpad import config
from mashpad.keymap import ItemSpec, item_for_key


@pytest.fixture
def rng():
    return random.Random(42)


# ---------------------------------------------------------------------------
# Purity: none of the pure modules should import pygame
# ---------------------------------------------------------------------------
def test_no_pygame_in_modules():
    """All five pure modules must load without pulling in pygame."""
    import mashpad
    import mashpad.config
    import mashpad.keymap
    import mashpad.items
    import mashpad.ratelimit
    import mashpad.trail
    assert "pygame" not in sys.modules, "A pure module imported pygame!"


# ---------------------------------------------------------------------------
# Letter mapping
# ---------------------------------------------------------------------------
def test_lowercase_letter(rng):
    spec = item_for_key("a", rng)
    assert spec.kind == "letter"
    assert spec.name == "a"
    assert spec.color in config.PALETTE


def test_uppercase_letter_folded(rng):
    spec = item_for_key("A", rng)
    assert spec.kind == "letter"
    assert spec.name == "a"  # case-folded


def test_all_letters(rng):
    for ch in "abcdefghijklmnopqrstuvwxyz":
        s = item_for_key(ch, rng)
        assert s.kind == "letter"
        assert s.name == ch

    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        s = item_for_key(ch, rng)
        assert s.kind == "letter"
        assert s.name == ch.lower()


# ---------------------------------------------------------------------------
# Digit mapping
# ---------------------------------------------------------------------------
def test_digit(rng):
    spec = item_for_key("7", rng)
    assert spec.kind == "digit"
    assert spec.name == "7"
    assert spec.color in config.PALETTE


def test_all_digits(rng):
    for ch in "0123456789":
        s = item_for_key(ch, rng)
        assert s.kind == "digit"
        assert s.name == ch


# ---------------------------------------------------------------------------
# Non-alphanumeric → shape
# ---------------------------------------------------------------------------
def test_none_gives_shape(rng):
    spec = item_for_key(None, rng)
    assert spec.kind == "shape"
    assert spec.name in config.SHAPES


def test_space_gives_shape(rng):
    spec = item_for_key(" ", rng)
    assert spec.kind == "shape"
    assert spec.name in config.SHAPES


def test_special_chars_give_shapes(rng):
    for ch in ["\n", "\t", "!", "@", "#", "€", "π"]:
        s = item_for_key(ch, rng)
        assert s.kind == "shape", f"Expected shape for {ch!r}, got {s.kind!r}"
        assert s.name in config.SHAPES


# ---------------------------------------------------------------------------
# Randomness: every shape reachable
# ---------------------------------------------------------------------------
def test_all_shapes_reachable():
    """All SHAPES names must appear within a reasonable number of draws."""
    rng = random.Random(0)
    seen = set()
    for _ in range(500):
        s = item_for_key(None, rng)
        seen.add(s.name)
    assert seen == set(config.SHAPES), f"Unreachable shapes: {set(config.SHAPES) - seen}"


def test_all_palette_colors_reachable():
    """All palette colours should appear within a reasonable number of draws."""
    rng = random.Random(0)
    seen = set()
    for _ in range(500):
        s = item_for_key("a", rng)
        seen.add(s.color)
    assert seen == set(map(tuple, config.PALETTE))


# ---------------------------------------------------------------------------
# ItemSpec is a dataclass
# ---------------------------------------------------------------------------
def test_itemspec_fields(rng):
    spec = item_for_key("b", rng)
    assert hasattr(spec, "kind")
    assert hasattr(spec, "name")
    assert hasattr(spec, "color")
