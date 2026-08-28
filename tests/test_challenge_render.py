# Tests for the challenge target overlay in mashpad.render — the ghost/flood
# glyph, the keep-out box and the spawn rejection that keeps smash glyphs off it.
#
# Runs each scenario in a subprocess (like test_menu.py / test_audio_effect_
# fallback.py) so mashpad.render / pygame are never imported into the pytest
# process and cannot break the purity assertions in test_keymap.py and friends.

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
import os, sys, random
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame
pygame.init()
screen = pygame.display.set_mode((1280, 720))

from mashpad import config, paths, render
from mashpad.challenge import View

FONT = pygame.font.Font(str(paths.app_root() / "assets" / "DejaVuSans-Bold.ttf"),
                        int(config.ITEM_SIZE_PX * 0.9))


def view(target="b", progress=0, step=0, art=None, kind="letter"):
    return View(kind=kind, target=target, answer=(target,), progress=progress,
                step=step, gimme=step >= 3, art=art)


def brightest(surface, box=None):
    x0, y0, x1, y1 = box or (0, 0, surface.get_width(), surface.get_height())
    return max((surface.get_at((x, y)) for x in range(x0, x1, 2)
                for y in range(y0, y1, 2)), key=lambda c: c[0] + c[1] + c[2])


def ink_right(surface, y0=200, y1=520):
    # Rightmost column holding anything but the background, or None.
    for x in range(surface.get_width() - 1, -1, -2):
        for y in range(y0, y1, 4):
            if surface.get_at((x, y))[:3] != render.BACKGROUND:
                return x
    return None
"""


def test_keepout_is_centred_and_scaled_from_the_item_size():
    _ok(r"""
x, y, w, h = render.challenge_keepout(1280, 720)
assert w == h == config.ITEM_SIZE_PX * config.CHALLENGE_KEEPOUT_SCALE, (w, h)
assert abs((x + w / 2) - 640) < 1e-9 and abs((y + h / 2) - 360) < 1e-9, (x, y)
""")


def test_spawn_position_never_lands_inside_the_keepout():
    _ok(r"""
rng = random.Random(11)
box = render.challenge_keepout(1280, 720)
bx, by, bw, bh = box
half = config.ITEM_SIZE_PX / 2.0
for _ in range(2000):
    px, py = render.spawn_position(rng, 1280, 720, half, box)
    assert half <= px <= 1280 - half and half <= py <= 720 - half, (px, py)
    assert not (bx <= px <= bx + bw and by <= py <= by + bh), (px, py)
""")


def test_spawn_position_without_a_keepout_is_the_plain_uniform_draw():
    _ok(r"""
half = config.ITEM_SIZE_PX / 2.0
a = random.Random(5)
b = random.Random(5)
got = render.spawn_position(a, 1280, 720, half, None)
want = (b.uniform(half, 1280 - half), b.uniform(half, 720 - half))
assert got == want, (got, want)
""")


def test_target_is_uppercase_whatever_letter_case_says():
    _ok(r"""
# The director's pool is lowercase; keycaps are not, and a ghost 'b' reads as
# a 'd'. The cache key records exactly which text was rendered.
render._TARGET_CACHE.clear()
screen.fill(render.BACKGROUND)
render.draw_challenge_target(screen, view("b"), FONT, None, 0.0)
keys = list(render._TARGET_CACHE)
assert keys and all(k[0] == "B" for k in keys), keys
render.draw_challenge_target(screen, view("b", progress=1), FONT, None, 0.0)
assert all(k[0] == "B" for k in render._TARGET_CACHE), list(render._TARGET_CACHE)
""")


def test_ghost_is_hollow_and_dim_while_the_flood_is_solid_and_full():
    _ok(r"""
screen.fill(render.BACKGROUND)
render.draw_challenge_target(screen, view("b", progress=0), FONT, None, 0.0)
ghost = brightest(screen, (500, 200, 800, 520))

screen.fill(render.BACKGROUND)
render.draw_challenge_target(screen, view("b", progress=1), FONT, None, 0.0)
flood = brightest(screen, (500, 200, 800, 520))

assert sum(flood[:3]) > sum(ghost[:3]), (flood, ghost)
assert flood[:3] == render.challenge_target_color("b"), flood
assert ghost[:3] != render.BACKGROUND, "the ghost must be visible at all"

# Hollow: the middle of a stroke-free interior region stays background.
screen.fill(render.BACKGROUND)
render.draw_challenge_target(screen, view("b", progress=0), FONT, None, 0.0)
interior = screen.get_at((600, 300))
assert interior[:3] == render.BACKGROUND, interior
""")


def test_ghost_pulses_only_from_hint_step_one():
    _ok(r"""
period = render.CHALLENGE_PULSE_PERIOD_S
assert render.challenge_ghost_alpha(0, 0.0) == render.CHALLENGE_GHOST_ALPHA
assert render.challenge_ghost_alpha(0, period / 4) == render.CHALLENGE_GHOST_ALPHA
peak = render.challenge_ghost_alpha(1, period / 4)
trough = render.challenge_ghost_alpha(1, 3 * period / 4)
assert peak > trough, (peak, trough)
assert trough >= render.CHALLENGE_GHOST_ALPHA - 1, trough
assert peak <= render.CHALLENGE_PULSE_ALPHA, peak
""")


def test_step_two_pops_the_sticker_only_when_the_target_has_art():
    _ok(r"""
art = pygame.Surface((120, 120), pygame.SRCALPHA)
art.fill((0, 255, 0, 255))
images = {"balloon": art}

def right_half_ink(v):
    screen.fill(render.BACKGROUND)
    render.draw_challenge_target(screen, v, FONT, images, 0.0)
    return ink_right(screen)

no_art = right_half_ink(view("b", step=2, art=None))
with_art = right_half_ink(view("b", step=2, art="balloon"))
assert with_art > no_art, (with_art, no_art)
# A target whose art name has no loaded image falls back to the plain ghost.
missing = right_half_ink(view("b", step=2, art="nosuchart"))
assert missing == no_art, (missing, no_art)
# Below step 2 the sticker stays away.
early = right_half_ink(view("b", step=1, art="balloon"))
assert early == no_art, (early, no_art)
""")


def test_the_surface_cache_is_content_addressed_and_bounded():
    _ok(r"""
render._TARGET_CACHE.clear()
first = render._target_surface("B", (255, 255, 0), False, FONT)
again = render._target_surface("B", (255, 255, 0), False, FONT)
assert first is again, "same content must not be re-rendered"
other = render._target_surface("B", (255, 255, 0), True, FONT)
assert other is not first, "found and ghost are different surfaces"
for i in range(render._TARGET_CACHE_MAX + 4):
    render._target_surface(chr(ord("A") + i), (255, 0, 0), False, FONT)
assert len(render._TARGET_CACHE) <= render._TARGET_CACHE_MAX, len(render._TARGET_CACHE)
""")


def test_drawing_a_missing_view_is_a_no_op():
    _ok(r"""
screen.fill(render.BACKGROUND)
render.draw_challenge_target(screen, None, FONT, None, 0.0)
assert ink_right(screen, 0, 720) is None, "nothing should have been drawn"
""")
