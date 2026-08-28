# mashpad/render.py — all pygame drawing.
#
# Perf contract (Pi 4 target):
#   * build_item_surface() is called ONCE per item at spawn; the result is
#     cached on item.surface. The font is never re-rendered per frame.
#   * smoothscale is used ONLY while an item is SPAWNING (scale != 1.0). Once the
#     bounce completes (scale == 1.0) the cached surface is blitted directly.
#   * The mouse trail is drawn with plain filled circles whose colour is
#     premultiplied toward the background (cheaper than allocating a per-point
#     SRCALPHA surface + blit every frame — see draw_trail).
#
# pygame API used here is limited to long-stable calls present in both the Pi's
# apt pygame 2.1 and the dev machine's pygame-ce 2.5: Surface, SRCALPHA,
# transform.smoothscale, draw.circle/rect/polygon, Surface.set_alpha, font.render.

from __future__ import annotations

import colorsys
import math

import pygame

from mashpad import config, items

# Solid, very dark background — full clear each frame is cheap and avoids trails
# smearing across frames.
BACKGROUND = (12, 12, 20)

# Base radius of a fresh mouse-trail dot in pixels; shrinks with age.
TRAIL_RADIUS = 18


# ---------------------------------------------------------------------------
# Shape vertex math (all 8 config.SHAPES)
# ---------------------------------------------------------------------------

def _regular_polygon(cx, cy, r, n, start_angle=-math.pi / 2.0):
    """n vertices evenly spaced on a circle, first at start_angle (top by default)."""
    return [
        (cx + r * math.cos(start_angle + 2.0 * math.pi * k / n),
         cy + r * math.sin(start_angle + 2.0 * math.pi * k / n))
        for k in range(n)
    ]


def _star_points(cx, cy, r_out, r_in, points=5, start=-math.pi / 2.0):
    """2*points vertices alternating between outer and inner radius (5-point star)."""
    verts = []
    for k in range(points * 2):
        r = r_out if k % 2 == 0 else r_in
        a = start + math.pi * k / points
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return verts


def _heart_points(cx, cy, scale, n=72):
    """Parametric heart curve; reads clearly as a heart. y is flipped for screen space."""
    pts = []
    for i in range(n):
        t = 2.0 * math.pi * i / n
        x = 16.0 * math.sin(t) ** 3
        y = (13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t)
             - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t))
        pts.append((cx + x * scale, cy - y * scale))
    return pts


def _draw_shape(surf: "pygame.Surface", name: str, color) -> None:
    """Draw the named shape filled in `color`, centred on the square surface."""
    s = surf.get_width()
    c = s / 2.0
    r = s * 0.45                     # margin so nothing clips at the edge
    center = (int(round(c)), int(round(c)))

    if name == "circle":
        pygame.draw.circle(surf, color, center, int(round(r)))
    elif name == "ring":
        # Annulus: a thick-width circle leaves the inner disc transparent.
        pygame.draw.circle(surf, color, center, int(round(r)), int(round(r * 0.35)))
    elif name == "square":
        side = r * 1.5
        rect = pygame.Rect(0, 0, int(round(side)), int(round(side)))
        rect.center = center
        pygame.draw.rect(surf, color, rect)
    elif name == "triangle":
        pygame.draw.polygon(surf, color, _regular_polygon(c, c, r, 3))
    elif name == "diamond":
        # A square rotated 45° (vertices at top/right/bottom/left).
        pygame.draw.polygon(surf, color, _regular_polygon(c, c, r, 4))
    elif name == "pentagon":
        pygame.draw.polygon(surf, color, _regular_polygon(c, c, r, 5))
    elif name == "star":
        pygame.draw.polygon(surf, color, _star_points(c, c, r, r * 0.42))
    elif name == "heart":
        pygame.draw.polygon(surf, color, _heart_points(c, c, r / 17.0))
    else:
        # Unknown name should never reach here (keymap only emits config.SHAPES);
        # fall back to a circle rather than drawing nothing.
        pygame.draw.circle(surf, color, center, int(round(r)))


# ---------------------------------------------------------------------------
# Item surfaces
# ---------------------------------------------------------------------------

