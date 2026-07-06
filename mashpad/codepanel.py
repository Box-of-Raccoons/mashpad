# mashpad/codepanel.py — scrolling syntax-highlighted code panel for BabyIDE mode.
#
# The pygame render half: measures glyphs and blits. All placement/scroll math
# and the bounce curve live in the pure codelayout.py (unit-tested there),
# mirroring the items.py (pure) / render.py (pygame) split. pygame is imported
# at module top like render.py/menu.py — so, like them, this module must never
# be imported by a pure module's purity test.

from __future__ import annotations

import pygame

from mashpad.codelayout import LayoutBuffer, bounce_scale


class CodePanel:
    """Scrolling syntax-highlighted code panel for BabyIDE mode.

    Persistent: tokens never fade.  Only the newest token animates with the
    overshoot bounce from items.Item.scale; older tokens are blitted directly.
    """

    def __init__(
        self,
        rect,
        font_path,
        font_px: int,
        token_colors: dict,
        bounce_s: float,
        overshoot: float,
    ) -> None:
        # rect: (x, y, w, h) region for the panel, or a pygame.Rect.
        self.rect = pygame.Rect(rect)
        self._font = pygame.font.Font(str(font_path), font_px)
        self._token_colors = token_colors
        self._bounce_s = bounce_s
        self._overshoot = overshoot

        self._space_width: int = self._font.size(" ")[0]
        line_height: int = self._font.get_linesize()

        self._buffer = LayoutBuffer(
            self.rect.width,
            self.rect.height,
            line_height,
            self._space_width,
        )

        # Track the source row of the previous token to detect line breaks.
        self._prev_row: int | None = None
        # Absolute time at which the newest token was placed.
        self._newest_spawn: float | None = None

    def append(self, token, now: float) -> None:
        """Append a token to the panel.

        token must expose .text (str), .category (str), .row (int), .col (int).
        """
        starts_new_line = (
            self._prev_row is not None and token.row != self._prev_row
        )
        indent_px = token.col * self._space_width
        token_width = self._font.size(token.text)[0]
        self._buffer.append(
            token.category,
            token.text,
            token_width,
            starts_new_line,
            indent_px,
        )
        self._newest_spawn = now
        self._prev_row = token.row

    def draw(self, screen: pygame.Surface, now: float) -> None:
        """Blit all tokens onto screen; newest gets the bounce-overshoot animation.

        Perf contract (mirrors render.draw_item):
          smoothscale runs ONLY while scale != 1.0.  At scale 1.0 the surface
          is blitted directly.  font.render is called once per visible token
          per frame (acceptable at BabyIDE token counts on the Pi).
        """
        placed = self._buffer.placed
        if not placed:
            return

        # Draw all but the newest first (oldest → second-newest).
        for p in placed[:-1]:
            color = self._token_colors.get(
                p.category, self._token_colors.get("name", (255, 255, 255))
            )
            surf = self._font.render(p.text, True, color)
            screen.blit(surf, (self.rect.x + p.x, self.rect.y + p.y))

        # Draw newest last so its bounce overlaps neighbours cleanly.
        newest = placed[-1]
        color = self._token_colors.get(
            newest.category, self._token_colors.get("name", (255, 255, 255))
        )
        surf = self._font.render(newest.text, True, color)

        if self._newest_spawn is not None:
            age = now - self._newest_spawn
            scale = bounce_scale(age, self._bounce_s, self._overshoot)
        else:
            scale = 1.0

        if scale != 1.0:
            w = max(1, int(round(surf.get_width() * scale)))
            h = max(1, int(round(surf.get_height() * scale)))
            draw_surf = pygame.transform.smoothscale(surf, (w, h))
        else:
            draw_surf = surf

        # Blit centered on the token's natural centre so the bounce radiates
        # from the middle of the glyph (same approach as render.draw_item).
        cx = self.rect.x + newest.x + surf.get_width() // 2
        cy = self.rect.y + newest.y + surf.get_height() // 2
        blit_rect = draw_surf.get_rect(center=(cx, cy))
        screen.blit(draw_surf, blit_rect)
