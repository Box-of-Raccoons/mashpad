# mashpad/items.py — item lifecycle, pure functions of age.
# No pygame imports anywhere in this file.

from __future__ import annotations

import math
from typing import Iterable, Optional, Tuple

from mashpad import config
from mashpad.keymap import ItemSpec

# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------
SPAWNING = "SPAWNING"
ALIVE    = "ALIVE"
FADING   = "FADING"
DEAD     = "DEAD"


class Item:
    """A single spawned item (letter, digit, or shape).

    All timing uses absolute seconds passed in from outside — no time.time().
    """

    def __init__(
        self,
        spec: ItemSpec,
        pos: Tuple[float, float],
        spawn_time: float,
    ) -> None:
        self.spec       = spec
        self.pos        = pos
        self.spawn_time = spawn_time
        # Optional cache slot for the render layer — set by render.py, ignored here.
        self.surface    = None
        # Absolute time at which fading was forced; None = natural lifetime.
        self._fade_start: Optional[float] = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _age(self, now: float) -> float:
        return now - self.spawn_time

    def _fade_begins_at(self) -> float:
        """Absolute time at which FADING starts."""
        if self._fade_start is not None:
            return self._fade_start
        return self.spawn_time + config.BOUNCE_S + config.LINGER_S

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def state(self, now: float) -> str:
        """Return current state string.

        All boundaries compare absolute times (spawn_time + offset), not ages —
        float subtraction (now - spawn_time) can land just below the offset at
        the exact boundary instant.
        """
        fade_begins = self._fade_begins_at()
        fade_ends   = fade_begins + config.FADE_S

        if now >= fade_ends:
            return DEAD
        if now >= fade_begins:
            return FADING
        if now >= self.spawn_time + config.BOUNCE_S:
            return ALIVE
        return SPAWNING

    def scale(self, now: float) -> float:
        """Scale multiplier for rendering (1.0 = nominal size).

        Bounce curve (two half-sine segments, smooth at join):
          First half  p in [0, 0.5]: 0 → OVERSHOOT via  OVERSHOOT * sin(pi*p)
          Second half p in [0.5, 1]: OVERSHOOT → 1.0 via
                       OVERSHOOT - (OVERSHOOT-1) * sin(pi/2 * 2*(p-0.5))

        Guarantees: scale(0)=0, peak=OVERSHOOT at p=0.5, scale(BOUNCE_S)=1.0.
        After BOUNCE_S: clamped to exactly 1.0 (no float drift).
        """
        if now >= self.spawn_time + config.BOUNCE_S:
            return 1.0  # exact clamp (absolute-time compare, see state())

        p        = self._age(now) / config.BOUNCE_S  # normalised 0..1
        overshoot = config.BOUNCE_OVERSHOOT
        if p <= 0.5:
            return overshoot * math.sin(math.pi * p)
        else:
            q = (p - 0.5) * 2.0  # 0..1 over second half
            return overshoot - (overshoot - 1.0) * math.sin(math.pi / 2.0 * q)

    def alpha(self, now: float) -> int:
        """Opacity in [0, 255].

        255 until FADING begins; then linearly 255 → 0 over FADE_S; 0 once DEAD.
        """
        fade_begins = self._fade_begins_at()
        if now < fade_begins:
            return 255
        elapsed = now - fade_begins
        if elapsed >= config.FADE_S:
            return 0
        fraction = elapsed / config.FADE_S  # 0..1
        return max(0, round(255 * (1.0 - fraction)))

    def force_fade(self, now: float) -> None:
        """Force fading to start at *now* (idempotent; ignored if already fading)."""
        if self._fade_start is not None:
            return  # already forced
        natural_fade = self.spawn_time + config.BOUNCE_S + config.LINGER_S
        if now < natural_fade:
            self._fade_start = now
        # If natural fade already started or passed, do nothing


class ItemField:
    """Container for all live items.  Enforces MAX_ITEMS cap."""

    def __init__(self) -> None:
        self._items: list[Item] = []

    @property
    def items(self) -> list[Item]:
        """Items ordered oldest → newest (copy)."""
        return list(self._items)

    def spawn(
        self,
        spec: ItemSpec,
        pos: Tuple[float, float],
        now: float,
    ) -> Item:
        """Create and register a new item.

        If live count >= MAX_ITEMS, force-fades the oldest non-fading item first.
        """
        live = [i for i in self._items if i.state(now) != DEAD]
        if len(live) >= config.MAX_ITEMS:
            for candidate in live:  # oldest first
                if candidate.state(now) not in (FADING, DEAD):
                    candidate.force_fade(now)
                    break

        item = Item(spec=spec, pos=pos, spawn_time=now)
        self._items.append(item)
        return item

    def update(self, now: float) -> None:
        """Drop DEAD items from the list."""
        self._items = [i for i in self._items if i.state(now) != DEAD]

    def __iter__(self) -> Iterable[Item]:
        return iter(self._items)
