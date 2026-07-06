# mashpad/combos.py — the grown-up key combos, in ONE AltGr-safe place.
#
# The parent-only combos (Ctrl+Alt+Q quit, Ctrl+Alt+O options) were duplicated
# in main.py and menu.py and both checked a naive `mod & KMOD_CTRL and mod &
# KMOD_ALT`. That is exploitable on Windows: an international keyboard's AltGr
# (right Alt) is synthesised by the OS as LeftCtrl+RightAlt, so AltGr+Q or
# AltGr+O — keys a toddler mashing an intl layout will hit — satisfied the naive
# test and quit the app / opened the menu, defeating the whole lockdown.
#
# Robust rule: require Ctrl AND *left* Alt (KMOD_LALT) specifically, and reject
# any event that carries the AltGr indicator (KMOD_MODE). AltGr sets RALT (and,
# on some SDL builds, KMOD_MODE) but NEVER LALT, so demanding LALT is what makes
# this layout-proof: a parent's real Ctrl + left-Alt + Q still works everywhere,
# while every AltGr chord is excluded. Either Ctrl (left or right) is accepted —
# only the Alt side must be the left one.
#
# Import note: the modifier decision (mods_are_grown_up) is deliberately pure —
# it uses the SDL2 keyboard-modifier bitmasks hardcoded below, so it needs NO
# pygame import and NO pygame.init(). That keeps it unit-testable off a real
# event AND keeps this module clear of the suite's "pure modules must not import
# pygame" contract (importing pygame here would drag it into sys.modules and
# trip that assertion). Only grown_up_combo, which needs the KEYDOWN / K_q / K_o
# event constants, touches pygame, and it imports it lazily at call time — by
# then the app has long since initialised pygame, so it is a cheap cached lookup.

from __future__ import annotations

# SDL2 keyboard-modifier bitmasks. These are ABI-stable values that pygame's
# KMOD_* names mirror exactly (pygame is built on SDL2); we hardcode only the
# handful the grown-up test needs so the decision stays pygame-free.
_KMOD_LCTRL = 0x0040             # left Ctrl
_KMOD_RCTRL = 0x0080             # right Ctrl
_KMOD_CTRL = _KMOD_LCTRL | _KMOD_RCTRL  # either Ctrl (== pygame.KMOD_CTRL, 0x00C0)
_KMOD_LALT = 0x0100              # left Alt — the ONLY Alt a grown-up combo accepts
_KMOD_MODE = 0x4000             # AltGr indicator (set on some SDL builds); a veto

# Combo action names — the string contract main.py / menu.py already consume.
QUIT = "quit"
OPTIONS = "options"


def mods_are_grown_up(mod: int) -> bool:
    """True iff the modifier mask is a real parent chord: Ctrl + LEFT Alt, no AltGr.

    Takes a raw KMOD_* bitmask (an int) so the decision is testable without a
    live pygame event. Requires some Ctrl bit and the LALT bit; rejects anything
    with the AltGr (KMOD_MODE) flag set. RALT alone never qualifies, which is
    what shuts out the Windows AltGr = LCTRL+RALT synthesis.
    """
    if mod & _KMOD_MODE:
        return False  # AltGr present → never a grown-up combo
    if not (mod & _KMOD_CTRL):
        return False  # need a Ctrl (either side is fine)
    return bool(mod & _KMOD_LALT)  # the Alt side MUST be the left one


def grown_up_combo(event) -> "str | None":
    """Return 'quit'/'options' for a KEYDOWN grown-up combo, else None.

    None for non-KEYDOWN events, non-combo keys, or any chord that fails the
    AltGr-safe modifier test (see mods_are_grown_up). Imports pygame lazily
    (runtime-only) for the event/key constants — never at module load.
    """
    import pygame  # cached: the running app initialised pygame long ago

    if event.type != pygame.KEYDOWN:
        return None
    if not mods_are_grown_up(event.mod):
        return None
    if event.key == pygame.K_q:
        return QUIT
    if event.key == pygame.K_o:
        return OPTIONS
    return None
