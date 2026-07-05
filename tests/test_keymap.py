"""Tests for mashpad.keymap — pure logic, no pygame."""

import random
import sys
from pathlib import Path

import pytest

from mashpad import config
from mashpad.imagepack import ImageEntry
from mashpad.keymap import ItemSpec, item_for_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(name: str, spoken: str = "") -> ImageEntry:
    """Build a minimal ImageEntry for test fixtures."""
    return ImageEntry(name=name, path=Path(f"{name}.png"), spoken=spoken or name)


@pytest.fixture
def rng():
    return random.Random(42)


# ---------------------------------------------------------------------------
# Purity: none of the pure modules should import pygame
# ---------------------------------------------------------------------------
def test_no_pygame_in_modules():
    """All six pure modules must load without pulling in pygame."""
    import mashpad
    import mashpad.config
    import mashpad.keymap
    import mashpad.items
    import mashpad.ratelimit
    import mashpad.trail
    import mashpad.imagepack
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


# ---------------------------------------------------------------------------
# spoken_name property
# ---------------------------------------------------------------------------

def test_spoken_name_uses_spoken_when_set():
    spec = ItemSpec(kind="image", name="raccoon3", color=(255, 0, 0), spoken="raccoon")
    assert spec.spoken_name == "raccoon"


def test_spoken_name_falls_back_to_name_when_spoken_empty():
    spec = ItemSpec(kind="shape", name="circle", color=(255, 0, 0))
    assert spec.spoken_name == "circle"


def test_spoken_name_falls_back_for_letter():
    spec = ItemSpec(kind="letter", name="a", color=(0, 255, 0))
    assert spec.spoken_name == "a"


# ---------------------------------------------------------------------------
# extras=() — empty extras behaves exactly as before
# ---------------------------------------------------------------------------

def test_empty_extras_behaves_as_before():
    """extras=() must give identical results to calling without extras."""
    rng1 = random.Random(42)
    rng2 = random.Random(42)
    s1 = item_for_key(None, rng1)
    s2 = item_for_key(None, rng2, extras=())
    assert s1.kind == "shape"
    assert s2.kind == "shape"
    assert s1.name == s2.name


def test_empty_extras_all_shapes_still_reachable():
    """With no extras, shape coverage is unchanged."""
    rng = random.Random(0)
    seen = set()
    for _ in range(500):
        s = item_for_key(None, rng, extras=())
        seen.add(s.name)
    assert seen == set(config.SHAPES)


# ---------------------------------------------------------------------------
# extras — join the combined pool
# ---------------------------------------------------------------------------

def test_extras_join_pool():
    """A seeded rng must produce both shapes and images when extras are present."""
    extra = _make_entry("raccoon", "raccoon")
    seen_shape = False
    seen_image = False
    rng = random.Random(0)
    for _ in range(300):
        s = item_for_key(None, rng, extras=[extra])
        if s.kind == "shape":
            seen_shape = True
        elif s.kind == "image":
            seen_image = True
        if seen_shape and seen_image:
            break
    assert seen_shape, "Should produce shape specs from the combined pool"
    assert seen_image, "Should produce image specs from the combined pool"


def test_extras_carry_kind_and_spoken():
    """Items from extras must have kind='image' and the correct spoken word."""
    extra = _make_entry("raccoon3", "raccoon")
    rng = random.Random(0)
    found = None
    for _ in range(300):
        s = item_for_key(None, rng, extras=[extra])
        if s.kind == "image":
            found = s
            break
    assert found is not None, "Should produce at least one image spec"
    assert found.name == "raccoon3"
    assert found.spoken == "raccoon"
    assert found.spoken_name == "raccoon"
    assert found.color in config.PALETTE


def test_extras_multiple_entries_all_reachable():
    """All extra entries must be reachable within a reasonable number of draws."""
    extras = [
        _make_entry("raccoon1", "raccoon"),
        _make_entry("wave", "wave"),
        _make_entry("star2", "star"),
    ]
    seen = set()
    rng = random.Random(0)
    for _ in range(500):
        s = item_for_key(None, rng, extras=extras)
        if s.kind == "image":
            seen.add(s.name)
    assert seen == {"raccoon1", "wave", "star2"}, (
        f"Not all extras were reachable. Seen: {seen}"
    )


def test_letter_key_ignores_extras(rng):
    """Extras do not affect letter key output."""
    extra = _make_entry("raccoon", "raccoon")
    spec = item_for_key("a", rng, extras=[extra])
    assert spec.kind == "letter"
    assert spec.name == "a"


def test_digit_key_ignores_extras(rng):
    """Extras do not affect digit key output."""
    extra = _make_entry("raccoon", "raccoon")
    spec = item_for_key("7", rng, extras=[extra])
    assert spec.kind == "digit"
    assert spec.name == "7"
