# mashpad/main.py — pygame init, event loop, input handling, dev-mode flag.
#
# Wires the pure-logic core (keymap / items / ratelimit / trail) to the pygame
# runtime (render / audio). No pygame calls happen at import time — everything
# lives inside main().

from __future__ import annotations

import argparse
import math
import random

import pygame

from mashpad import (
    challenge as challenge_mod, codepanel, codetext, combos, config, imagepack,
    items, keymap, lockdown as lockdown_mod, melodies, paths, render,
    settings as settings_mod,
)
from mashpad.audio import Audio
from mashpad.challenge import ChallengeDirector
from mashpad.items import ItemField
from mashpad.menu import IMPLEMENTED_CHALLENGES, Menu
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


def _scaled(surface, scale: float):
    """Resize a freshly built item surface once, at spawn (never per frame)."""
    if scale == 1.0:
        return surface
    return pygame.transform.smoothscale(
        surface,
        (max(1, int(round(surface.get_width() * scale))),
         max(1, int(round(surface.get_height() * scale)))),
    )


def _challenge_stems(round_, level: int) -> tuple[str, ...]:
    """Stems for one challenge utterance: the ask, or a hint rung.

    Level 0 is both the opening ask and the re-announce a parked round emits on
    the next press, so it must speak the full carrier again — a child returning
    after twenty minutes gets no context from a bare "B".
    """
    if level <= 1:
        carrier = ("find-the-number" if round_.kind == "number"
                   else "find-the-letter")
        return (carrier, round_.target)
    if level == 2 and round_.art:
        return (round_.target, "for", round_.art)   # "B… for… balloon"
    return (round_.target,)


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
           images=None, note=None, item_scale: float = 1.0,
           max_items=None) -> None:
    """Register an item, build+cache its render surface once, and fire its audio.

    Every allowed spawn advances the voice selector, then plays the clip in the
    now-current voice (letters honour *letter_case* when their surface is built).
    *note* (a note name in piano mode, None in dings mode) selects the effect
    layer: a melody note vs. a random ding — see Audio.play_for.
    Also feeds the phrase director: if spawn force-faded a live item to enforce
    the MAX_ITEMS cap, arms 'screenfull'; the spawn itself — with the live image
    count — drives hello / fun / raccoons.

    *item_scale* and *max_items* are the challenge layer's two occlusion knobs:
    non-target spawns shrink to CHALLENGE_ITEM_SCALE and the field caps at
    CHALLENGE_MAX_ITEMS so the centred target stays readable under a mash.
    """
    item, forced_fade = field.spawn(spec, pos, now, max_items=max_items)
    item.surface = _scaled(
        render.build_item_surface(spec, font, images, letter_case=letter_case),
        item_scale)
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

        def _build_challenge():
            """The round director for the selected challenge, or None for plain smash.

            BabyIDE has no glyph field to overlay a target on, so a challenge
            simply does not run there. Only values the menu can actually select
            are built: a hand-edited settings.json naming an unshipped challenge
            would otherwise draw from an empty target pool.
            """
            if (app_settings.display_mode == "babyide"
                    or app_settings.challenge == "none"
                    or app_settings.challenge not in IMPLEMENTED_CHALLENGES):
                return None
            return ChallengeDirector(
                app_settings.challenge, rng,
                art_names=[e.name for e in _image_entries],
            )

        challenge = _build_challenge()
        # (challenge, display_mode) as they were when the menu opened — a change
        # rebuilds the director on close, so the row isn't dead until a reboot.
        menu_open_challenge = (app_settings.challenge, app_settings.display_mode)
        # The pack speaking the current round; resolved once per ask, None = silent.
        challenge_voice = None

        field = ItemField()
        trail = Trail()
        # Piano-mode melody sequencer: one note per allowed spawn, stepping
        # through the song list. Only consulted when sound_mode == "piano".
        sequencer = melodies.MelodySequencer()
        bucket = TokenBucket(config.BUCKET_CAPACITY, config.BUCKET_REFILL_PER_S)
        splash = Splash(screen)
        director = PhraseDirector(
            rng, pygame.time.get_ticks() / 1000.0,
            fun_every=(config.BABYIDE_FUN_EVERY_SPAWNS
                       if app_settings.display_mode == "babyide"
                       else config.FUN_EVERY_SPAWNS),
        )
        if splash.visible:
            director.note_splash(pygame.time.get_ticks() / 1000.0)
        clock = pygame.time.Clock()

        width, height = screen.get_size()
        half = config.ITEM_SIZE_PX / 2.0  # keep keyboard spawns fully on-screen

        def _celebrate(spec, note, now: float) -> None:
            """The win payoff: the key's own sound, confetti, a raccoon, a line.

            Deliberately does NOT spawn a random-position glyph. The target
            flooding with colour is the answer; a second B somewhere else muddies
            which one the child found.
            """
            # The ask has been answered — drop any hint still queued so the
            # celebration line doesn't fight it for PHRASE_CHANNEL.
            audio.cancel_speech(now)
            audio.play_for(spec, rng, voice=selector.current(), note=note)
            cx, cy = width / 2.0, height / 2.0
            reach = config.ITEM_SIZE_PX * config.CHALLENGE_KEEPOUT_SCALE / 2.0
            for i in range(config.CHALLENGE_CONFETTI_N):
                # Ring the keep-out box, jittered — an exact circle reads mechanical.
                angle = 2.0 * math.pi * (i + rng.random()) / config.CHALLENGE_CONFETTI_N
                far = reach * rng.uniform(1.0, 1.35)
                pos = (min(max(cx + far * math.cos(angle), 0.0), float(width)),
                       min(max(cy + far * math.sin(angle), 0.0), float(height)))
                piece = keymap.item_for_key(None, rng, ())   # always a plain shape
                item, _forced = field.spawn(piece, pos, now,
                                            max_items=config.CHALLENGE_MAX_ITEMS)
                item.surface = _scaled(
                    render.build_item_surface(piece, font, images,
                                              letter_case=app_settings.letter_case),
                    config.CHALLENGE_CONFETTI_SCALE)
            if _extras:
                rspec = keymap.item_for_key(None, rng, _extras, image_weight=1.0)
                if rspec.kind == "image":
                    side = rng.choice((-1.0, 1.0))
                    rpos = (min(max(cx + side * reach * 1.15, half), width - half), cy)
                    ritem, _forced = field.spawn(rspec, rpos, now,
                                                 max_items=config.CHALLENGE_MAX_ITEMS)
                    ritem.surface = render.build_item_surface(
                        rspec, font, images, letter_case=app_settings.letter_case)
            audio.play_phrase("fun", rng, selector.current())

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

            # The three occlusion knobs, live only while a challenge is running:
            # smaller non-target glyphs, a tighter field cap, and a keep-out box
            # random spawns dodge. All three are required to keep the target
            # readable during exactly the mashing that escalates the hints.
            challenge_on = challenge is not None
            item_scale = config.CHALLENGE_ITEM_SCALE if challenge_on else 1.0
            max_items = (config.CHALLENGE_MAX_ITEMS if challenge_on
                         else config.MAX_ITEMS)
            keepout = render.challenge_keepout(width, height) if challenge_on else None

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
                        # A Challenge or Display change takes effect on close, not
                        # at the next boot — the grown-up is watching the screen.
                        if ((app_settings.challenge, app_settings.display_mode)
                                != menu_open_challenge):
                            challenge = _build_challenge()
                            challenge_voice = None
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
                        menu_open_challenge = (app_settings.challenge,
                                               app_settings.display_mode)
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
                            # Reveal a small burst of tokens per keypress so whole
                            # lines fill in and the panel scrolls at a fun pace,
                            # instead of crawling one token at a time. Only the last
                            # of the burst carries the bounce (newest wins).
                            chunk = rng.randint(
                                config.BABYIDE_TOKENS_PER_KEY_MIN,
                                config.BABYIDE_TOKENS_PER_KEY_MAX)
                            burst = codetext.take(code_stream, chunk)
                            for token in burst:
                                code_panel.append(token, now)
                            emitted = len(burst)
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
                            babyide_tokens_since_save += emitted
                            if babyide_tokens_since_save >= config.BABYIDE_CHECKPOINT_TOKENS:
                                codetext.save_position(code_stream.position(), babyide_state_path)
                                babyide_tokens_since_save = 0
                        else:
                            director.note_drop(now)
                        continue
                    char = _char_for_event(event)
                    # Judge BEFORE the bucket: the child pressed a key, and the
                    # rate limiter's opinion says nothing about whether they are
                    # trying. Lowercased because _char_for_event preserves shift
                    # /caps case and the director's answers are lowercase.
                    verdict = challenge_mod.IGNORED
                    if challenge is not None:
                        verdict = challenge.on_key(
                            char.lower() if char else None, now)
                    image_weight = config.RACCOON_WEIGHTS.get(app_settings.raccoon_amount, config.RACCOON_WEIGHTS["normal"])
                    spec = keymap.item_for_key(
                        char, rng, _extras, image_weight=image_weight
                    )
                    # Advance the melody only on an allowed spawn (piano mode);
                    # dings mode passes note=None → a random effect.
                    if verdict == challenge_mod.CORRECT:
                        # The winning press bypasses the bucket entirely: a
                        # mashing toddler empties it, and swallowing the one
                        # press that must land would break the whole mode.
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        _celebrate(spec, note, now)
                    elif bucket.try_take(now):
                        pos = render.spawn_position(rng, width, height, half, keepout)
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        _spawn(field, spec, pos, now, font, audio, selector,
                               app_settings.letter_case, director, images, note,
                               item_scale=item_scale, max_items=max_items)
                    else:
                        director.note_drop(now)

                elif event.type == pygame.MOUSEMOTION:
                    trail.add(event.pos, now)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if app_settings.display_mode == "babyide":
                        continue  # BabyIDE is a key smasher; ignore clicks
                    # A click is baby input like any other press: it feeds the
                    # ladder, and at the any-key step it can win the round.
                    verdict = challenge_mod.IGNORED
                    if challenge is not None:
                        verdict = challenge.on_key(None, now)
                    # Click → shape at the cursor, through the SAME rate-limit bucket.
                    image_weight = config.RACCOON_WEIGHTS.get(app_settings.raccoon_amount, config.RACCOON_WEIGHTS["normal"])
                    spec = keymap.item_for_key(None, rng, _extras, image_weight=image_weight)
                    if verdict == challenge_mod.CORRECT:
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        _celebrate(spec, note, now)
                    elif bucket.try_take(now):
                        # Clicks advance the melody too (piano mode); see above.
                        note = (sequencer.next()
                                if app_settings.sound_mode == "piano" else None)
                        # The child pointed here, so a click ignores the keep-out
                        # box; only random spawns dodge the target.
                        _spawn(field, spec, event.pos, now, font, audio, selector,
                               app_settings.letter_case, director, images, note,
                               item_scale=item_scale, max_items=max_items)
                    else:
                        director.note_drop(now)

            field.update(now)
            trail.prune(now)
            audio.update(now)  # start due phrases + apply the duck envelope

            # Challenge round clock and events, once per frame. The clock only
            # runs while the child can act on it: a 40-second options visit would
            # otherwise escalate the round to a gimme behind their back, and the
            # first ask waits for the splash so it can't cut off startup 'hello'.
            challenge_view = None
            if challenge is not None:
                if menu.visible or splash.visible:
                    challenge.pause(now)
                else:
                    challenge.resume(now)
                    if challenge.round is None:
                        challenge.start_round(now)
                    signal = challenge.poll(now)
                    if signal is not None:
                        kind, payload = signal
                        round_ = challenge.round
                        # Level 0 is the ask; a parked round re-announces as hint 0.
                        level = 0 if kind == "ask" else payload
                        if kind == "ask":
                            challenge_voice = audio.challenge_voice(
                                _challenge_stems(round_, 0),
                                preferred=selector.current())
                        print(f"[mashpad] challenge {kind} {round_.target!r} "
                              f"step {level} ({challenge_voice or 'silent'})")
                        if challenge_voice is not None:
                            stems = _challenge_stems(round_, level)
                            if not audio.speak(stems, challenge_voice, rng, now):
                                # A pack with the ask but no "B for balloon" still
                                # gets the plain re-ask, never a silent hint.
                                audio.speak((round_.target,), challenge_voice,
                                            rng, now)
                challenge_view = challenge.view()

            # Reactive phrases: once per frame, when enabled and the menu is closed.
            # The splash does NOT gate polling — hello greets over it at startup;
            # nothing else can be armed before the first input dismisses it. Rotate
            # the voice first (cycle mode) so the comment speaks in the new voice.
            # Suppressed outright while a challenge utterance is queued or
            # sounding: the gate has to sit here, ahead of poll(), because a
            # trigger armed this frame would otherwise fire play_phrase and cut a
            # word out of "Find the letter B". Nothing backs up — armed triggers
            # expire on PHRASE_ARM_TTL_S.
            if app_settings.phrases and not menu.visible and not audio.speaking:
                # Keep the fun/manager cadence matched to the current mode (a
                # Display toggle mid-session switches Smash <-> BabyIDE pacing).
                director.set_fun_every(
                    config.BABYIDE_FUN_EVERY_SPAWNS
                    if app_settings.display_mode == "babyide"
                    else config.FUN_EVERY_SPAWNS)
                trigger = director.poll(now)
                if trigger is not None:
                    # BabyIDE speaks corporate-manager praise instead of the smash
                    # "fun" line — same cadence/cooldown, just a different clip set.
                    if app_settings.display_mode == "babyide" and trigger == "fun":
                        trigger = "manager"
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
                # Target first: under the flying items, over the background, so
                # the overlay never blocks the smash payoff. Rebuilt from view()
                # every frame — no render state is held between frames.
                render.draw_challenge_target(screen, challenge_view, font,
                                             images, now)
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
