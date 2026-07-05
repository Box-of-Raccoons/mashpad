# mashpad/main.py — pygame init, event loop, input handling, dev-mode flag.
#
# Wires the pure-logic core (keymap / items / ratelimit / trail) to the pygame
# runtime (render / audio). No pygame calls happen at import time — everything
# lives inside main().

from __future__ import annotations

import argparse
import random

import pygame

from mashpad import config, imagepack, keymap, render
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


def _spawn(field: ItemField, spec, pos, now: float, font, audio: Audio, images=None) -> None:
    """Register an item, build+cache its render surface once, and fire its audio."""
    item = field.spawn(spec, pos, now)
    item.surface = render.build_item_surface(spec, font, images)
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

    # Load the image pack.  Scan first (pure, no pygame), then load + scale each
    # PNG once at startup.  A corrupt or unloadable file prints one warning and is
    # skipped — the app must not crash on a bad image.
    _image_entries = imagepack.scan(
        repo_root() / "assets" / config.IMAGES_DIR_NAME
    )
    images: dict[str, pygame.Surface] = {}
    for _entry in _image_entries:
        try:
            _raw = pygame.image.load(str(_entry.path)).convert_alpha()
            # Scale to fit within ITEM_SIZE_PX × ITEM_SIZE_PX preserving aspect ratio.
            _w, _h = _raw.get_size()
            _scale = min(config.ITEM_SIZE_PX / _w, config.ITEM_SIZE_PX / _h)
            _nw = max(1, int(round(_w * _scale)))
            _nh = max(1, int(round(_h * _scale)))
            images[_entry.name] = pygame.transform.smoothscale(_raw, (_nw, _nh))
        except Exception as exc:  # noqa: BLE001 — skip bad image, never crash
            print(f"[mashpad images] could not load {_entry.path.name}: {exc}")

    # Extras: pool members for non-alphanumeric key spawns.  Single-char names
    # (e.g. "a.png", "7.png") are reskins only — exclude them from the pool.
    _extras = [
        e for e in _image_entries
        if not (len(e.name) == 1 and e.name.isalnum())
    ]

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
                spec = keymap.item_for_key(_char_for_event(event), rng, _extras)
                if bucket.try_take(now):
                    pos = (rng.uniform(half, width - half),
                           rng.uniform(half, height - half))
                    _spawn(field, spec, pos, now, font, audio, images)

            elif event.type == pygame.MOUSEMOTION:
                trail.add(event.pos, now)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Click → shape at the cursor, through the SAME rate-limit bucket.
                spec = keymap.item_for_key(None, rng, _extras)
                if bucket.try_take(now):
                    _spawn(field, spec, event.pos, now, font, audio, images)

        field.update(now)
        trail.prune(now)

        screen.fill(render.BACKGROUND)
        for item in field.items:          # oldest → newest
            render.draw_item(screen, item, now)
        render.draw_trail(screen, trail, now)
        pygame.display.flip()

        clock.tick(config.FPS)

    pygame.quit()
