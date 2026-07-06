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
# Discrete phase steps per pulse period. The pulse is quantised to these so the
# size cache holds at most PULSE_STEPS surfaces (~2 px between adjacent sizes —
# visually indistinguishable from the continuous curve at ±3%). Unquantised, a
# ~594 px base spans ~37 integer sizes ≈ 50 MB of cached RGBA on a 1080p screen;
# quantised it is ≤16 (fewer after the sine's symmetry dedups), freed on dismiss.
PULSE_STEPS = 16


class Splash:
    """Centred, gently pulsing startup image; dismissed on first input."""

    def __init__(self, screen) -> None:
        self._visible = False
        self._base = None
        # Lazy size-keyed cache: (w, h) → pre-scaled Surface, populated on first
        # use of each distinct quantised pulse size (see draw()). Bounded by
        # PULSE_STEPS entries; warm-up is ≤PULSE_STEPS smoothscales during the
        # first period, steady-state is a dict lookup — zero scaling per frame.
        # dismiss() frees the cache and the base (the splash never returns).
        self._frame_cache: dict = {}
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
        """Hide the splash for good (idempotent) and release its surfaces.

        The splash can never come back, so the pre-scaled frames and the base
        image (up to ~25 MB on a 1080p screen) go back to the allocator now
        rather than living for the whole session — this matters on a 1 GB Pi.
        """
        self._visible = False
        self._frame_cache.clear()
        self._base = None

    def draw(self, screen, now: float) -> None:
        """Draw the pulsing splash centred on *screen* when visible."""
        if not self.visible:
            return
        # Quantise the phase to PULSE_STEPS so the cache stays small (see above).
        step = int(now / PULSE_PERIOD_S * PULSE_STEPS) % PULSE_STEPS
        pulse = 1.0 + PULSE_AMPLITUDE * math.sin(2.0 * math.pi * step / PULSE_STEPS)
        bw, bh = self._base.get_size()
        key = (max(1, int(round(bw * pulse))), max(1, int(round(bh * pulse))))
        img = self._frame_cache.get(key)
        if img is None:
            # First visit to this pixel size — smoothscale once and cache forever.
            # After one full pulse period every blit is a dict lookup only.
            img = pygame.transform.smoothscale(self._base, key)
            self._frame_cache[key] = img
        w, h = screen.get_size()
        screen.blit(img, img.get_rect(center=(w // 2, h // 2)))
