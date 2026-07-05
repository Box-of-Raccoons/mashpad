# mashpad/trail.py — mouse-trail state.
# Pure — no pygame imports. Rainbow drawing is render.py's job.

from __future__ import annotations

import math
from collections import deque
from typing import Generator, Tuple

from mashpad import config


class Trail:
    """Records recent mouse positions and exposes them with age fractions.

    Points older than TRAIL_FADE_S are considered expired.  The deque is
    capped at TRAIL_MAX_POINTS; oldest entry evicted when full.
    """

    # Rainbow hue cycles once every HUE_CYCLE_S seconds.
    HUE_CYCLE_S: float = 3.0

    def __init__(self) -> None:
        # Each entry is (pos, timestamp) where pos=(x,y) float pair.
        self._pts: deque[Tuple[Tuple[float, float], float]] = deque(
            maxlen=config.TRAIL_MAX_POINTS
        )

    def add(self, pos: Tuple[float, float], now: float) -> None:
        """Append a new point (evicts oldest if at capacity)."""
        self._pts.append((pos, now))

    def prune(self, now: float) -> None:
        """Remove points older than TRAIL_FADE_S."""
        cutoff = now - config.TRAIL_FADE_S
        while self._pts and self._pts[0][1] < cutoff:
            self._pts.popleft()

    def points(
        self, now: float
    ) -> Generator[Tuple[Tuple[float, float], float], None, None]:
        """Yield (pos, age_fraction) for points still alive.

        age_fraction is in [0.0, 1.0) where 0.0 = just added, 1.0 = expired.
        Points at or past TRAIL_FADE_S are skipped.
        """
        cutoff = now - config.TRAIL_FADE_S
        for pos, t in self._pts:
            if t < cutoff:
                continue
            age = now - t
            age_fraction = age / config.TRAIL_FADE_S  # 0..1
            if age_fraction >= 1.0:
                continue  # fully expired
            yield pos, age_fraction

    def hue_for(self, now: float) -> float:
        """Return a hue value in [0.0, 1.0) cycling once every HUE_CYCLE_S.

        Render layer maps this to a colour (e.g. colorsys.hsv_to_rgb).
        """
        return math.fmod(now / self.HUE_CYCLE_S, 1.0)
