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

Before running without `--mute`, generate the two sound sets:

```sh
# Synthesize pops, boings, dings, and chirps (numpy, no network required):
python -m mashpad.gen_effects

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
`python3-numpy`, `espeak-ng`), piper install and model download, sound
generation, and systemd service setup. Piper steps are optional — if they fail,
espeak-ng is used instead.

## Audio output (Pi)

By default, audio routes to whichever output is active in `raspi-config`:
**Advanced Options → Audio** — choose between HDMI and the 3.5 mm headphone
jack. Run `raspi-config` over SSH or before the first reboot.

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
| **Voice** | Which voice pack speaks. Steps through each installed pack, then **Random** (a new voice per spawn) and **Cycle** (rotates voices every ~200 spawns). Choosing a specific pack plays a sample word so you can audition it. |
| **Volume** | Master volume, 0–100 in steps of 10. Voice clips play at this level; sound effects at 70% of it. |
| **Letters** | Render letters as **ABC** (uppercase) or **abc** (lowercase). |
| **Raccoons** | How often a non-letter key spawns image art instead of a shape (when images are installed): **Less** (~25%), **Normal** (~50%), **Lots** (~75%). |

Every change is saved immediately (and again on close) to `settings.json` in the
repo root. That file is device-local and git-ignored — deleting it restores the
defaults (Random voice, volume 80, uppercase, Normal raccoons).

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

## Font license

`assets/DejaVuSans-Bold.ttf` is from the [DejaVu Fonts](https://dejavu-fonts.github.io/)
project, released under a free permissive license. See [dejavu-fonts.org](https://dejavu-fonts.org)
for the full license text.
