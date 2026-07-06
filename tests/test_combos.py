"""Tests for mashpad.combos — the AltGr-safe grown-up modifier decision.

These test the PURE mods_are_grown_up() predicate with raw SDL2 modifier
bitmasks and deliberately never import pygame, so the suite's "pure modules must
not import pygame" assertion (test_keymap.py) stays green. combos imports pygame
only lazily inside grown_up_combo(), so importing combos here is pygame-free.
"""

import sys

from mashpad import combos

# SDL2 keyboard-modifier bits (the values pygame.KMOD_* mirror). Kept local so
# this test needs no pygame; one test below pins combos' own copies to these.
LSHIFT = 0x0001
LCTRL = 0x0040
RCTRL = 0x0080
LALT = 0x0100
RALT = 0x0200
MODE = 0x4000  # AltGr indicator on some SDL builds


def test_combos_import_is_pygame_free():
    """Importing combos must not drag pygame into sys.modules (purity contract)."""
    import mashpad.combos  # noqa: F401 — ensure it is imported
    assert "pygame" not in sys.modules, "combos imported pygame at module level!"


def test_module_constants_match_sdl_values():
    """combos' hardcoded KMOD mirrors must equal the real SDL2 bit values."""
    assert combos._KMOD_LCTRL == LCTRL
    assert combos._KMOD_RCTRL == RCTRL
    assert combos._KMOD_CTRL == (LCTRL | RCTRL)
    assert combos._KMOD_LALT == LALT
    assert combos._KMOD_MODE == MODE


def test_left_ctrl_right_alt_is_not_grown_up():
    """AltGr on Windows == LCTRL+RALT — must NOT count as a grown-up combo."""
    assert combos.mods_are_grown_up(LCTRL | RALT) is False


def test_left_ctrl_left_alt_is_grown_up():
    """A real parent chord: left Ctrl + left Alt."""
    assert combos.mods_are_grown_up(LCTRL | LALT) is True


def test_right_ctrl_left_alt_is_grown_up():
    """Either Ctrl side is fine so long as the Alt side is the left one."""
    assert combos.mods_are_grown_up(RCTRL | LALT) is True


def test_altgr_mode_flag_vetoes_even_with_lalt():
    """The AltGr indicator (KMOD_MODE) rejects the chord even if LALT bits are set."""
    assert combos.mods_are_grown_up(LCTRL | RALT | MODE) is False
    assert combos.mods_are_grown_up(LCTRL | LALT | MODE) is False


def test_ctrl_without_any_alt_is_not_grown_up():
    assert combos.mods_are_grown_up(LCTRL) is False


def test_left_alt_without_ctrl_is_not_grown_up():
    assert combos.mods_are_grown_up(LALT) is False


def test_right_alt_only_is_not_grown_up():
    assert combos.mods_are_grown_up(RALT) is False


def test_no_modifiers_is_not_grown_up():
    assert combos.mods_are_grown_up(0) is False


def test_harmless_extra_modifier_does_not_break_match():
    """Shift held alongside a valid Ctrl+left-Alt chord still counts."""
    assert combos.mods_are_grown_up(LCTRL | LALT | LSHIFT) is True
