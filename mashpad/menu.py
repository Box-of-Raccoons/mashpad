# mashpad/menu.py — the grown-up options overlay (pygame UI).
#
# A keyboard-only overlay state machine. main.py opens it with Ctrl+Alt+O and,
# while it is visible, routes ALL events here (baby spawning is suppressed). It
# dims the screen, draws a centred panel, and edits the shared Settings object
# in place — autosaving on every change and on close. No mouse handling.

from __future__ import annotations

import random

import pygame

import mashpad
from mashpad import combos, config, settings as settings_mod

# Menu font size (px) — a couch-readable slice of the item glyph font.
MENU_FONT_PX = 48

# About-footer font size (px) — small, quiet credit line at the panel bottom.
ABOUT_FONT_PX = 24

# Row indices (order the rows are drawn / navigated).
_ROW_VOICE = 0
_ROW_VOLUME = 1
_ROW_LETTERS = 2
_ROW_RACCOONS = 3
_ROW_PHRASES = 4
_ROW_SOUNDS = 5
_ROW_DISPLAY = 6
_ROW_QUIT = 7
_ROW_COUNT = 8

# Note auditioned when the Sounds row is switched to Piano (mirrors the voice-row
# "hello" audition). A mid-range generated note so grown-ups hear the timbre.
_AUDITION_NOTE = "c5"


class _SampleWord:
    """Minimal spec stand-in: Audio.play_for only reads .spoken_name."""

    def __init__(self, word: str) -> None:
        self.spoken_name = word


