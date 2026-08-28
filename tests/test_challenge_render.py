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


# ---------------------------------------------------------------------------
# The spelling slot row
# ---------------------------------------------------------------------------

_SLOTS = r"""
from mashpad.challenge import View

SLOT_FONT = pygame.font.Font(str(paths.app_root() / "assets" / "DejaVuSans-Bold.ttf"),
                             config.CHALLENGE_SLOT_PX)


def word_view(word="book", progress=0, filled_at=None, art=None, step=0):
    return View(kind="spell", target=word, answer=tuple(word), progress=progress,
                step=step, gimme=False, art=art, filled_at=filled_at)


def draw(v, now=0.0, guided=True, images=None):
    screen.fill(render.BACKGROUND)
    render.draw_challenge_slots(screen, v, SLOT_FONT, images, now, guided=guided)
    return render.challenge_slot_layout(screen.get_width(), screen.get_height(),
                                        len(v.answer))


def peak(rect):
    # Brightest pixel inside rect, as an R+G+B sum.
    return max(sum(screen.get_at((x, y))[:3])
               for x in range(rect.left, rect.right, 2)
               for y in range(rect.top, rect.bottom, 2))


DARK = sum(render.BACKGROUND)
"""


def test_a_spelling_row_has_one_slot_per_letter():
    _ok(_SLOTS + r"""
_art, cells = draw(word_view("bubbles"))
assert len(cells) == 7, len(cells)
w, h = screen.get_size()
assert cells[0].left >= 0 and cells[-1].right <= w
assert all(cells[i].right <= cells[i + 1].left for i in range(len(cells) - 1))
# The block is centred: equal slack either side.
assert abs((cells[0].left) - (w - cells[-1].right)) <= 2
""")


def test_the_current_slot_is_the_brightest_letter_in_the_row():
    _ok(_SLOTS + r"""
# The glow IS the instruction, so exactly one slot may be bright — at every
# point of the pulse, including its trough, where a completed letter at full
# colour would otherwise match it.
period = render.CHALLENGE_PULSE_PERIOD_S
for now in (period / 4.0, period * 0.75):            # glow peak, then trough
    _art, cells = draw(word_view("book", progress=1), now=now)
    assert peak(cells[1]) > peak(cells[0]), (now, peak(cells[1]), peak(cells[0]))
    assert peak(cells[1]) > peak(cells[2]), (now, peak(cells[1]), peak(cells[2]))
""")


def test_a_landing_slot_holds_the_next_one_dark_until_it_settles():
    _ok(_SLOTS + r"""
# The double-letter rule: after the first O of BOOK the glow must not simply
# slide to an identical O. The filled letter lands first, and only then does the
# next slot light.
v = word_view("book", progress=1, filled_at=1.0)
_art, cells = draw(v, now=1.0)
assert peak(cells[0]) > peak(cells[1])          # the landing flash
during = peak(cells[1])

after = 1.0 + config.CHALLENGE_SLOT_LAND_S + 0.01
lit = 0
for k in range(12):                              # sweep a full pulse period
    draw(v, now=after + k * 0.1)
    lit = max(lit, peak(cells[1]))
assert lit > during, (lit, during)
""")


def test_guided_shows_the_letters_still_to_come_and_advanced_does_not():
    _ok(_SLOTS + r"""
v = word_view("book", progress=0)
_art, cells = draw(v, guided=True)
assert peak(cells[2]) > DARK, peak(cells[2])
_art, cells = draw(v, guided=False)
assert peak(cells[2]) == DARK, peak(cells[2])
# Advanced still draws the bar beneath, so the row reads as slots, not a gap.
bar = pygame.Rect(cells[2].left, cells[2].bottom, cells[2].width,
                  render.CHALLENGE_SLOT_BAR_GAP_PX + render.CHALLENGE_SLOT_BAR_PX + 2)
assert peak(bar) > DARK, peak(bar)
""")


