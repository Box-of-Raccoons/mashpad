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


# ---------------------------------------------------------------------------
# Counting blocks
# ---------------------------------------------------------------------------

_BLOCKS = r"""
from mashpad import counting
from mashpad.challenge import View

SLOT_FONT = pygame.font.Font(str(paths.app_root() / "assets" / "DejaVuSans-Bold.ttf"),
                             config.CHALLENGE_SLOT_PX)


def sum_view(target="3+2", progress=0, step=0, step_at=None, gimme=False):
    return View(kind="math", target=target, answer=counting.answer(target),
                progress=progress, step=step, gimme=gimme, art=None,
                filled_at=None, step_at=step_at)


def draw(v, now=0.0, guided=True):
    screen.fill(render.BACKGROUND)
    render.draw_challenge_blocks(screen, v, SLOT_FONT, now, guided=guided)
    return render.challenge_blocks_layout(screen.get_width(), screen.get_height(),
                                          v.target, len(v.answer), guided)


def colors_in(rect):
    return {tuple(screen.get_at((x, y))[:3])
            for x in range(max(0, rect.left), min(screen.get_width(), rect.right), 2)
            for y in range(max(0, rect.top), min(screen.get_height(), rect.bottom), 2)}


def numeral_box(layout, group="a"):
    r = layout["rect_" + group]
    top = r.bottom + render.CHALLENGE_NUM_GAP_PX
    return pygame.Rect(r.left - 40, top, r.width + 80, config.CHALLENGE_SLOT_PX)


DARK = render.BACKGROUND
"""


def test_the_two_groups_take_colours_far_apart_in_hue():
    _ok(_BLOCKS + r"""
# No blue beside azure: a pairing the child cannot tell apart teaches nothing.
for target, _answer in counting.pool("0-20"):
    a, b = render.challenge_block_colors(target)
    i, j = config.PALETTE.index(a), config.PALETTE.index(b)
    apart = min((i - j) % len(config.PALETTE), (j - i) % len(config.PALETTE))
    assert apart >= render.CHALLENGE_HUE_SEPARATION, (target, i, j, apart)
""")


def test_block_colours_do_not_change_between_runs():
    _ok(_BLOCKS + r"""
# The overlay is rebuilt from view() every frame, so the colour has to be a
# function of the target and nothing else. hash() is salted per process.
assert render.challenge_block_colors("7+4") == render.challenge_block_colors("7+4")
""")


def test_an_addition_draws_one_block_per_thing_being_counted():
    _ok(_BLOCKS + r"""
layout = draw(sum_view("4+3"))
assert len(layout["blocks_a"]) == 4, len(layout["blocks_a"])
assert len(layout["blocks_b"]) == 3, len(layout["blocks_b"])
w, h = screen.get_size()
for rect in layout["blocks_a"] + layout["blocks_b"]:
    assert 0 <= rect.left and rect.right <= w, rect
""")


def test_each_numeral_is_drawn_in_its_own_group_colour():
    _ok(_BLOCKS + r"""
# The colour pairing IS the teaching mechanic: a child who cannot read "3" can
# still see that the blue numeral belongs to the blue pile.
v = sum_view("4+3")
layout = draw(v)
color_a, color_b = render.challenge_block_colors(v.target)
assert color_a in colors_in(numeral_box(layout, "a")), color_a
assert color_b in colors_in(numeral_box(layout, "b")), color_b
""")


def test_a_subtraction_has_one_group_and_one_colour():
    _ok(_BLOCKS + r"""
# The blocks leave rather than a second colour arriving, so the group never
# reads as two piles waiting to be added.
v = sum_view("5-2")
layout = draw(v)
assert len(layout["blocks_a"]) == 5
assert layout["blocks_b"] == []
_color_a, color_b = render.challenge_block_colors(v.target)
assert color_b not in colors_in(pygame.Rect(0, 0, *screen.get_size()))
# The two that left drained to grey.
assert config.CHALLENGE_BLOCK_GONE_COLOR in colors_in(
    pygame.Rect(layout["rect_a"].left, layout["rect_a"].top - 20,
                layout["rect_a"].width + 60, layout["rect_a"].height + 60))
""")


def test_the_guided_pile_shows_the_total_and_advanced_does_not():
    _ok(_BLOCKS + r"""
# Hardy's call: show the count with the blocks, never ghost the numeral.
layout = draw(sum_view("4+3"), guided=True)
assert len(layout["result"]) == 7, len(layout["result"])
cell = layout["cells"][0]
assert colors_in(cell) != {DARK}
layout = draw(sum_view("4+3"), guided=False)
assert layout["result"] == []
assert colors_in(layout["cells"][0]) == {DARK}
""")


def test_the_pile_clears_once_a_digit_lands():
    _ok(_BLOCKS + r"""
# The numeral takes that space, so the two must never be drawn on top of
# each other.
layout = draw(sum_view("12+5", progress=1))
assert colors_in(layout["cells"][1]) == {DARK}
""")


