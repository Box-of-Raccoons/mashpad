# mashpad/main.py — pygame init, event loop, input handling, dev-mode flag.
#
# Wires the pure-logic core (keymap / items / ratelimit / trail) to the pygame
# runtime (render / audio). No pygame calls happen at import time — everything
# lives inside main().

from __future__ import annotations

import argparse
import random

import pygame

from mashpad import config, keymap, render
from mashpad.audio import Audio, repo_root
from mashpad.items import ItemField
from mashpad.ratelimit import TokenBucket
from mashpad.trail import Trail

# One unseeded RNG for the whole app (colours, shapes, effect choice, positions).
rng = random.Random()


def _parse_size(text: str) -> tuple[int, int]:
    """Parse a 'WxH' string (e.g. '1280x720') into an (int, int) size."""
    w, h = text.lower().split("x")
    return int(w), int(h)


def _char_for_event(event) -> str | None:
    """Return the a-zA-Z0-9 char for a KEYDOWN, else None (→ random shape).

    keymap lowercases letters itself; we just gate to single ASCII alnum chars.
    Space, enter, F-keys, modifiers-alone, etc. yield a non-alnum / empty
    unicode and map to None.
    """
    u = event.unicode
    if len(u) == 1:
        lo = u.lower()
        if ("a" <= lo <= "z") or ("0" <= u <= "9"):
            return u
    return None


def _spawn(field: ItemField, spec, pos, now: float, font, audio: Audio) -> None:
    """Register an item, build+cache its render surface once, and fire its audio."""
    item = field.spawn(spec, pos, now)
    item.surface = render.build_item_surface(spec, font)
    audio.play_for(spec, rng)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="mashpad")
    parser.add_argument(
        "--windowed",
        nargs="?",
        const="1280x720",
        default=None,
        metavar="WxH",
        help="run in a window (default 1280x720); omit for fullscreen",
    )
    parser.add_argument("--mute", action="store_true", help="disable audio")
    args = parser.parse_args(argv)

    pygame.init()

    if args.windowed is not None:
        screen = pygame.display.set_mode(_parse_size(args.windowed))
        pygame.mouse.set_visible(True)
    else:
        # Fullscreen on the Pi: NEVER pass a real size — (0,0)+FULLSCREEN takes
        # the native KMS/DRM mode.
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
    pygame.display.set_caption("mashpad")

    font_path = repo_root() / "assets" / "DejaVuSans-Bold.ttf"
    # Sized once from ITEM_SIZE_PX; reused for every glyph (never re-created).
    font = pygame.font.Font(str(font_path), int(config.ITEM_SIZE_PX * 0.9))

    audio = Audio(muted=args.mute)
    field = ItemField()
    trail = Trail()
    bucket = TokenBucket(config.BUCKET_CAPACITY, config.BUCKET_REFILL_PER_S)
    clock = pygame.time.Clock()

    width, height = screen.get_size()
    half = config.ITEM_SIZE_PX / 2.0  # keep keyboard spawns fully on-screen

    running = True
    while running:
        now = pygame.time.get_ticks() / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                # Grown-up exit combo: Ctrl+Alt+Q.
                if (event.key == pygame.K_q
                        and event.mod & pygame.KMOD_CTRL
                        and event.mod & pygame.KMOD_ALT):
                    running = False
                    continue
                spec = keymap.item_for_key(_char_for_event(event), rng)
                if bucket.try_take(now):
                    pos = (rng.uniform(half, width - half),
                           rng.uniform(half, height - half))
                    _spawn(field, spec, pos, now, font, audio)

            elif event.type == pygame.MOUSEMOTION:
                trail.add(event.pos, now)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Click → shape at the cursor, through the SAME rate-limit bucket.
                spec = keymap.item_for_key(None, rng)
                if bucket.try_take(now):
                    _spawn(field, spec, event.pos, now, font, audio)

        field.update(now)
        trail.prune(now)

        screen.fill(render.BACKGROUND)
        for item in field.items:          # oldest → newest
            render.draw_item(screen, item, now)
        render.draw_trail(screen, trail, now)
        pygame.display.flip()

        clock.tick(config.FPS)

    pygame.quit()