def build_item_surface(
    spec,
    font: "pygame.font.Font",
    images: "dict | None" = None,
    letter_case: str = "upper",
) -> "pygame.Surface":
    """Render an item to a fresh per-pixel-alpha surface. Called ONCE at spawn.

    The surface is always ITEM_SIZE_PX square; glyphs/shapes are centred within
    it so draw_item can scale/centre uniformly. `font` is pre-sized by the caller
    (main.py) from config.ITEM_SIZE_PX and reused for every glyph.

    *letter_case* ("upper"|"lower") picks the case for letter glyphs; digits are
    unaffected. It comes from the grown-up Settings.letter_case option.

    If *images* is provided and contains *spec.name*, that pre-scaled surface is
    returned as a fresh copy (.copy()) — each item owns its surface because
    draw_item calls set_alpha on it.  Image lookup takes priority over glyph/shape
    rendering for ANY kind: dropping ``a.png`` into assets/images/ reskins the
    letter 'a', and ``circle.png`` would reskin the circle shape.  No tinting is
    applied — brand art keeps its exact colours.
    """
    # Image lookup takes priority over glyph/shape rendering for any kind.
    if images is not None:
        img_surf = images.get(spec.name)
        if img_surf is not None:
            return img_surf.copy()

    size = config.ITEM_SIZE_PX
    surf = pygame.Surface((size, size), pygame.SRCALPHA)

    if spec.kind in ("letter", "digit"):
        if spec.kind == "letter":
            text = spec.name.lower() if letter_case == "lower" else spec.name.upper()
        else:
            text = spec.name
        glyph = font.render(text, True, spec.color)
        surf.blit(glyph, glyph.get_rect(center=(size // 2, size // 2)))
    else:
        _draw_shape(surf, spec.name, spec.color)

    return surf


def draw_item(screen: "pygame.Surface", item, now: float) -> None:
    """Blit an item's cached surface centred on item.pos, applying scale + alpha.

    smoothscale runs ONLY while SPAWNING (scale != 1.0). At scale 1.0 the cached
    surface is blitted directly. Alpha uses set_alpha: since pygame 2.0 blanket
    alpha combines with per-pixel alpha at blit time, so fading costs no copy —
    each item owns its cached surface and its alpha only ever decreases.
    """
    surf = item.surface
    if surf is None:
        return
    state = item.state(now)
    if state == items.DEAD:
        return

    scale = item.scale(now)
    if state == items.SPAWNING and scale != 1.0:
        w = max(1, int(round(surf.get_width() * scale)))
        h = max(1, int(round(surf.get_height() * scale)))
        draw_surf = pygame.transform.smoothscale(surf, (w, h))
    else:
        draw_surf = surf

    alpha = item.alpha(now)
    if alpha < 255:
        draw_surf.set_alpha(alpha)

    rect = draw_surf.get_rect(center=(int(round(item.pos[0])), int(round(item.pos[1]))))
    screen.blit(draw_surf, rect)


# ---------------------------------------------------------------------------
# Mouse trail
# ---------------------------------------------------------------------------

def draw_trail(screen: "pygame.Surface", trail, now: float) -> None:
    """Draw the fading rainbow mouse trail.

    Each live point becomes a filled circle whose radius and colour fade with
    age. Hue is reconstructed from the point's original time (now - age) so the
    trail shows a moving rainbow, not one flat colour. Colour is premultiplied
    toward BACKGROUND instead of using a per-point alpha surface — this is the
    cheaper option and matters on the Pi (no allocation/blit per point).
    """
    for pos, age_fraction in trail.points(now):
        f = 1.0 - age_fraction            # 1.0 = fresh, 0.0 = fully aged
        point_time = now - age_fraction * config.TRAIL_FADE_S
        hue = trail.hue_for(point_time)
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)  # full saturation/value
        cr = int(BACKGROUND[0] + (r * 255.0 - BACKGROUND[0]) * f)
        cg = int(BACKGROUND[1] + (g * 255.0 - BACKGROUND[1]) * f)
        cb = int(BACKGROUND[2] + (b * 255.0 - BACKGROUND[2]) * f)
        radius = int(round(TRAIL_RADIUS * f))
        if radius < 1:
            continue
        pygame.draw.circle(screen, (cr, cg, cb), (int(pos[0]), int(pos[1])), radius)


# ---------------------------------------------------------------------------
# Challenge target overlay
#
# The geometry (keep-out box, spawn positions) lives beside the drawing on
# purpose: the box the spawner avoids is defined by the glyph this file draws,
# and splitting them is how the two silently drift apart.
# ---------------------------------------------------------------------------

# Blanket alpha of the un-found ghost outline, and the brightness it breathes up
# to from hint step 1 on (a brightness pulse, not a scale pulse — scaling a
# ~300px surface every frame is a per-frame smoothscale the Pi does not need).
CHALLENGE_GHOST_ALPHA = 130
CHALLENGE_PULSE_ALPHA = 240

# Period of that breathing pulse, in seconds.
CHALLENGE_PULSE_PERIOD_S = 1.1

# Outline thickness of the ghost target, in pixels.
CHALLENGE_OUTLINE_PX = 10

# Gap between the target and the step-2 sticker, and the screen margin the
# sticker is clamped inside.
CHALLENGE_ART_GAP_PX = 40
CHALLENGE_ART_MARGIN_PX = 20


# Content-addressed cache of built target surfaces, keyed by (text, color,
# found). NOT render state: nothing here can drift out of sync with view(),
# because the key IS the content. It exists because the perf contract at the top
# of this file forbids re-rendering a 280px glyph (plus nine blits) every frame.
# Cleared wholesale past a handful of entries — a round needs at most two.
_TARGET_CACHE: dict = {}
_DILATION_CACHE: dict = {}
_TARGET_CACHE_MAX = 6


def challenge_target_color(target: str) -> tuple[int, int, int]:
    """PALETTE colour for a target, derived from the character itself.

    Derived rather than drawn at round start so the overlay can be rebuilt from
    view() alone and main.py holds no per-round render state.
    """
    return config.PALETTE[ord(target[:1] or "a") % len(config.PALETTE)]


def challenge_keepout(width: int, height: int, slots: int = 1):
    """(x, y, w, h) box around the centred target that random spawns avoid.

    *slots* > 1 is a spelling or sum round: the overlay is then a picture stacked
    over a row of answer slots, which is far wider and taller than one glyph, so
    the box grows to cover what is actually drawn. Both come from
    challenge_slot_layout, so the box and the drawing cannot drift apart.
    """
    side = config.ITEM_SIZE_PX * config.CHALLENGE_KEEPOUT_SCALE
    if slots <= 1:
        return (width / 2.0 - side / 2.0, height / 2.0 - side / 2.0, side, side)
    art_rect, cells = challenge_slot_layout(width, height, slots)
    left = min(art_rect.left, cells[0].left) - CHALLENGE_SLOT_MARGIN_PX
    right = max(art_rect.right, cells[-1].right) + CHALLENGE_SLOT_MARGIN_PX
    top = art_rect.top - CHALLENGE_SLOT_MARGIN_PX
    bottom = cells[0].bottom + CHALLENGE_SLOT_MARGIN_PX
    return (float(left), float(top), float(right - left), float(bottom - top))


def _spawn_bands(x0: float, y0: float, x1: float, y1: float, box):
    """[(area, rect), ...] tiling the spawnable rect minus the keep-out box.

    Four non-overlapping strips: full width above and below the box, then the
    slivers left and right of it within its own rows. An empty list means the
    box covers everything the caller may spawn into.
    """
    bx0, by0, bw, bh = box
    bx1, by1 = bx0 + bw, by0 + bh
    strips = (
        (x0, y0, x1, min(by0, y1)),                          # above the box
        (x0, max(by1, y0), x1, y1),                          # below it
        (x0, max(by0, y0), min(bx0, x1), min(by1, y1)),      # left of it
        (max(bx1, x0), max(by0, y0), x1, min(by1, y1)),      # right of it
    )
    return [((sx1 - sx0) * (sy1 - sy0), (sx0, sy0, sx1, sy1))
            for sx0, sy0, sx1, sy1 in strips if sx1 > sx0 and sy1 > sy0]


def spawn_position(rng, width: int, height: int, half: float, avoid=None):
    """Random on-screen spawn position, kept *half* px clear of every edge.

    With *avoid* set to a keep-out box, a sample landing inside is redrawn from
    the bands outside it rather than rejection-sampled. Rejection was fine for a
    single centred glyph but not for a spelling row: that box spans most of the
    screen, so a bounded retry loop gave up often enough to drop glyphs straight
    onto the answer. Bands are exact, uniform, and cost one extra draw.

    Pure apart from *rng*; with avoid=None it is exactly the uniform draw the
    smash mode has always used.
    """
    x = rng.uniform(half, width - half)
    y = rng.uniform(half, height - half)
    if avoid is None:
        return (x, y)
    ax, ay, aw, ah = avoid
    if not (ax <= x <= ax + aw and ay <= y <= ay + ah):
        return (x, y)
    bands = _spawn_bands(half, half, width - half, height - half, avoid)
    if not bands:
        return (x, y)      # the box swallows the screen; nowhere else to put it
    pick = rng.uniform(0.0, sum(area for area, _rect in bands))
    for area, (bx0, by0, bx1, by1) in bands:
        pick -= area
        if pick <= 0.0:
            return (rng.uniform(bx0, bx1), rng.uniform(by0, by1))
    _area, (bx0, by0, bx1, by1) = bands[-1]
    return (rng.uniform(bx0, bx1), rng.uniform(by0, by1))


def _dilation_offsets(ring: int):
    """Offsets whose union thickens a glyph into an even outline, cached per ring.

    Sampling only the eight points of a square (the first cut) left stair-steps
    wherever a stroke curved: at a tight bend the translated copies stop
    overlapping and the union notches. A filled disc samples every pixel in the
    radius instead: a 2px lattice still left ticks on near-vertical edges, where
    a one-pixel gap in the sampling is a one-pixel step in the outline. Cost
    lands once per target, not per frame — _TARGET_CACHE holds the result.
    """
    offsets = _DILATION_CACHE.get(ring)
    if offsets is None:
        offsets = _DILATION_CACHE[ring] = [
            (dx, dy)
            for dy in range(-ring, ring + 1)
            for dx in range(-ring, ring + 1)
            if (dx or dy) and dx * dx + dy * dy <= ring * ring
        ]
    return offsets


def _target_surface(text: str, color, found: bool, font: "pygame.font.Font"):
    """Build (or reuse) the target glyph: a flooded fill, or a hollow outline."""
    key = (text, color, found)
    surf = _TARGET_CACHE.get(key)
    if surf is not None:
        return surf
    glyph = font.render(text, True, color)
    if found:
        surf = glyph
    else:
        ring = CHALLENGE_OUTLINE_PX
        gw, gh = glyph.get_size()
        surf = pygame.Surface((gw + 2 * ring, gh + 2 * ring), pygame.SRCALPHA)
        for dx, dy in _dilation_offsets(ring):
            surf.blit(glyph, (ring + dx, ring + dy))
        # Hollow the dilated glyph by painting its interior in BACKGROUND, which
        # is exact because this overlay is drawn straight onto the background
        # fill with nothing beneath it. Subtracting the glyph instead would take
        # its RGB with it and leave a black ring: font.render keeps the text
        # colour in its fully transparent pixels, so BLEND_RGBA_SUB zeroes the
        # ring's colour while leaving its alpha at 255.
        surf.blit(font.render(text, True, BACKGROUND), (ring, ring))
    if len(_TARGET_CACHE) >= _TARGET_CACHE_MAX:
        _TARGET_CACHE.clear()
    _TARGET_CACHE[key] = surf
    return surf


def challenge_ghost_alpha(step: int, now: float) -> int:
    """Blanket alpha for the un-found ghost; it breathes from hint step 1 on."""
    if step < 1:
        return CHALLENGE_GHOST_ALPHA
    swing = (math.sin(2.0 * math.pi * now / CHALLENGE_PULSE_PERIOD_S) + 1.0) / 2.0
    return int(round(CHALLENGE_GHOST_ALPHA
                     + (CHALLENGE_PULSE_ALPHA - CHALLENGE_GHOST_ALPHA) * swing))


def draw_challenge_target(screen: "pygame.Surface", view, font: "pygame.font.Font",
                          images: "dict | None", now: float) -> None:
    """Draw the centred challenge target for *view* (a challenge.View).

    Dim hollow outline while the child is hunting, flooded with full colour once
    found. ALWAYS uppercase: physical keycaps are uppercase, and a lowercase
    ghost 'b' matches nothing on the keyboard and reads as a 'd'. The
    letter_case setting still governs the echoed smash glyphs.

    Called before the item loop so the overlay sits under the flying items and
    over the background — the smash payoff is never blocked. Everything drawn
    here comes from *view* and *now*; no state survives the call.
    """
    if view is None:
        return
    found = view.progress >= len(view.answer)
    color = challenge_target_color(view.target)
    surf = _target_surface(view.target.upper(), color, found, font)
    surf.set_alpha(255 if found else challenge_ghost_alpha(view.step, now))
    w, h = screen.get_size()
    screen.blit(surf, surf.get_rect(center=(w // 2, h // 2)))

    # Step-2 sticker, when this target has art at all. Only 7 of 26 letters do,
    # so the no-art path is the common one and simply shows nothing extra.
    if found or view.step < 2 or not view.art or not images:
        return
    art = images.get(view.art)
    if art is None:
        return
    rect = art.get_rect()
    rect.center = (w // 2 + surf.get_width() // 2 + CHALLENGE_ART_GAP_PX
                   + rect.width // 2, h // 2)
    if rect.right > w - CHALLENGE_ART_MARGIN_PX:
        rect.right = w - CHALLENGE_ART_MARGIN_PX
    screen.blit(art, rect)


# ---------------------------------------------------------------------------
# Challenge slot row (spelling; the two-digit sums of the math tier reuse it)
#
# Same discipline as the target overlay above: the geometry the spawner avoids
# and the geometry drawn here come from one function, and every surface is
# content-addressed so nothing cached can disagree with view().
# ---------------------------------------------------------------------------

# Breathing room the keep-out box leaves around the whole slot overlay.
# Deliberately thinner than a scaled item's half-width: giving the row the same
# clearance the single centred glyph gets would cover every spawnable pixel of a
# 1280x720 screen for a seven-letter word. Glyph centres stay off the row; their
# edges may still clip it.
CHALLENGE_SLOT_MARGIN_PX = 30

# Gap between the word's picture and the row of slots below it.
CHALLENGE_SLOT_ART_GAP_PX = 28

# Alpha of a slot the child has not reached yet, and of its underline bar. Low
# enough that the current slot is the only bright thing in the row.
CHALLENGE_SLOT_GHOST_ALPHA = 70
CHALLENGE_SLOT_BAR_ALPHA = 90

# Underline bar height in pixels, and its gap below the glyph cell.
CHALLENGE_SLOT_BAR_PX = 8
CHALLENGE_SLOT_BAR_GAP_PX = 6

# Alpha of a letter already in place. Held below full so the current slot is
# brighter than a completed one at EVERY point of its pulse, not just at the
# peak: the glow is the instruction, and a trough that matches the finished
# letters leaves nothing telling the child where to look. The word floods to 255
# the moment it is complete, which is the win.
CHALLENGE_SLOT_FILLED_ALPHA = 205

# Alpha range of the white overlay that makes the current slot glow, and the
# flash a slot lands with. White over the colour rather than a re-render: the
# perf contract at the top of this file forbids a font.render per frame.
CHALLENGE_SLOT_GLOW_MIN_ALPHA = 60
CHALLENGE_SLOT_GLOW_ALPHA = 180
CHALLENGE_SLOT_LAND_ALPHA = 255

_SLOT_CACHE: dict = {}
_SLOT_CACHE_MAX = 48
_ART_CACHE: dict = {}
_ART_CACHE_MAX = 8


def challenge_slot_layout(width: int, height: int, slots: int):
    """(art rect, [cell rects]) for a *slots*-wide answer row, centred on screen.

    The picture sits above the row and the pair is centred as one block, so a
    two-letter word and BUBBLES both land in the middle of the screen.
    """
    art = int(round(config.ITEM_SIZE_PX * config.CHALLENGE_WORD_ART_SCALE))
    cell = config.CHALLENGE_SLOT_PX
    gap = config.CHALLENGE_SLOT_GAP_PX
    row_w = slots * cell + max(0, slots - 1) * gap
    total_h = art + CHALLENGE_SLOT_ART_GAP_PX + cell
    top = height / 2.0 - total_h / 2.0
    art_rect = pygame.Rect(0, 0, art, art)
    art_rect.center = (int(width // 2), int(round(top + art / 2.0)))
    row_top = int(round(top + art + CHALLENGE_SLOT_ART_GAP_PX))
    left = int(round(width / 2.0 - row_w / 2.0))
    cells = [pygame.Rect(left + i * (cell + gap), row_top, cell, cell)
             for i in range(slots)]
    return art_rect, cells


def _slot_glyph(text: str, color, font: "pygame.font.Font"):
    """One slot's glyph, cached by (text, colour) — never re-rendered per frame."""
    key = (text, color)
    surf = _SLOT_CACHE.get(key)
    if surf is None:
        if len(_SLOT_CACHE) >= _SLOT_CACHE_MAX:
            _SLOT_CACHE.clear()
        surf = _SLOT_CACHE[key] = font.render(text, True, color)
    return surf


def _word_art_surface(name: str, color, size: int, images: "dict | None"):
    """The word's picture at *size*: its sticker if one exists, else its shape.

    BOOK and DRUM have PNG stickers; STAR and RING are shapes with no art file,
    so they are drawn rather than loaded. A word that is neither returns None and
    the round simply shows its slot row.
    """
    key = (name, color, size)
    surf = _ART_CACHE.get(key)
    if surf is not None:
        return surf
    built = None
    art = images.get(name) if images else None
    if art is not None:
        built = pygame.transform.smoothscale(art, (size, size))
    elif name in config.SHAPES:
        built = pygame.Surface((size, size), pygame.SRCALPHA)
        _draw_shape(built, name, color)
    if built is None:
        return None
    if len(_ART_CACHE) >= _ART_CACHE_MAX:
        _ART_CACHE.clear()
    _ART_CACHE[key] = built
    return built


def challenge_slot_glow(now: float) -> float:
    """0.0-1.0 breathing envelope for the current slot's white overlay."""
    return (math.sin(2.0 * math.pi * now / CHALLENGE_PULSE_PERIOD_S) + 1.0) / 2.0


def _draw_slot_bar(screen, cell, color, alpha: int) -> None:
    """The underline under one slot — the row's 'here is a letter' skeleton."""
    bar = pygame.Surface((cell.width, CHALLENGE_SLOT_BAR_PX), pygame.SRCALPHA)
    bar.fill(color)
    bar.set_alpha(alpha)
    screen.blit(bar, (cell.left, cell.bottom + CHALLENGE_SLOT_BAR_GAP_PX))


def draw_challenge_slots(screen: "pygame.Surface", view, font: "pygame.font.Font",
                         images: "dict | None", now: float,
                         guided: bool = True) -> None:
    """Draw a spelling round: the word's picture over a row of answer slots.

    Completed letters sit in full colour, the current slot breathes white, and
    everything else stays dim — the glow is the instruction, so exactly one thing
    in the row may be bright. *guided* shows the letters still to come as ghosts;
    advanced shows only their bars, so the picture and the announcer carry it.

    A just-filled slot flashes and settles for CHALLENGE_SLOT_LAND_S before the
    next one lights. That pause is the whole reason View carries filled_at: in
    BOOK the glow would otherwise slide from one O to an identical O, which reads
    as nothing having happened.

    Rebuilt from *view* and *now* every frame; no state survives the call.
    """
    if view is None:
        return
    color = challenge_target_color(view.target)
    art_rect, cells = challenge_slot_layout(
        screen.get_width(), screen.get_height(), len(view.answer))

    art = _word_art_surface(view.art, color, art_rect.width, images) if view.art else None
    if art is not None:
        art.set_alpha(255)
        screen.blit(art, art_rect)

    won = view.progress >= len(view.answer)
    landing = (view.progress > 0 and view.filled_at is not None
               and now - view.filled_at < config.CHALLENGE_SLOT_LAND_S)
    land_left = (1.0 - (now - view.filled_at) / config.CHALLENGE_SLOT_LAND_S
                 if landing else 0.0)

    for i, cell in enumerate(cells):
        text = view.answer[i].upper()
        filled = i < view.progress
        # While a slot lands, the next one stays dark: two bright slots at once
        # would leave the child guessing which one the glow means.
        current = i == view.progress and not landing
        # Advanced shows only what has been won. Lighting the letter the row is
        # waiting on would hand over the answer one slot at a time, which is the
        # guided tier wearing a different coat.
        show_glyph = filled or guided

        if show_glyph:
            glyph = _slot_glyph(text, color, font)
            if current or won:
                alpha = 255
            elif filled:
                alpha = CHALLENGE_SLOT_FILLED_ALPHA
            else:
                alpha = CHALLENGE_SLOT_GHOST_ALPHA
            glyph.set_alpha(alpha)
            screen.blit(glyph, glyph.get_rect(center=cell.center))

        white = 0
        if landing and i == view.progress - 1:
            white = int(round(CHALLENGE_SLOT_LAND_ALPHA * land_left))
        elif current:
            white = int(round(CHALLENGE_SLOT_GLOW_MIN_ALPHA
                              + (CHALLENGE_SLOT_GLOW_ALPHA
                                 - CHALLENGE_SLOT_GLOW_MIN_ALPHA)
                              * challenge_slot_glow(now)))

        _draw_slot_bar(screen, cell, color,
                       255 if current else CHALLENGE_SLOT_BAR_ALPHA)
        if white > 0:
            # The bar carries the glow too, so an advanced slot with no letter in
            # it is still unmistakably the one being asked for.
            if current:
                _draw_slot_bar(screen, cell, (255, 255, 255), white)
            if show_glyph:
                hot = _slot_glyph(text, (255, 255, 255), font)
                hot.set_alpha(white)
                screen.blit(hot, hot.get_rect(center=cell.center))