def test_the_answer_is_never_shown_before_the_gimme():
    _ok(_BLOCKS + r"""
# Guided shows the quantity, not the numeral; the numeral is the ask. The
# answer glyph is the only near-white thing that can appear in a cell — no
# PALETTE colour has all three channels high.
def numeral_pixels(cell):
    return sum(1 for c in colors_in(cell) if min(c) > 200)

for guided in (True, False):
    layout = draw(sum_view("5-2"), guided=guided)
    assert numeral_pixels(layout["cells"][0]) == 0, guided
# The last rung hands it over: that is what the gimme is for.
layout = draw(sum_view("5-2", step=3, gimme=True, step_at=0.0))
assert numeral_pixels(layout["cells"][0]) > 0
""")


def test_a_counting_hint_lights_one_block_at_a_time():
    _ok(_BLOCKS + r"""
v = sum_view("4+3", step=1, step_at=10.0)
cad = config.CHALLENGE_COUNT_CADENCE_S
assert render.challenge_count_lit(v, 10.0) == (1, 0)
assert render.challenge_count_lit(v, 10.0 + 1.5 * cad) == (2, 0)
assert render.challenge_count_lit(v, 10.0 + 9 * cad) == (4, 0)   # never past the group
v2 = sum_view("4+3", step=2, step_at=10.0)
assert render.challenge_count_lit(v2, 10.0) == (4, 1)            # first pile stays lit
v3 = sum_view("4+3", step=3, step_at=10.0)
assert render.challenge_count_lit(v3, 10.0 + 5 * cad) == (4, 2)  # counts the whole line
""")


def test_outside_a_hint_every_block_is_lit():
    _ok(_BLOCKS + r"""
# The blocks are the sum, not a quiz — they only dim while a hint is counting.
assert render.challenge_count_lit(sum_view("4+3"), 99.0) == (4, 3)
assert render.challenge_count_lit(sum_view("5-2"), 99.0) == (5, 0)
""")


def test_a_subtraction_hint_counts_the_survivors_after_the_first_rung():
    _ok(_BLOCKS + r"""
cad = config.CHALLENGE_COUNT_CADENCE_S
whole = sum_view("5-2", step=1, step_at=0.0)
assert render.challenge_count_lit(whole, 9 * cad) == (5, 0)
left = sum_view("5-2", step=2, step_at=0.0)
assert render.challenge_count_lit(left, 9 * cad) == (3, 0)
""")


def test_a_counting_round_keeps_smash_glyphs_off_the_equation():
    _ok(_BLOCKS + r"""
from mashpad.challenge import Round
w, h = screen.get_size()
round_ = Round(kind="math", target="15+5", answer=("2", "0"), art=None)
box = render.challenge_round_keepout(w, h, round_)
layout = render.challenge_blocks_layout(w, h, round_.target, 2, True)
bx, by, bw, bh = box
rect = pygame.Rect(int(bx), int(by), int(bw), int(bh))
for r in layout["blocks_a"] + layout["blocks_b"] + layout["cells"]:
    assert rect.contains(r), (rect, r)
rng = random.Random(4)
half = config.ITEM_SIZE_PX / 2.0
for _ in range(500):
    x, y = render.spawn_position(rng, w, h, half, box)
    assert not (bx <= x <= bx + bw and by <= y <= by + bh), (x, y)
""")


def test_the_widest_equation_still_fits_the_windowed_default():
    _ok(_BLOCKS + r"""
# 1280x720 is the --windowed default and the narrowest screen the app runs on.
for target, answer in counting.pool("0-20"):
    layout = render.challenge_blocks_layout(1280, 720, target, len(answer), True)
    for r in (layout["blocks_a"] + layout["blocks_b"] + layout["result"]
              + layout["cells"]):
        assert 0 <= r.left and r.right <= 1280, (target, r)
        assert 0 <= r.top and r.bottom <= 720, (target, r)
""")


def test_the_keepout_covers_the_numerals_under_a_wide_subtraction():
    _ok(_BLOCKS + r"""
# "16 - 15" is three glyphs under a group five blocks across, so it reaches
# wider than any rect the layout returns.
from mashpad.challenge import Round
w, h = screen.get_size()
round_ = Round(kind="math", target="16-15", answer=("1",), art=None)
bx, by, bw, bh = render.challenge_round_keepout(w, h, round_)
box = pygame.Rect(int(bx), int(by), int(bw), int(bh))
v = sum_view("16-15")
layout = draw(v)
lit = pygame.Rect(0, 0, 0, 0)
for x in range(0, w, 2):
    for y in range(0, h, 2):
        if tuple(screen.get_at((x, y))[:3]) != render.BACKGROUND:
            lit = pygame.Rect(x, y, 1, 1) if lit.width == 0 else lit.union(
                pygame.Rect(x, y, 1, 1))
assert box.contains(lit), (box, lit)
""")