def test_a_shape_word_is_drawn_because_it_has_no_sticker():
    _ok(_SLOTS + r"""
# STAR and RING have no PNG; they are config.SHAPES and get drawn instead.
art, _cells = draw(word_view("star", art="star"), images={})
assert peak(art) > DARK, peak(art)
art, _cells = draw(word_view("star", art=None), images={})
assert peak(art) == DARK, peak(art)
""")


def test_a_sticker_word_uses_its_image():
    _ok(_SLOTS + r"""
sticker = pygame.Surface((config.ITEM_SIZE_PX, config.ITEM_SIZE_PX), pygame.SRCALPHA)
sticker.fill((255, 0, 0, 255))
art, _cells = draw(word_view("book", art="book"), images={"book": sticker})
r, g, b = screen.get_at((art.centerx, art.centery))[:3]
assert r > 200 and g < 40 and b < 40, (r, g, b)
""")


def test_the_keepout_box_covers_the_whole_slot_overlay():
    _ok(_SLOTS + r"""
w, h = screen.get_size()
one = render.challenge_keepout(w, h, 1)
row = render.challenge_keepout(w, h, 7)
assert row[2] > one[2], (one, row)
art_rect, cells = render.challenge_slot_layout(w, h, 7)
x, y, bw, bh = row
box = pygame.Rect(int(x), int(y), int(bw), int(bh))
assert box.contains(art_rect), (box, art_rect)
assert box.contains(cells[0]) and box.contains(cells[-1])
""")


def test_a_slot_round_keeps_smash_glyphs_off_the_row():
    _ok(_SLOTS + r"""
w, h = screen.get_size()
box = render.challenge_keepout(w, h, 7)
rng = random.Random(7)
half = config.ITEM_SIZE_PX / 2.0
bx, by, bw, bh = box
for _ in range(2000):
    x, y = render.spawn_position(rng, w, h, half, box)
    assert half <= x <= w - half and half <= y <= h - half, (x, y)
    assert not (bx <= x <= bx + bw and by <= y <= by + bh), (x, y)
""")


def test_a_keepout_covering_the_screen_still_returns_a_position():
    _ok(r"""
# Degenerate but reachable on a small window: with no band left, the spawner
# hands back its sample rather than looping or raising.
half = config.ITEM_SIZE_PX / 2.0
rng = random.Random(3)
x, y = render.spawn_position(rng, 1280, 720, half, (0.0, 0.0, 1280.0, 720.0))
assert half <= x <= 1280 - half and half <= y <= 720 - half, (x, y)
""")


def test_the_finished_word_floods_to_full_brightness():
    _ok(_SLOTS + r"""
# Completed letters sit just under full colour while hunting, so the glow always
# wins; the moment the word is done there is no glow to lose to, and it floods.
mid = word_view("book", progress=1)
done = word_view("book", progress=4)
_art, cells = draw(mid, now=0.0)
hunting = peak(cells[0])
_art, cells = draw(done, now=0.0)
assert peak(cells[0]) > hunting, (peak(cells[0]), hunting)
""")


def test_advanced_does_not_light_the_letter_it_is_asking_for():
    _ok(_SLOTS + r"""
# Advanced shows only what has been won. Lighting the current letter would hand
# the answer over one slot at a time.
v = word_view("book", progress=1)
_art, cells = draw(v, now=render.CHALLENGE_PULSE_PERIOD_S / 4.0, guided=False)
assert peak(cells[1]) == DARK, peak(cells[1])
# Its bar still glows, so the child knows which slot is being asked for.
def bar(c):
    return pygame.Rect(c.left, c.bottom, c.width,
                       render.CHALLENGE_SLOT_BAR_GAP_PX
                       + render.CHALLENGE_SLOT_BAR_PX + 2)
assert peak(bar(cells[1])) > peak(bar(cells[2])), (peak(bar(cells[1])),
                                                   peak(bar(cells[2])))
""")
