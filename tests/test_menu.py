# Tests for mashpad.menu — the grown-up options overlay.
#
# menu.py had no tests at all before the challenge rows were added, and adding
# rows meant editing three lists that had to stay in sync by hand (_ROW_* index
# constants, _rows(), and the _step dispatch). These characterize the behavior
# that must survive making _rows() the single source of truth, so they are
# deliberately written against labels rather than row indices.
#
# Runs each scenario in a subprocess (like test_audio_effect_fallback.py) so
# mashpad.menu / pygame are never imported into the pytest process and cannot
# break the purity assertions in test_keymap.py and friends.

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
import os, sys, tempfile
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
from pathlib import Path

import pygame
pygame.init()
pygame.display.set_mode((1280, 720))

from mashpad import paths, settings as settings_mod
from mashpad.menu import Menu


class FakeAudio:
    def __init__(self):
        self.auditioned = []
        self.notes = []
        self.master = None

    @property
    def voices(self):
        return ["achernar", "charon"]

    def set_master_volume(self, v):
        self.master = v

    def play_for(self, spec, rng, voice=None, note=None):
        self.auditioned.append(voice)

    def play_note(self, name):
        self.notes.append(name)
        return True


def make():
    path = Path(tempfile.mkdtemp()) / "settings.json"
    s = settings_mod.Settings()
    a = FakeAudio()
    font = paths.app_root() / "assets" / "DejaVuSans-Bold.ttf"
    m = Menu(s, a, font, path)
    m.open()
    return m, s, a


def labels(m):
    return [label for label, _ in m._rows()]


def select(m, label):
    m._selected = labels(m).index(label)


def key(k, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="", scancode=0)
"""


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------

def test_row_order_is_stable():
    _ok("""
m, s, a = make()
assert labels(m)[:7] == ["Voice", "Volume", "Letters", "Raccoons",
                         "Phrases", "Sounds", "Display"], labels(m)
assert labels(m)[-1] == "Quit", labels(m)
""")


def test_open_resets_the_highlight_to_the_top():
    _ok("""
m, s, a = make()
m._selected = 3
m.open()
assert m._selected == 0
""")


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

def test_down_advances_and_wraps():
    _ok("""
m, s, a = make()
n = len(m._rows())
for i in range(n):
    assert m._selected == i
    m.handle_event(key(pygame.K_DOWN))
assert m._selected == 0, "down did not wrap to the top"
""")


def test_up_wraps_backwards():
    _ok("""
m, s, a = make()
n = len(m._rows())
m.handle_event(key(pygame.K_UP))
assert m._selected == n - 1, "up did not wrap to the bottom"
""")


# ---------------------------------------------------------------------------
# Row behavior
# ---------------------------------------------------------------------------

def test_letters_row_toggles_case():
    _ok("""
m, s, a = make()
select(m, "Letters")
m.handle_event(key(pygame.K_RIGHT))
assert s.letter_case == "lower", s.letter_case
m.handle_event(key(pygame.K_LEFT))
assert s.letter_case == "upper", s.letter_case
""")


def test_volume_steps_by_ten_and_clamps():
    _ok("""
m, s, a = make()
select(m, "Volume")
m.handle_event(key(pygame.K_RIGHT))
assert s.volume == 90, s.volume
m.handle_event(key(pygame.K_RIGHT))
assert s.volume == 100, s.volume
m.handle_event(key(pygame.K_RIGHT))
assert s.volume == 100, "volume passed its ceiling"
assert a.master == 1.0, a.master
""")


def test_raccoons_clamps_without_wrapping():
    _ok("""
m, s, a = make()
select(m, "Raccoons")
m.handle_event(key(pygame.K_LEFT))
assert s.raccoon_amount == "less", s.raccoon_amount
m.handle_event(key(pygame.K_LEFT))
assert s.raccoon_amount == "less", "raccoons wrapped instead of clamping"
""")


def test_phrases_row_toggles():
    _ok("""
m, s, a = make()
select(m, "Phrases")
m.handle_event(key(pygame.K_RIGHT))
assert s.phrases is False
m.handle_event(key(pygame.K_RIGHT))
assert s.phrases is True
""")


def test_sounds_row_toggles_and_auditions_a_note():
    _ok("""
m, s, a = make()
select(m, "Sounds")
m.handle_event(key(pygame.K_RIGHT))
assert s.sound_mode == "dings", s.sound_mode
m.handle_event(key(pygame.K_RIGHT))
assert s.sound_mode == "piano", s.sound_mode
assert a.notes, "switching to piano did not audition a note"
""")


def test_display_row_toggles():
    _ok("""
m, s, a = make()
select(m, "Display")
m.handle_event(key(pygame.K_RIGHT))
assert s.display_mode == "babyide", s.display_mode
m.handle_event(key(pygame.K_RIGHT))
assert s.display_mode == "smash", s.display_mode
""")


def test_voice_row_cycles_and_auditions_a_pack():
    _ok("""