def test_every_sum_in_every_tier_draws_without_raising():
    _ok(_BLOCKS + r"""
# Cheap net for the edges the layout has to survive: a total of zero draws no
# answer pile at all, and a group of one draws a single-column grid.
for tier in ("2-9", "0-20"):
    for target, answer in counting.pool(tier):
        for guided in (True, False):
            for step in (0, 1, 2, 3):
                v = sum_view(target, step=step, step_at=0.0, gimme=step >= 3)
                screen.fill(render.BACKGROUND)
                render.draw_challenge_blocks(screen, v, SLOT_FONT, 1.0,
                                             guided=guided)
assert counting.answer("5-5") == ("0",)
layout = draw(sum_view("5-5"))
assert layout["result"] == []          # nothing left to show
""")


# ---------------------------------------------------------------------------
# Glyph clearance: a smash letter must not land ON the answer
# ---------------------------------------------------------------------------

_CLEAR = r"""
from mashpad.challenge import Round

REACH = config.ITEM_SIZE_PX * config.CHALLENGE_ITEM_SCALE / 2.0
HALF = config.ITEM_SIZE_PX / 2.0


def spell_round(word):
    return Round(kind="spell", target=word, answer=tuple(word), art=word)


def drawn_bounds(w, h, word):
    art, cells = render.challenge_slot_layout(w, h, len(word))
    box = art.copy()
    for c in cells:
        box.union_ip(c)
    return box


def worst_overlap(w, h, round_, drawn, samples=400):
    # Widest a spawned glyph's own rect pushes into what the overlay draws.
    box = render.challenge_round_keepout(w, h, round_)
    rng = random.Random(19)
    worst = 0
    for _ in range(samples):
        x, y = render.spawn_position(rng, w, h, HALF, box)
        item = pygame.Rect(0, 0, int(2 * REACH), int(2 * REACH))
        item.center = (int(x), int(y))
        hit = item.clip(drawn)
        worst = max(worst, min(hit.width, hit.height))
    return worst
"""


def test_a_smash_glyph_never_lands_on_the_word_being_spelled():
    _ok(_CLEAR + r"""
# The keep-out constrains a spawn's centre, and a challenge glyph is 196px
# across, so the box has to carry half a glyph of clearance or letters land on
# the row. This is the bug in the DRUM screenshot.
for w, h in ((1280, 720), (1920, 1080)):
    for word in config.SPELL_WORDS_GUIDED:
        drawn = drawn_bounds(w, h, word)
        assert worst_overlap(w, h, spell_round(word), drawn) == 0, (w, h, word)
""")


def test_the_advanced_words_stay_clear_at_the_pi_resolution():
    _ok(_CLEAR + r"""
for word in config.SPELL_WORDS_ADVANCED:
    drawn = drawn_bounds(1920, 1080, word)
    assert worst_overlap(1920, 1080, spell_round(word), drawn) == 0, word
""")


def test_the_longest_word_degrades_on_a_narrow_screen_rather_than_giving_up():
    _ok(_CLEAR + r"""
# BUBBLES is seven slots. At 1280x720 the row plus full clearance is wider than
# every spawn position the screen has, so the clearance shrinks until a band
# survives. That is a smaller overlap, not the unconstrained sample a vanished
# band would produce.
drawn = drawn_bounds(1280, 720, "bubbles")
got = worst_overlap(1280, 720, spell_round("bubbles"), drawn)
assert got < REACH / 2, got
# The box still excludes centres outright, which is the floor this can reach.
box = render.challenge_round_keepout(1280, 720, spell_round("bubbles"))
bx, by, bw, bh = box
rng = random.Random(2)
for _ in range(400):
    x, y = render.spawn_position(rng, 1280, 720, HALF, box)
    assert not (bx <= x <= bx + bw and by <= y <= by + bh), (x, y)
""")


def test_a_smash_glyph_never_lands_on_a_counting_sum():
    _ok(_CLEAR + r"""
from mashpad import counting
for tier, (w, h) in (("2-9", (1280, 720)), ("0-20", (1920, 1080))):
    for target, answer in counting.pool(tier):
        round_ = Round(kind="math", target=target, answer=answer, art=None)
        layout = render.challenge_blocks_layout(w, h, target, len(answer), True)
        drawn = render._bounds(layout["blocks_a"] + layout["blocks_b"]
                               + layout["result"] + layout["cells"])
        assert worst_overlap(w, h, round_, drawn, samples=60) == 0, (tier, target)
""")


def test_the_plain_target_gets_the_same_clearance():
    _ok(_CLEAR + r"""
# One rule for all five challenges: the ghost letter is 280px and a smash glyph
# reaching 98px into it was always a near miss.
w, h = 1280, 720
box = render.challenge_round_keepout(w, h, None)
glyph = pygame.Rect(0, 0, config.ITEM_SIZE_PX, config.ITEM_SIZE_PX)
glyph.center = (w // 2, h // 2)
rng = random.Random(8)
for _ in range(400):
    x, y = render.spawn_position(rng, w, h, HALF, box)
    item = pygame.Rect(0, 0, int(2 * REACH), int(2 * REACH))
    item.center = (int(x), int(y))
    hit = item.clip(glyph)
    assert min(hit.width, hit.height) == 0, (x, y)
""")