class Menu:
    """Grown-up options overlay driven entirely by the keyboard."""

    def __init__(self, settings, audio, font_path, save_path) -> None:
        self._settings = settings
        self._audio = audio
        self._font = pygame.font.Font(str(font_path), MENU_FONT_PX)
        self._small_font = pygame.font.Font(str(font_path), ABOUT_FONT_PX)
        self._rng = random.Random()  # for auditioning sample words
        # settings.json is writable state — caller provides path.
        self._save_path = save_path
        self._visible = False
        self._selected = 0

    # ------------------------------------------------------------------ state

    @property
    def visible(self) -> bool:
        return self._visible

    def open(self) -> None:
        self._visible = True
        self._selected = 0

    def close(self) -> None:
        self._visible = False
        self._save()  # persist on close as well as on every change

    # ------------------------------------------------------------------ events

    def handle_event(self, event) -> "str | None":
        """Handle one event while the menu is open. Returns 'quit' or None."""
        if event.type != pygame.KEYDOWN:
            return None

        key = event.key

        # Grown-up combos while the menu is open (AltGr-safe; shared helper).
        # Ctrl+Alt+Q must still quit — main.py routes ALL events here while the
        # menu is up, so without this the documented quit combo would be dead.
        combo = combos.grown_up_combo(event)
        if combo == combos.QUIT:
            return "quit"
        if combo == combos.OPTIONS:  # same Ctrl+Alt+O that opened it → close
            self.close()
            return None

        # Close: Esc.
        if key == pygame.K_ESCAPE:
            self.close()
            return None

        if key == pygame.K_UP:
            self._selected = (self._selected - 1) % _ROW_COUNT
        elif key == pygame.K_DOWN:
            self._selected = (self._selected + 1) % _ROW_COUNT
        elif key == pygame.K_LEFT:
            self._step(-1)
        elif key == pygame.K_RIGHT:
            self._step(+1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self._selected == _ROW_QUIT:
                return "quit"
        return None

    def _step(self, direction: int) -> None:
        """Apply a left/right change to the currently highlighted row."""
        row = self._selected
        if row == _ROW_VOICE:
            self._step_voice(direction)
        elif row == _ROW_VOLUME:
            self._step_volume(direction)
        elif row == _ROW_LETTERS:
            self._step_letters()
        elif row == _ROW_RACCOONS:
            self._step_raccoons(direction)
        elif row == _ROW_PHRASES:
            self._step_phrases()
        elif row == _ROW_SOUNDS:
            self._step_sounds()
        elif row == _ROW_DISPLAY:
            self._step_display()
        # Quit row: no left/right value.

    # --------------------------------------------------------------- row logic

    def _voice_options(self):
        """Ordered Voice-row values: concrete voices, then VOICE_MODE_RANDOM, VOICE_MODE_CYCLE."""
        return list(self._audio.voices) + [settings_mod.VOICE_MODE_RANDOM, settings_mod.VOICE_MODE_CYCLE]

    def _step_voice(self, direction: int) -> None:
        options = self._voice_options()
        if not options:
            return
        try:
            idx = options.index(self._settings.voice_mode)
        except ValueError:
            idx = 0  # current value isn't an option (e.g. a voice that vanished)
        idx = (idx + direction) % len(options)
        value = options[idx]
        self._settings.voice_mode = value
        self._save()
        # Audition a specific voice so grown-ups hear the pack; none for VOICE_MODE_RANDOM/VOICE_MODE_CYCLE.
        if value not in (settings_mod.VOICE_MODE_RANDOM, settings_mod.VOICE_MODE_CYCLE):
            self._audio.play_for(_SampleWord("hello"), self._rng, voice=value)

    def _step_volume(self, direction: int) -> None:
        vol = max(0, min(100, self._settings.volume + direction * 10))
        if vol != self._settings.volume:
            self._settings.volume = vol
            self._audio.set_master_volume(vol / 100.0)  # live feedback
            self._save()

    def _step_letters(self) -> None:
        # Two-value toggle: left and right both flip it.
        self._settings.letter_case = (
            "lower" if self._settings.letter_case == "upper" else "upper"
        )
        self._save()

    def _step_raccoons(self, direction: int) -> None:
        try:
            idx = settings_mod.RACCOON_AMOUNTS.index(self._settings.raccoon_amount)
        except ValueError:
            idx = 1  # "normal"
        idx = max(0, min(len(settings_mod.RACCOON_AMOUNTS) - 1, idx + direction))  # clamp, no wrap
        self._settings.raccoon_amount = settings_mod.RACCOON_AMOUNTS[idx]
        self._save()

    def _step_phrases(self) -> None:
        # Two-value toggle: left and right both flip it.
        self._settings.phrases = not self._settings.phrases
        self._save()

    def _step_sounds(self) -> None:
        # Two-value toggle: left and right both flip piano <-> dings.
        self._settings.sound_mode = (
            "dings" if self._settings.sound_mode == "piano" else "piano"
        )
        self._save()
        # Audition one note when switching to Piano so grown-ups hear the timbre
        # (the Dings side is auditioned by its own random effect on real spawns).
        if self._settings.sound_mode == "piano":
            self._audio.play_note(_AUDITION_NOTE)

    def _step_display(self) -> None:
        # Two-value toggle: left and right both flip smash <-> babyide.
        self._settings.display_mode = (
            "babyide" if self._settings.display_mode == "smash" else "smash"
        )
        self._save()

    def _save(self) -> None:
        settings_mod.save(self._settings, self._save_path)

    # ---------------------------------------------------------------- drawing

    def _voice_label(self) -> str:
        v = self._settings.voice_mode
        if v == settings_mod.VOICE_MODE_RANDOM:
            return "Random"
        if v == settings_mod.VOICE_MODE_CYCLE:
            return "Cycle"
        # Friendly label for a known pack; unknown packs fall back to name.title().
        return config.voice_label(v)

    def _rows(self):
        """(label, value) pairs, in draw order."""
        return [
            ("Voice", self._voice_label()),
            ("Volume", str(self._settings.volume)),
            ("Letters", "ABC" if self._settings.letter_case == "upper" else "abc"),
            ("Raccoons", self._settings.raccoon_amount.title()),
            ("Phrases", "On" if self._settings.phrases else "Off"),
            ("Sounds", "Piano" if self._settings.sound_mode == "piano" else "Dings"),
            ("Display", "BabyIDE" if self._settings.display_mode == "babyide" else "Smash"),
            ("Quit", ""),
        ]

    def draw(self, screen) -> None:
        """Draw the dim overlay + panel on top of the running scene."""
        if not self._visible:
            return
        w, h = screen.get_size()

        # Translucent dark overlay over the whole screen.
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 190))
        screen.blit(overlay, (0, 0))

        rows = self._rows()
        title_surf = self._font.render("Options", True, (255, 255, 255))
        line_h = self._font.get_linesize() + 18

        # About footer occupies two small lines + padding at the panel bottom.
        foot_line_h = self._small_font.get_linesize()
        footer_h = foot_line_h * 2 + 24

        panel_w = int(w * 0.6)
        panel_h = title_surf.get_height() + 60 + line_h * len(rows) + 40 + footer_h
        panel_x = (w - panel_w) // 2
        panel_y = (h - panel_h) // 2

        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill((20, 20, 30, 235))
        screen.blit(panel, (panel_x, panel_y))

        # Centred title.
        title_y = panel_y + 30
        screen.blit(
            title_surf,
            title_surf.get_rect(center=(w // 2, title_y + title_surf.get_height() // 2)),
        )

        pad = 48
        left_x = panel_x + pad
        right_x = panel_x + panel_w - pad
        y = title_y + title_surf.get_height() + 30

        for i, (label, value) in enumerate(rows):
            highlighted = i == self._selected
            # Highlighted row → a bright palette colour; others → soft grey.
            color = config.PALETTE[i % len(config.PALETTE)] if highlighted else (200, 200, 200)
            label_surf = self._font.render(label, True, color)
            screen.blit(label_surf, (left_x, y))
            if value:
                value_surf = self._font.render(value, True, color)
                screen.blit(value_surf, value_surf.get_rect(topright=(right_x, y)))
            y += line_h

        # About footer: two quiet centred lines at the bottom of the panel.
        foot_grey = (140, 140, 150)
        foot_top = panel_y + panel_h - 16 - foot_line_h * 2
        line1 = self._small_font.render(f"mashpad v{mashpad.__version__}", True, foot_grey)
        line2 = self._small_font.render(
            f"{config.COMPANY}, {config.BUILD_YEAR}", True, foot_grey
        )
        screen.blit(line1, line1.get_rect(center=(w // 2, foot_top + foot_line_h // 2)))
        screen.blit(
            line2,
            line2.get_rect(center=(w // 2, foot_top + foot_line_h + foot_line_h // 2)),
        )
