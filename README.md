# mashpad

A lightweight baby keyboard smasher for Raspberry Pi. Every key press or mouse
click spawns a bright letter, digit, or shape with a spoken name and a fun sound
effect. Inspired by [BabySmash](https://www.hanselman.com/babysmash/) by Scott
Hanselman. Runs on Raspberry Pi OS Lite (no desktop required) via a systemd
service that starts at boot.

## Dev quickstart

```sh
pip install -r requirements-dev.txt
python -m mashpad --windowed          # run in a window (default 1280×720)
python -m pytest                      # run the test suite
```

Add `--mute` to skip audio init when sound files haven't been generated yet.

## Generating sounds

Before running without `--mute`, generate the sound sets:

```sh
# Synthesize pops, boings, dings, and chirps (numpy, no network required):
python -m mashpad.gen_effects

# Synthesize the piano-melody notes (xylophone tones, G4–C6; numpy, no network):
python -m mashpad.gen_notes

# Generate voice clips (requires piper or espeak-ng):
python -m mashpad.gen_voice                    # piper (default, see below)
python -m mashpad.gen_voice --engine espeak    # espeak-ng fallback
```

### Voice pack layout

Voice clips live under `sounds/voice/`. Two layouts are supported and can coexist:

```
sounds/voice/
├── hello.wav              # flat legacy layout → one anonymous "default" voice
├── circle.wav
├── puck/                  # a named voice pack (dir name = voice name)
│   ├── hello-1.ogg        #   multiple takes per word (-1, -2, -3)
│   ├── hello-2.ogg        #   a random take is chosen each spawn
│   └── circle-1.ogg
└── nova/
    └── hello-1.ogg
```

Each pack subdirectory holds `<word>-<take>.ogg` (or `.wav`) files grouped by
word; a file with no `-<digit>` suffix counts as take 1. Flat `*.wav` files
directly under `sounds/voice/` form the single **default** voice. The app runs
fine with zero packs, flat files only, or several packs — the Voice option in the
menu lists whatever it finds.

### Piper voice model

The default voice engine is [Piper](https://github.com/rhasspy/piper) using the
`en_US-lessac-medium` model (~60 MB). Download it manually if you're not running
`install.sh`:

```sh
VOICES=~/.local/share/piper-voices
BASE=https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium
mkdir -p "$VOICES"
wget -O "$VOICES/en_US-lessac-medium.onnx"      "$BASE/en_US-lessac-medium.onnx"
wget -O "$VOICES/en_US-lessac-medium.onnx.json" "$BASE/en_US-lessac-medium.onnx.json"
pip install piper-tts
python -m mashpad.gen_voice
```

## Pi install

```sh
git clone <this-repo> ~/mashpad
cd ~/mashpad
sudo bash install.sh
```

Reboot when it finishes — mashpad starts automatically on tty1.

`install.sh` handles everything: system packages (`python3-pygame`,
`python3-numpy`, `espeak-ng`), the display runtime (see below), piper install
and model download, sound generation, and systemd service setup. Piper steps are
optional — if they fail, espeak-ng is used instead.

### How it reaches the screen (no desktop needed)

Still Raspberry Pi OS **Lite** — there's no desktop environment. But mashpad
doesn't draw to the framebuffer directly: SDL's bare `kmsdrm` backend fails to
present on the Pi 4's split GPU (the v3d core renders, the vc4 core scans out),
so the app renders black. Instead the service runs mashpad inside
[**cage**](https://github.com/cage-kiosk/cage) — a single-application Wayland
kiosk — which drives that GPU path correctly. `install.sh` therefore also
installs:

- **`libgl1-mesa-dri libegl1 libgles2`** — the Mesa EGL/GLES userspace. A bare
  Lite image ships none of it (the text console uses the kernel framebuffer), so
  without these SDL dies at startup with `EGL not initialized`.
- **`cage`** — the kiosk compositor mashpad runs inside.
- **`seatd`** — a seat manager that grants cage DRM + VT access (a systemd system
  service has no login session to get a seat from). It's enabled at install time.
  Debian runs it as `seatd -g video`, so the unit's existing `video` group
  membership is all cage needs to reach the seat — no extra setup.

None of this is a desktop — it's the minimum needed to put a fullscreen app on
the screen from a headless Lite boot.

## Audio output (Pi)

By default, audio routes to whichever output is active in `raspi-config`:
**Advanced Options → Audio** — choose between HDMI and the 3.5 mm headphone
jack. Run `raspi-config` over SSH or before the first reboot.

## Desktop (Windows)

mashpad also ships as a standalone Windows app (a frozen PyInstaller build — see
the packaging notes). When it runs **fullscreen** it installs an OS-level
keyboard lockdown so a baby can't escape or close the app by mashing system
combos. It swallows:

| Combo | Normally does |
|-------|---------------|
| **Windows key** (left/right) | Opens the Start menu |
| **Alt+Tab** | Switches windows |
| **Alt+F4** | Closes the app |
| **Alt+Esc** | Cycles windows |
| **Ctrl+Esc** | Opens the Start menu |

It **cannot** intercept **Ctrl+Alt+Del** — that's a Secure Attention Sequence
the OS reserves, and no application (this one included) can trap it. That's your
guaranteed way out if you ever need it.

The grown-up combos still work as always: **Ctrl+Alt+O** opens the options menu
and **Ctrl+Alt+Q** quits the app.

The lockdown is active only in fullscreen. Windowed runs (`--windowed`) never
hook, and you can force it off in fullscreen with **`--no-lockdown`**. It is a
silent no-op on Raspberry Pi / Linux — that platform is unaffected.

In the installed Windows app, settings are saved to
**`%APPDATA%\mashpad\settings.json`** (not next to the read-only program files).
Deleting that file restores the defaults. Running from a source checkout (dev +
Pi) still keeps `settings.json` in the repo root as before.

## Controls

| Input | Action |
|-------|--------|
| Letter or digit key | Spawn that character |
| Any other key | Spawn a random shape (or image) |
| Mouse motion | Draw a fading rainbow trail |
| Mouse click | Spawn a shape at the cursor |
| **Ctrl+Alt+O** | Open the grown-up options menu |
| **Ctrl+Alt+Q** | Quit (grown-up escape combo) |

SSH into the Pi is the fallback exit method if the keyboard is inaccessible.

## Options menu

Press **Ctrl+Alt+O** (a combo a baby won't mash) to open a simple, couch-readable
overlay. The baby's keys are ignored while it's open; the scene keeps animating
underneath. Navigate with the **arrow keys** (Up/Down to move, Left/Right to
change a value), press **Enter** on *Quit* to exit the app, and **Esc** (or
Ctrl+Alt+O again) to close the menu.

| Setting | What it does |
|---------|--------------|
| **Voice** | Which voice pack speaks. Steps through each installed pack (shown as friendly labels like *Voice 1*), then **Random** (a new voice per spawn) and **Cycle** (the voice changes when the app comments, alternating male/female). Choosing a specific pack plays a sample word so you can audition it. |
| **Volume** | Master volume, 0–100 in steps of 10. Voice clips play at this level; sound effects at 70% of it. |
| **Letters** | Render letters as **ABC** (uppercase) or **abc** (lowercase). |
| **Raccoons** | How often a non-letter key spawns image art instead of a shape (when images are installed): **Less** (~25%), **Normal** (~50%), **Lots** (~75%). |
| **Phrases** | **On/Off** — whether the app occasionally speaks a short reactive comment (see [Reactive phrases](#reactive-phrases)). |
| **Sounds** | **Piano/Dings** — what plays on each keypress or click alongside the spoken name. **Piano** (default) steps through children's-song melodies (London Bridge, Twinkle Twinkle, Mary Had a Little Lamb, and more) — any key plays the next note, and finished songs roll into the next. **Dings** plays the classic random pops/boings/dings. Switching to Piano plays a sample note. |

Every change is saved immediately (and again on close) to `settings.json` in the
repo root. That file is device-local and git-ignored — deleting it restores the
defaults (Random voice, volume 80, uppercase, Normal raccoons).

## Splash screen

On launch, mashpad shows a centred splash image (`assets/splash.png`) with a
gentle breathing pulse over the running scene. The **first** key press or mouse
click dismisses it — and that same smash still spawns its item, so the baby's
first bash pays off immediately. If the splash image is missing or unreadable,
the app simply starts without it.

## Reactive phrases

Now and then the app speaks a short, friendly comment in the current voice
(toggle with **Phrases** in the options menu). Phrases are rate-limited — at most
one every 60 seconds, and each kind has its own longer cooldown — so they stay a
treat, not a nag. In **Cycle** voice mode, the voice rotates to a new speaker
(alternating male/female) each time a phrase plays. Five things can prompt one:

| Trigger | When it fires |
|---------|---------------|
| **hello** | The first spawn after launch, and again after a long idle gap — a reliable greeting (this one ignores the cooldown). |
| **slowdown** | A burst of very fast mashing (many key presses dropped by the rate limiter in a few seconds). |
| **screenfull** | The screen fills up and the oldest item is pushed off to make room. |
| **raccoons** | A pile of image "raccoon" stickers are on screen at once. |
| **fun** | Occasionally, after a few hundred spawns — just for fun. |

Phrase clips live in each voice pack as `phrase-<trigger>-<n>.ogg` (e.g.
`phrase-slowdown-3.ogg`) and are kept separate from spoken words, so they are
never picked as a letter/shape name.

## Custom images

Drop PNG files into `assets/images/` to add sticker art (raccoon stickers,
custom shapes, etc.) that spawns when the baby smashes non-alphanumeric keys.

**Naming rules:**

- Trailing digits are stripped to form the spoken word: `raccoon1.png`,
  `raccoon2.png`, … all share one voice clip, `raccoon.wav`.
- Names without trailing digits use the full stem: `wave.png` → "wave".
- Single-character names (e.g. `a.png`, `7.png`) reskin that letter or digit
  key — they appear only when that key is pressed, and are not added to the
  random-spawn pool.
- All other names become pool members: non-alphanumeric key presses and mouse
  clicks pick uniformly from the combined shapes + image pool.

**After adding images**, regenerate voice clips so the new spoken words are
available:

```sh
python -m mashpad.gen_voice   # or --engine espeak
```

Images are loaded once at startup, scaled to fit within the item size
(`ITEM_SIZE_PX × ITEM_SIZE_PX` in `config.py`) while preserving aspect ratio.
Transparency (PNG alpha) is preserved. Corrupt or unloadable files are skipped
with a warning — the app will not crash.

## Versioning

The version lives in `mashpad/__init__.py` (`__version__`) and is shown in the
options-menu About footer. Development builds carry a Maven-style `-SNAPSHOT`
suffix naming the *next* release (e.g. `1.0.0-SNAPSHOT`); cutting a release
strips the suffix (`1.0.0`) on `main`, and the next development cycle bumps to
the following `-SNAPSHOT`.

## Font license

`assets/DejaVuSans-Bold.ttf` is from the [DejaVu Fonts](https://dejavu-fonts.github.io/)
project, released under a free permissive license. See [dejavu-fonts.org](https://dejavu-fonts.org)
for the full license text.
