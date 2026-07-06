# mashpad/codelayout.py — pure layout math for the BabyIDE code panel.
#
# Pure — no pygame imports (joins the purity test). Holds the bounce curve and
# the wrap/scroll LayoutBuffer; the pygame CodePanel (codepanel.py) measures
# glyphs and blits, delegating all placement math here. Mirrors the items.py
# (pure) / render.py (pygame) split.

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# bounce_scale
# ---------------------------------------------------------------------------

def bounce_scale(age: float, dur: float, overshoot: float) -> float:
    """Scale multiplier for a token 'age' seconds after it landed.

    Mirrors items.Item.scale: 0 at age<=0, peak=overshoot at age=dur/2,
    exactly 1.0 at age>=dur (clamped). Two half-sine segments, smooth at join.

    First half  p in [0, 0.5]: 0 → overshoot via  overshoot * sin(pi*p)
    Second half p in [0.5, 1]: overshoot → 1.0 via
                 overshoot - (overshoot-1) * sin(pi/2 * 2*(p-0.5))
    """
    if age <= 0.0:
        return 0.0
    if age >= dur:
        return 1.0
    p = age / dur  # normalised 0..1
    if p <= 0.5:
        return overshoot * math.sin(math.pi * p)
    else:
        q = (p - 0.5) * 2.0  # 0..1 over second half
        return overshoot - (overshoot - 1.0) * math.sin(math.pi / 2.0 * q)


# ---------------------------------------------------------------------------
# Placed
# ---------------------------------------------------------------------------

@dataclass
class Placed:
    text: str
    category: str
    x: int      # screen x (already scroll-adjusted)
    y: int      # screen y (already scroll-adjusted)


# ---------------------------------------------------------------------------
# LayoutBuffer
# ---------------------------------------------------------------------------

class LayoutBuffer:
    """Lays tokens left-to-right, wrapping and scrolling.

    Token widths are passed in (the pygame layer measures them), so this class
    makes no pygame calls and is fully unit-testable.

    Coordinates
    -----------
    Stored tokens use absolute (unscrolled) y coordinates.  The ``placed``
    and ``newest`` properties subtract ``scroll_offset`` to return screen
    coords relative to the top-left of the panel.
    """

    def __init__(
        self,
        width: int,
        height: int,
        line_height: int,
        space_width: int,
        left_margin: int = 0,
        top_margin: int = 0,
    ) -> None:
        self._width = width
        self._height = height
        self._line_height = line_height
        self._space_width = space_width
        self._left_margin = left_margin
        self._top_margin = top_margin

        # Stored tokens: (category, text, abs_x, abs_y)
        self._tokens: list[tuple[str, str, int, int]] = []

        # Cursor in absolute coords (top-left of where next token goes).
        self._cursor_x: int = left_margin
        self._cursor_y: int = top_margin

        # Pixels scrolled up so the newest line stays fully visible.
        self._scroll_offset: int = 0

        # True once at least one token has ever been placed (survives pruning).
        self._has_placed: bool = False

    def append(
        self,
        category: str,
        text: str,
        token_width: int,
        starts_new_line: bool,
        indent_px: int = 0,
    ) -> None:
        """Place one token, advancing the cursor, wrapping, and scrolling."""
        nothing_placed = not self._has_placed

        if starts_new_line and not nothing_placed:
            # Explicit line break (e.g. new source line).
            self._cursor_y += self._line_height
            self._cursor_x = self._left_margin + indent_px
        elif not starts_new_line:
            # Soft-wrap: wrap if the token would overflow the right edge.
            if self._cursor_x + token_width > self._width:
                self._cursor_y += self._line_height
                self._cursor_x = self._left_margin

        # Record at the current cursor position (absolute coords).
        self._tokens.append((category, text, self._cursor_x, self._cursor_y))
        self._has_placed = True

        # Advance cursor past this token.
        self._cursor_x += token_width + self._space_width

        # Scroll so the current (newest) line is fully visible.
        if self._cursor_y + self._line_height > self._height:
            self._scroll_offset = self._cursor_y + self._line_height - self._height

        # Prune tokens that are entirely above the visible area.
        self._tokens = [
            t for t in self._tokens
            if t[3] - self._scroll_offset >= -self._line_height
        ]

    @property
    def placed(self) -> list[Placed]:
        """All retained tokens in screen coordinates (scroll-adjusted)."""
        return [
            Placed(text=t[1], category=t[0], x=t[2], y=t[3] - self._scroll_offset)
            for t in self._tokens
        ]

    @property
    def newest(self) -> Placed | None:
        """The last-placed token in screen coordinates, or None if empty."""
        if not self._tokens:
            return None
        t = self._tokens[-1]
        return Placed(text=t[1], category=t[0], x=t[2], y=t[3] - self._scroll_offset)

    @property
    def scroll_offset(self) -> int:
        """Pixels scrolled up (0 while content fits within height)."""
        return self._scroll_offset
