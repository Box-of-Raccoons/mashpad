# mashpad/main.py — pygame init, event loop, input handling, dev-mode flag.
#
# Wires the pure-logic core (keymap / items / ratelimit / trail) to the pygame
# runtime (render / audio). No pygame calls happen at import time — everything
# lives inside main().

from __future__ import annotations

import argparse
import random

import pygame

from mashpad import (
    codepanel, codetext, combos, config, imagepack, items, keymap,
    lockdown as lockdown_mod, melodies, paths, render, settings as settings_mod,
)
from mashpad.audio import Audio
from mashpad.items import ItemField
from mashpad.menu import Menu
from mashpad.phrases import PhraseDirector
from mashpad.ratelimit import TokenBucket
from mashpad.splash import Splash
from mashpad.trail import Trail
from mashpad.voiceselect import VoiceSelector

# One unseeded RNG for the whole app (colours, shapes, effect choice, positions).
rng = random.Random()


def _parse_size(text: str) -> tuple[int, int]:
    """Parse a 'WxH' string (e.g. '1280x720') into an (int, int) size.

    Raises argparse.ArgumentTypeError on any malformed input so that argparse
    prints a proper usage error instead of a raw traceback.
    """
    parts = text.lower().split("x")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError(
            f"expected WxH (e.g. 1280x720), got {text!r}"
        )
    try:
        w, h = int(parts[0]), int(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected WxH (e.g. 1280x720), got {text!r}"
        )
    if w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError(
            f"expected WxH (e.g. 1280x720), got {text!r}"
        )
    return w, h


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


