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
| Any other key | Spawn a random shape |
| Mouse motion | Draw a fading rainbow trail |
| Mouse click | Spawn a shape at the cursor |
| **Ctrl+Alt+Q** | Quit (grown-up escape combo) |

SSH into the Pi is the fallback exit method if the keyboard is inaccessible.

## Font license

`assets/DejaVuSans-Bold.ttf` is from the [DejaVu Fonts](https://dejavu-fonts.github.io/)
project, released under a free permissive license. See [dejavu-fonts.org](https://dejavu-fonts.org)
for the full license text.