m, s, a = make()
select(m, "Voice")
m.handle_event(key(pygame.K_RIGHT))
assert s.voice_mode in ("achernar", "charon", "random", "cycle"), s.voice_mode
seen = set()
for _ in range(8):
    seen.add(s.voice_mode)
    m.handle_event(key(pygame.K_RIGHT))
assert {"achernar", "charon", "random", "cycle"} <= seen, seen
assert a.auditioned, "selecting a concrete voice did not audition it"
""")


# ---------------------------------------------------------------------------
# Challenge rows
# ---------------------------------------------------------------------------

def test_challenge_row_offers_only_implemented_values():
    """spell and math must not be selectable before their slices land."""
    _ok("""
from mashpad.menu import IMPLEMENTED_CHALLENGES
m, s, a = make()
select(m, "Challenge")
seen = set()
for _ in range(len(IMPLEMENTED_CHALLENGES) + 2):
    seen.add(s.challenge)
    m.handle_event(key(pygame.K_RIGHT))
assert seen == set(IMPLEMENTED_CHALLENGES), seen
assert "spell" not in seen and "math" not in seen, seen
""")


def test_challenge_row_steps_backwards_too():
    _ok("""
m, s, a = make()
select(m, "Challenge")
m.handle_event(key(pygame.K_LEFT))
assert s.challenge != "none", s.challenge
""")


def test_answers_row_appears_only_for_spell_and_math():
    _ok("""
m, s, a = make()
assert "Answers" not in labels(m)
for value in ("spell", "math"):
    s.challenge = value
    assert "Answers" in labels(m), (value, labels(m))
s.challenge = "letter"
assert "Answers" not in labels(m), labels(m)
""")


def test_numbers_row_appears_only_for_math():
    _ok("""
m, s, a = make()
s.challenge = "spell"
assert "Numbers" not in labels(m), labels(m)
s.challenge = "math"
assert "Numbers" in labels(m), labels(m)
""")


def test_answers_and_numbers_rows_toggle():
    _ok("""
m, s, a = make()
s.challenge = "math"
select(m, "Answers")
m.handle_event(key(pygame.K_RIGHT))
assert s.answer_style == "advanced", s.answer_style
select(m, "Numbers")
m.handle_event(key(pygame.K_RIGHT))
assert s.math_range == "0-20", s.math_range
""")


def test_highlight_clamps_when_rows_disappear():
    """Sitting on the last row when the list shrinks must not index off the end."""
    _ok("""
m, s, a = make()
s.challenge = "math"
m._selected = len(m._rows()) - 1
s.challenge = "none"
m.handle_event(key(pygame.K_RIGHT))
assert m._selected < len(m._rows()), (m._selected, len(m._rows()))
""")


def test_panel_fits_with_every_row_visible():
    _ok("""
m, s, a = make()
s.challenge = "math"
assert len(m._rows()) == 11, labels(m)
screen = pygame.Surface((1280, 720))
m.draw(screen)
assert m.panel_height(720) <= 720, m.panel_height(720)
assert m.panel_height(1080) <= 1080, m.panel_height(1080)
""")


# ---------------------------------------------------------------------------
# Closing and quitting
# ---------------------------------------------------------------------------

def test_enter_on_quit_returns_quit():
    _ok("""
m, s, a = make()
select(m, "Quit")
assert m.handle_event(key(pygame.K_RETURN)) == "quit"
""")


def test_escape_closes_and_persists():
    _ok("""
m, s, a = make()
select(m, "Letters")
m.handle_event(key(pygame.K_RIGHT))
m.handle_event(key(pygame.K_ESCAPE))
assert not m.visible
assert settings_mod.load(m._save_path).letter_case == "lower"
""")


def test_every_row_survives_a_left_and_a_right():
    """No row may raise on either arrow, including value-less rows like Quit."""
    _ok("""
m, s, a = make()
for i in range(len(m._rows())):
    m._selected = i
    m.handle_event(key(pygame.K_LEFT))
    m.handle_event(key(pygame.K_RIGHT))
""")


# ---------------------------------------------------------------------------
# The panel has to fit on the screen
# ---------------------------------------------------------------------------

def test_panel_fits_the_pi_screen():
    _ok("""
m, s, a = make()
screen = pygame.Surface((1920, 1080))
m.draw(screen)
assert m.panel_height(1080) <= 1080, m.panel_height(1080)
""")


def test_panel_fits_the_windowed_default():
    """1280x720 is the --windowed dev default; the panel overflowed it before."""
    _ok("""
m, s, a = make()
screen = pygame.Surface((1280, 720))
m.draw(screen)
assert m.panel_height(720) <= 720, m.panel_height(720)
""")
