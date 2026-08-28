# Tests for the challenge wiring helpers in mashpad.main — which stems each
# ladder rung speaks, and which settings actually build a director.
#
# Runs each scenario in a subprocess (like test_menu.py) so mashpad.main /
# pygame are never imported into the pytest process and cannot break the purity
# assertions in test_keymap.py and friends.

import subprocess
import sys


def _run(body: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _PRE + body],
                          capture_output=True, text=True)


def _ok(body: str) -> None:
    """Run *body* in a subprocess; fail the test with its stderr if it raises."""
    proc = _run(body)
    assert proc.returncode == 0, proc.stderr or proc.stdout


_PRE = r"""
import os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from mashpad import main as main_mod
from mashpad.challenge import Round

LETTER = Round(kind="letter", target="b", answer=("b",), art="balloon")
BARE = Round(kind="letter", target="q", answer=("q",), art=None)
NUMBER = Round(kind="number", target="7", answer=("7",), art=None)
stems = main_mod._challenge_stems
"""


def test_the_ask_names_the_kind_of_thing_being_hunted():
    _ok(r"""
assert stems(LETTER, 0) == ("find-the-letter", "b"), stems(LETTER, 0)
assert stems(NUMBER, 0) == ("find-the-number", "7"), stems(NUMBER, 0)
""")


def test_hint_one_repeats_the_whole_ask():
    _ok(r"""
assert stems(LETTER, 1) == stems(LETTER, 0)
assert stems(NUMBER, 1) == stems(NUMBER, 0)
""")


def test_hint_two_uses_the_art_when_the_target_has_some():
    _ok(r"""
assert stems(LETTER, 2) == ("b", "for", "balloon"), stems(LETTER, 2)
# 19 of 26 letters have no sticker; those fall back to the bare target.
assert stems(BARE, 2) == ("q",), stems(BARE, 2)
""")


def test_hint_three_is_always_the_bare_target():
    _ok(r"""
assert stems(LETTER, 3) == ("b",), stems(LETTER, 3)
assert stems(BARE, 3) == ("q",), stems(BARE, 3)
assert stems(NUMBER, 3) == ("7",), stems(NUMBER, 3)
""")


def test_a_parked_round_re_announces_with_the_full_carrier():
    _ok(r"""
# challenge.poll emits ("hint", 0) when a parked round wakes up; a child back
# after twenty minutes gets no context from a bare "B".
assert stems(LETTER, 0) == ("find-the-letter", "b")
""")


def test_only_shipped_challenges_can_build_a_director():
    _ok(r"""
from mashpad.menu import IMPLEMENTED_CHALLENGES
from mashpad import settings as settings_mod

# main() only builds a director for a value the menu can actually select, so a
# hand-edited settings.json naming a later slice cannot draw from an empty pool.
assert set(IMPLEMENTED_CHALLENGES) <= set(settings_mod.CHALLENGES)
assert "spell" not in IMPLEMENTED_CHALLENGES
assert "math" not in IMPLEMENTED_CHALLENGES
assert "letter" in IMPLEMENTED_CHALLENGES and "number" in IMPLEMENTED_CHALLENGES
""")
