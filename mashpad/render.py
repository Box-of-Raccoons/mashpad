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
# transform.smoothscale, draw.circle/rect/polygon, Surface.set_alpha.

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

def build_item_surface(spec, font: "pygame.font.Font") -> "pygame.Surface":
    """Render an item to a fresh per-pixel-alpha surface. Called ONCE at spawn.

    The surface is always ITEM_SIZE_PX square; glyphs/shapes are centred within
    it so draw_item can scale/centre uniformly. `font` is pre-sized by the caller
    (main.py) from config.ITEM_SIZE_PX and reused for every glyph.
    """
    size = config.ITEM_SIZE_PX
    surf = pygame.Surface((size, size), pygame.SRCALPHA)

    if spec.kind in ("letter", "digit"):
        text = spec.name.upper() if spec.kind == "letter" else spec.name
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