def _draw_babyide_tab(screen, font, tab_h: int, width: int, filename: str) -> None:
    """Draw the fake editor tab bar (a filename chip) across the top."""
    pygame.draw.rect(screen, (30, 30, 42), (0, 0, width, tab_h))
    label = font.render(filename or "", True, (235, 235, 245))
    chip_w = label.get_width() + 40
    pygame.draw.rect(screen, (52, 52, 70), (0, 0, chip_w, tab_h))
    pygame.draw.rect(screen, (120, 170, 120), (0, tab_h - 4, chip_w, 4))  # accent underline
    screen.blit(label, (20, (tab_h - label.get_height()) // 2))


def _spawn(field: ItemField, spec, pos, now: float, font, audio: Audio,
           selector: VoiceSelector, letter_case: str, director: PhraseDirector,
           images=None, note=None) -> None:
    """Register an item, build+cache its render surface once, and fire its audio.

    Every allowed spawn advances the voice selector, then plays the clip in the
    now-current voice (letters honour *letter_case* when their surface is built).
    *note* (a note name in piano mode, None in dings mode) selects the effect
    layer: a melody note vs. a random ding — see Audio.play_for.
    Also feeds the phrase director: if spawn force-faded a live item to enforce
    the MAX_ITEMS cap, arms 'screenfull'; the spawn itself — with the live image
    count — drives hello / fun / raccoons.
    """
    item, forced_fade = field.spawn(spec, pos, now)
    item.surface = render.build_item_surface(spec, font, images, letter_case=letter_case)
    selector.on_keystroke()
    audio.play_for(spec, rng, voice=selector.current(), note=note)
    raccoons = sum(
        1 for i in field.items
        if i.state(now) != items.DEAD and i.spec.kind == "image"
    )
    director.note_spawn(now, raccoons)
    if forced_fade:
        director.note_cap_hit(now)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="mashpad")
    parser.add_argument(
        "--windowed",
        nargs="?",
        const="1280x720",
        default=None,
        type=_parse_size,
        metavar="WxH",
        help="run in a window (default 1280x720); omit for fullscreen",
    )
    parser.add_argument("--mute", action="store_true", help="disable audio")
    parser.add_argument(
        "--no-lockdown",
        action="store_true",
        help=(
            "don't install the Windows keyboard lockdown "
            "(Win key / Alt-Tab / Alt-F4 / Alt-Esc / Ctrl-Esc stay live)"
        ),
    )
    args = parser.parse_args(argv)

    # Larger mixer buffer BEFORE pygame.init() (which would otherwise init the
    # mixer at the 512-sample default — audible crackle/underruns on the Pi).
    pygame.mixer.pre_init(frequency=config.MIXER_FREQUENCY_HZ, size=-16, channels=2, buffer=config.MIXER_BUFFER_SAMPLES)
    pygame.init()

    if args.windowed is not None:
        screen = pygame.display.set_mode(args.windowed)
        pygame.mouse.set_visible(True)
    else:
        # Fullscreen on the Pi: NEVER pass a real size — (0,0)+FULLSCREEN takes
        # the native KMS/DRM mode.
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.mouse.set_visible(False)
    pygame.display.set_caption("mashpad")

    # Windows keyboard lockdown: in fullscreen, swallow the OS escape combos a
    # baby could hit (Win key, Alt-Tab, Alt-F4, Alt-Esc, Ctrl-Esc) at the OS
    # level. A silent no-op off Windows, when --windowed, or when --no-lockdown.
    # Ctrl+Alt+Del is reserved by the OS and is never affected. Torn down before
    # pygame.quit() at shutdown.
    lock = lockdown_mod.Lockdown()
    code_stream = None  # bound below in babyide setup; referenced in finally
    try:
        if args.windowed is None and not args.no_lockdown:
            lock.start()

        font_path = paths.app_root() / "assets" / "DejaVuSans-Bold.ttf"
        # Sized once from ITEM_SIZE_PX; reused for every glyph (never re-created).
        font = pygame.font.Font(str(font_path), int(config.ITEM_SIZE_PX * 0.9))

        # Load the image pack.  Scan first (pure, no pygame), then load + scale each
        # PNG once at startup.  A corrupt or unloadable file prints one warning and is
        # skipped — the app must not crash on a bad image.
        _image_entries = imagepack.scan(
            paths.app_root() / "assets" / config.IMAGES_DIR_NAME
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

        # Grown-up options: load persisted settings, apply master volume, and build
        # the voice selector from the discovered packs + the saved mode.
        settings_path = paths.data_dir() / config.SETTINGS_FILE
        app_settings = settings_mod.load(settings_path)
        audio.set_master_volume(app_settings.volume / 100.0)
        # Gender per discovered pack (unknown packs → None) for cycle alternation.
        genders = {
            name: config.voice_gender(name)
            for name in audio.voices
        }
        selector = VoiceSelector(
            audio.voices, app_settings.voice_mode, genders, rng
        )
        menu = Menu(app_settings, audio, font_path, settings_path)
        # voice_mode as it was when the menu opened — used to detect a rebuild on close.
        menu_open_voice_mode = app_settings.voice_mode

        field = ItemField()
        trail = Trail()
        # Piano-mode melody sequencer: one note per allowed spawn, stepping
        # through the song list. Only consulted when sound_mode == "piano".
        sequencer = melodies.MelodySequencer()
        bucket = TokenBucket(config.BUCKET_CAPACITY, config.BUCKET_REFILL_PER_S)
        splash = Splash(screen)
        director = PhraseDirector(rng, pygame.time.get_ticks() / 1000.0)
        if splash.visible:
            director.note_splash(pygame.time.get_ticks() / 1000.0)
        clock = pygame.time.Clock()

        width, height = screen.get_size()
        half = config.ITEM_SIZE_PX / 2.0  # keep keyboard spawns fully on-screen

        # BabyIDE mode: source token stream (resumed from the saved cursor) + a
        # scrolling code panel below a filename tab. Built once; only used when
        # display_mode == "babyide".
        babyide_state_path = paths.data_dir() / config.BABYIDE_STATE_FILE
        tab_font = pygame.font.Font(str(font_path), config.BABYIDE_TAB_FONT_PX)
        tab_h = tab_font.get_linesize() + 16

        def _read_source(name):
            return (paths.source_dir() / name).read_text(encoding="utf-8")

        code_stream = codetext.CodeStream(
            codetext.SOURCE_FILES, _read_source,
            position=codetext.load_position(babyide_state_path),
        )
        code_panel = codepanel.CodePanel(
            (0, tab_h, width, height - tab_h),
            font_path, config.BABYIDE_FONT_PX, config.BABYIDE_TOKEN_COLORS,
            config.BOUNCE_S, config.BOUNCE_OVERSHOOT,
        )
        babyide_tokens_since_save = 0

        running = True
        while running:
            now = pygame.time.get_ticks() / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    continue

                # While the menu is open, ALL events route to it and baby input is
                # suppressed.  On the close transition, reapply volume and rebuild the
                # selector if the voice mode changed.
                if menu.visible:
                    if menu.handle_event(event) == "quit":
                        running = False
                    if not menu.visible:  # just closed
                        audio.set_master_volume(app_settings.volume / 100.0)
                        if app_settings.voice_mode != menu_open_voice_mode:
                            selector = VoiceSelector(
                                audio.voices, app_settings.voice_mode, genders, rng,
                            )
                    continue

                # Splash: the first key press / click dismisses it, then the very
                # same event is processed normally below — the dismissing smash still
                # spawns its item (and grown-up combos still do their thing).
                if splash.visible and event.type in (
                    pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN
                ):
                    splash.dismiss()

                if event.type == pygame.KEYDOWN:
                    # Grown-up combos (AltGr-safe; see mashpad.combos). Ctrl+left-Alt
                    # +Q quits, Ctrl+left-Alt+O opens the options menu.
                    combo = combos.grown_up_combo(event)
                    if combo == combos.QUIT:
                        running = False
                        continue
                    if combo == combos.OPTIONS:
                        menu_open_voice_mode = app_settings.voice_mode
                        menu.open()
                        continue
                    if app_settings.display_mode == "babyide":
                        # Speak the pressed key + tone (same audio decision as
                        # smash) but print the next SOURCE token instead of a
                        # giant glyph; pop the odd fading raccoon over the editor.
                        image_weight = config.RACCOON_WEIGHTS.get(
                            app_settings.raccoon_amount, config.RACCOON_WEIGHTS["normal"])
                        if bucket.try_take(now):
                            key_spec = keymap.item_for_key(
                                _char_for_event(event), rng, _extras, image_weight=image_weight)
                            note = (sequencer.next()
                                    if app_settings.sound_mode == "piano" else None)
                            selector.on_keystroke()
                            audio.play_for(key_spec, rng, voice=selector.current(), note=note)
                            token = code_stream.next()
                            if token is not None:
                                code_panel.append(token, now)
                            raccoons = sum(
                                1 for i in field.items
                                if i.state(now) != items.DEAD and i.spec.kind == "image"
                            )
                            director.note_spawn(now, raccoons)
                            # Occasionally pop one fading raccoon over the editor.
                            if _extras and rng.random() < config.BABYIDE_RACCOON_CHANCE:
                                rspec = keymap.item_for_key(None, rng, _extras, image_weight=1.0)
                                if rspec.kind == "image":
                                    rpos = (rng.uniform(half, width - half),
                                            rng.uniform(half, height - half))
                                    ritem, forced = field.spawn(rspec, rpos, now)
                                    ritem.surface = render.build_item_surface(
                                        rspec, font, images, letter_case=app_settings.letter_case)
                                    if forced:
                                        director.note_cap_hit(now)
                            babyide_tokens_since_save += 1
                            if babyide_tokens_since_save >= config.BABYIDE_CHECKPOINT_TOKENS:
                                codetext.save_position(code_stream.position(), babyide_state_path)
                                babyide_tokens_since_save = 0
                        else:
                            director.note_drop(now)
                        continue
                    image_weight = config.RACCOON_WEIGHTS.get(app_settings.raccoon_amount, config.RACCOON_WEIGHTS["normal"])
                    spec = keymap.item_for_key(
                        _char_for_event(event), rng, _extras, image_weight=image_weight
                    )
                    if bucket.try_take(now):
                        pos = (rng.uniform(half, width - half),
                               rng.uniform(half, height - half))
                        # Advance the melody only on an allowed spawn (piano mode);
                        # dings mode passes note=None → a random effect.
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        _spawn(field, spec, pos, now, font, audio, selector,
                               app_settings.letter_case, director, images, note)
                    else:
                        director.note_drop(now)

                elif event.type == pygame.MOUSEMOTION:
                    trail.add(event.pos, now)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if app_settings.display_mode == "babyide":
                        continue  # BabyIDE is a key smasher; ignore clicks
                    # Click → shape at the cursor, through the SAME rate-limit bucket.
                    image_weight = config.RACCOON_WEIGHTS.get(app_settings.raccoon_amount, config.RACCOON_WEIGHTS["normal"])
                    spec = keymap.item_for_key(None, rng, _extras, image_weight=image_weight)
                    if bucket.try_take(now):
                        # Clicks advance the melody too (piano mode); see above.
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        _spawn(field, spec, event.pos, now, font, audio, selector,
                               app_settings.letter_case, director, images, note)
                    else:
                        director.note_drop(now)

            field.update(now)
            trail.prune(now)
            audio.update(now)  # start due phrases + apply the duck envelope

            # Reactive phrases: once per frame, when enabled and the menu is closed.
            # The splash does NOT gate polling — hello greets over it at startup;
            # nothing else can be armed before the first input dismisses it. Rotate
            # the voice first (cycle mode) so the comment speaks in the new voice.
            if app_settings.phrases and not menu.visible:
                trigger = director.poll(now)
                if trigger is not None:
                    selector.on_trigger()
                    print(f"[mashpad] phrase: {trigger} ({selector.current() or 'default'})")
                    audio.play_phrase(trigger, rng, selector.current())

            screen.fill(render.BACKGROUND)
            if app_settings.display_mode == "babyide":
                code_panel.draw(screen, now)          # persistent scrolling code
                for item in field.items:              # raccoons fading, over code
                    render.draw_item(screen, item, now)
                _draw_babyide_tab(screen, tab_font, tab_h, width, code_stream.current_file)
            else:
                for item in field.items:              # oldest → newest
                    render.draw_item(screen, item, now)
                render.draw_trail(screen, trail, now)
            menu.draw(screen)                 # overlay on top when visible
            splash.draw(screen, now)          # startup splash, above everything
            pygame.display.flip()

            clock.tick(config.FPS)

    finally:
        if code_stream is not None:  # best-effort save the resume cursor
            try:
                codetext.save_position(code_stream.position(),
                                       paths.data_dir() / config.BABYIDE_STATE_FILE)
            except Exception:  # noqa: BLE001 — shutdown must never raise
                pass
        lock.stop()  # remove the keyboard hook (no-op if it was never installed)
        pygame.quit()
