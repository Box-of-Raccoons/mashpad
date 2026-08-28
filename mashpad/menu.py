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

# Smallest font the panel may shrink to before it gives up and overflows.
MENU_MIN_FONT_PX = 20

# Vertical breathing room left around the panel when fitting it to the screen.
MENU_MARGIN_PX = 40

# Challenge values the menu is allowed to offer. This list was the per-slice
# gate while the epic was landing; all five have now shipped.
IMPLEMENTED_CHALLENGES = ("none", "letter", "number", "spell", "math")

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
        self._font_path = str(font_path)
        # Fonts are sized to the screen at draw time (see _metrics), so they are
        # cached by point size rather than built once here.
        self._fonts: dict[int, "pygame.font.Font"] = {}
        self._metrics_key = None
        self._metrics = None
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

        count = len(self._row_specs())
        if key == pygame.K_UP:
            self._selected = (self._selected - 1) % count
        elif key == pygame.K_DOWN:
            self._selected = (self._selected + 1) % count
        elif key == pygame.K_LEFT:
            self._step(-1)
        elif key == pygame.K_RIGHT:
            self._step(+1)
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if self._selected_key() == "quit":
                return "quit"
        return None

    def _selected_key(self) -> str:
        """Key of the highlighted row, clamped if the row list just shrank."""
        specs = self._row_specs()
        self._selected = max(0, min(self._selected, len(specs) - 1))
        return specs[self._selected][0]

    def _step(self, direction: int) -> None:
        """Apply a left/right change to the currently highlighted row.

        Dispatch is by row key, so adding a row means adding it to _row_specs()
        and writing its _step_<key> handler — nothing else has to stay in sync.
        Rows with no handler (Quit) are a silent no-op.
        """
        handler = getattr(self, f"_step_{self._selected_key()}", None)
        if handler is None:
            return
        handler(direction)
        # Some rows appear and disappear (Answers, Numbers), so the highlight
        # may now be past the end of a shorter list.
        self._selected = max(0, min(self._selected, len(self._row_specs()) - 1))

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

    def _step_letters(self, direction: int = 0) -> None:
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

    def _step_phrases(self, direction: int = 0) -> None:
        # Two-value toggle: left and right both flip it.
        self._settings.phrases = not self._settings.phrases
        self._save()

    def _step_sounds(self, direction: int = 0) -> None:
        # Two-value toggle: left and right both flip piano <-> dings.
        self._settings.sound_mode = (
            "dings" if self._settings.sound_mode == "piano" else "piano"
        )
        self._save()
        # Audition one note when switching to Piano so grown-ups hear the timbre
        # (the Dings side is auditioned by its own random effect on real spawns).
        if self._settings.sound_mode == "piano":
            self._audio.play_note(_AUDITION_NOTE)

    def _step_display(self, direction: int = 0) -> None:
        # Two-value toggle: left and right both flip smash <-> babyide.
        self._settings.display_mode = (
            "babyide" if self._settings.display_mode == "smash" else "smash"
        )
        self._save()

    def _cycle(self, current, options, direction):
        """Next value in *options*, wrapping. Unknown current value → the first."""
        try:
            idx = options.index(current)
        except ValueError:
            return options[0]
        return options[(idx + direction) % len(options)]

    def _step_challenge(self, direction: int) -> None:
        self._settings.challenge = self._cycle(
            self._settings.challenge, IMPLEMENTED_CHALLENGES, direction or 1)
        self._save()

    def _step_answer_style(self, direction: int) -> None:
        self._settings.answer_style = self._cycle(
            self._settings.answer_style, settings_mod.ANSWER_STYLES, direction or 1)
        self._save()

    def _step_math_range(self, direction: int) -> None:
        self._settings.math_range = self._cycle(
            self._settings.math_range, settings_mod.MATH_RANGES, direction or 1)
        self._save()

    def _step_math_ops(self, direction: int) -> None:
        self._settings.math_ops = self._cycle(
            self._settings.math_ops, settings_mod.MATH_OPS, direction or 1)
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

    _MATH_OP_LABELS = {
        "add": "Adding",
        "subtract": "Taking away",
        "both": "Both",
    }

    _CHALLENGE_LABELS = {
        "none": "Off",
        "letter": "Find a letter",
        "number": "Find a number",
        "spell": "Spelling",
        "math": "Math",
    }

    def _row_specs(self):
        """(key, label, value) for every visible row, in draw order.

        The single source of truth: navigation counts these, the left/right
        dispatch reads the key, and draw() renders the label and value. Answers
        and Numbers only appear when the selected challenge actually uses them,
        which also keeps the panel short enough to fit a 720p window.
        """
        s = self._settings
        rows = [
            ("voice", "Voice", self._voice_label()),
            ("volume", "Volume", str(s.volume)),
            ("letters", "Letters", "ABC" if s.letter_case == "upper" else "abc"),
            ("raccoons", "Raccoons", s.raccoon_amount.title()),
            ("phrases", "Phrases", "On" if s.phrases else "Off"),
            ("sounds", "Sounds", "Piano" if s.sound_mode == "piano" else "Dings"),
            ("display", "Display", "BabyIDE" if s.display_mode == "babyide" else "Smash"),
            ("challenge", "Challenge", self._CHALLENGE_LABELS.get(s.challenge, "Off")),
        ]
        if s.challenge in ("spell", "math"):
            rows.append(("answer_style", "Answers",
                         "Guided" if s.answer_style == "guided" else "Advanced"))
        if s.challenge == "math":
            rows.append(("math_range", "Numbers",
                         "2 to 9" if s.math_range == "2-9" else "0 to 20"))
            rows.append(("math_ops", "Sums",
                         self._MATH_OP_LABELS.get(s.math_ops, "Both")))
        rows.append(("quit", "Quit", ""))
        return rows

    def _rows(self):
        """(label, value) pairs, in draw order."""
        return [(label, value) for _key, label, value in self._row_specs()]

    # ------------------------------------------------------------- panel size

    def _font_at(self, px: int):
        font = self._fonts.get(px)
        if font is None:
            font = self._fonts[px] = pygame.font.Font(self._font_path, px)
        return font

    def _measure(self, height: int, row_count: int):
        """(font, small_font, line_h, footer_h, panel_h) fitted to *height*.

        The panel used to be built from a fixed 48px font, which overflowed even
        the 1280x720 windowed default at eight rows. Shrinking to fit keeps every
        row reachable on any screen the app runs on, Pi or dev window.
        """
        key = (height, row_count)
        if self._metrics_key == key:
            return self._metrics
        px = MENU_FONT_PX
        while True:
            font = self._font_at(px)
            small = self._font_at(max(12, round(px * ABOUT_FONT_PX / MENU_FONT_PX)))
            line_h = font.get_linesize() + round(18 * px / MENU_FONT_PX)
            footer_h = small.get_linesize() * 2 + 24
            panel_h = font.get_linesize() + 60 + line_h * row_count + 40 + footer_h
            if panel_h <= height - MENU_MARGIN_PX or px <= MENU_MIN_FONT_PX:
                break
            px -= 2
        self._metrics_key = key
        self._metrics = (font, small, line_h, footer_h, panel_h)
        return self._metrics

    def panel_height(self, height: int) -> int:
        """Height the panel would occupy on a screen *height* px tall."""
        return self._measure(height, len(self._row_specs()))[4]

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
        # Fitted to the screen, so the panel never runs off the bottom.
        font, small_font, line_h, footer_h, panel_h = self._measure(h, len(rows))
        title_surf = font.render("Options", True, (255, 255, 255))
        foot_line_h = small_font.get_linesize()

        panel_w = int(w * 0.6)
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
            label_surf = font.render(label, True, color)
            screen.blit(label_surf, (left_x, y))
            if value:
                value_surf = font.render(value, True, color)
                screen.blit(value_surf, value_surf.get_rect(topright=(right_x, y)))
            y += line_h

        # About footer: two quiet centred lines at the bottom of the panel.
        foot_grey = (140, 140, 150)
        foot_top = panel_y + panel_h - 16 - foot_line_h * 2
        line1 = small_font.render(f"mashpad v{mashpad.__version__}", True, foot_grey)
        line2 = small_font.render(
            f"{config.COMPANY}, {config.BUILD_YEAR}", True, foot_grey
        )
        screen.blit(line1, line1.get_rect(center=(w // 2, foot_top + foot_line_h // 2)))
        screen.blit(
            line2,
            line2.get_rect(center=(w // 2, foot_top + foot_line_h + foot_line_h // 2)),
        )
