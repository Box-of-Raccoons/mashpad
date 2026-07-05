# mashpad/splash.py — startup splash image with a gentle scale pulse (pygame).
#
# Loads assets/splash.png once, scaled to ~55% of the screen height (aspect
# preserved), and draws it centred with a slow ±3% breathing pulse. If the PNG
# is missing or unloadable the splash is simply never visible and the app runs
# normally — no crash. main.py dismisses it on the first key press / click.

from __future__ import annotations

import math

import pygame

from mashpad import paths

# Fraction of the screen height the splash image spans.
SPLASH_HEIGHT_FRAC = 0.55
# Scale-pulse amplitude (±) and period in seconds.
PULSE_AMPLITUDE = 0.03
PULSE_PERIOD_S = 1.2


class Splash:
    """Centred, gently pulsing startup image; dismissed on first input."""

    def __init__(self, screen) -> None:
        self._visible = False
        self._base = None
        path = paths.app_root() / "assets" / "splash.png"
        try:
            raw = pygame.image.load(str(path)).convert_alpha()
            _, ih = raw.get_size()
            target_h = screen.get_height() * SPLASH_HEIGHT_FRAC
            scale = target_h / ih if ih else 1.0
            iw2, ih2 = raw.get_size()
            nw = max(1, int(round(iw2 * scale)))
            nh = max(1, int(round(ih2 * scale)))
            self._base = pygame.transform.smoothscale(raw, (nw, nh))
            self._visible = True
        except Exception as exc:  # noqa: BLE001 — missing/corrupt → never visible
            print(f"[mashpad splash] could not load {path.name}: {exc}")

    @property
    def visible(self) -> bool:
        return self._visible and self._base is not None

    def dismiss(self) -> None:
        """Hide the splash for good (idempotent)."""
        self._visible = False

    def draw(self, screen, now: float) -> None:
        """Draw the pulsing splash centred on *screen* when visible."""
        if not self.visible:
            return
        pulse = 1.0 + PULSE_AMPLITUDE * math.sin(2.0 * math.pi * now / PULSE_PERIOD_S)
        bw, bh = self._base.get_size()
        img = pygame.transform.smoothscale(
            self._base, (max(1, int(round(bw * pulse))), max(1, int(round(bh * pulse))))
        )
        w, h = screen.get_size()
        screen.blit(img, img.get_rect(center=(w // 2, h // 2)))
