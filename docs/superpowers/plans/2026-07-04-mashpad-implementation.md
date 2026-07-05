# mashpad — implementation plan

**Date:** 2026-07-04
**Spec:** `docs/superpowers/specs/2026-07-04-mashpad-design.md` (approved)
**Execution model:** Opus/Sonnet worker agents make file edits; the orchestrator
runs every gate and all git. Workers are told: *shell is denied — file edits
only; desk-check your work; the orchestrator runs verification.*

## Stakes

Low-blast, greenfield. New repo, no consumers, fully reversible. The two real
risks are environmental, not code: (R1) pygame on the Pi's KMS/DRM framebuffer,
(R2) Piper TTS on Pi aarch64. Both are isolated behind fallbacks below and are
only fully verifiable on the Pi itself.

## Assumptions (marked)

- **A1 (inferred):** Raspberry Pi OS Bookworm's apt `python3-pygame` is built
  against system SDL2 with kmsdrm support, so fullscreen-without-desktop works.
  `install.sh` therefore uses **apt python3-pygame**, not pip. Confirmed only
  when Hardy runs it on the Pi; fallback if kmsdrm fails: enable the legacy
  fbcon driver or install X-less cage/weston — decide then, don't pre-build.
- **A2 (inferred):** `piper-tts` installs and runs one-shot on Pi aarch64 via
  pip. Fallback wired into `gen_voice.py`: `--engine espeak` uses espeak-ng
  (apt, always available) to produce the same WAV set.
- **A3 (inferred):** default ALSA device routes audio (HDMI or 3.5mm per
  `raspi-config`). README documents the switch; code just uses the default
  mixer device.
- **A4 (confirmed by design):** dev machine is Windows; pygame pip wheel works
  there; all unit tests run headless via `SDL_VIDEODRIVER=dummy`.

## Decided forks (low-blast, swappable)

- **Sound effects are procedurally generated**, not downloaded. A
  `gen_effects.py` synthesizes ~8 short effects (pops, boings, dings, chirps)
  with numpy → WAV. No licensing/asset-hunting risk, deterministic, and CC0 by
  construction. Swap: drop real giggle WAVs into `sounds/effects/` — the
  loader plays whatever is in that directory.
- **Bundled font:** DejaVu Sans Bold TTF committed to `assets/` (free license,
  identical rendering on Windows dev and Pi). Swap: replace the file.
- **Palette:** 12 fully saturated HSV-spaced colors defined in `config.py`.
- **Shapes (8):** circle, square, triangle, star, heart, diamond, pentagon,
  ring. Single source of truth: `config.SHAPES`; `gen_voice.py` imports it so
  voice clips can never drift from the shape list.

## Architecture pinned (workers must not re-decide)

```
mashpad/
├── mashpad/
│   ├── __init__.py
│   ├── __main__.py     # python -m mashpad → main.main()
│   ├── config.py       # ALL tunables: palette, SHAPES, MAX_ITEMS=20, FPS=60,
│   │                   #   timings (bounce 0.3s, linger 4s, fade 1.5s),
│   │                   #   rate limits, trail params, mixer channels=8
│   ├── keymap.py       # item_for_key(key, rng) -> ItemSpec(kind, name, color)
│   │                   #   kind ∈ {letter, digit, shape}; pure, no pygame
│   ├── items.py        # Item lifecycle: states SPAWNING→ALIVE→FADING→DEAD,
│   │                   #   update(dt), scale/alpha as pure functions of age;
│   │                   #   ItemField: holds items, enforces MAX_ITEMS cap
│   │                   #   (oldest item forced to FADING when cap exceeded);
│   │                   #   pure logic — NO pygame imports
│   ├── ratelimit.py    # token bucket: capacity 8, refill 6/s; pure
│   ├── render.py       # pygame drawing: build_item_surface(spec, font) done
│   │                   #   ONCE at spawn (cached on item); per-frame only
│   │                   #   blit + set_alpha; smoothscale only during bounce;
│   │                   #   shape polygon vertex math lives here
│   ├── audio.py        # loads sounds/voice/*.wav + sounds/effects/*.wav,
│   │                   #   play_for(spec): voice clip + random effect;
│   │                   #   degrades silently if dirs empty/mixer init fails
│   ├── trail.py        # mouse trail: deque of (pos, t), fade 0.6s; pure
│   │                   #   logic + a draw() in render.py
│   ├── main.py         # argparse (--windowed WxH, --mute), pygame init
│   │                   #   (fullscreen on Pi / windowed dev), event loop,
│   │                   #   Ctrl+Alt+Q exit, wires everything
│   ├── gen_voice.py    # CLI: piper (default) or --engine espeak →
│   │                   #   sounds/voice/{a..z,0..9,<shape>}.wav
│   └── gen_effects.py  # numpy synthesis → sounds/effects/*.wav
├── assets/DejaVuSans-Bold.ttf
├── sounds/effects/.gitkeep   # generated, not committed
├── sounds/voice/.gitkeep     # generated, not committed
├── tests/              # pytest: keymap, items, ratelimit, trail
├── install.sh          # Pi: apt deps, pip piper, gen clips, systemd enable
├── mashpad.service     # systemd unit (Restart=always, tty/DRM perms)
├── requirements-dev.txt
└── README.md           # dev-mode usage + Pi install + audio routing notes
```

Behavioral details binding on workers:

- Letter/digit keys → that character; every other key → random shape.
- Spawn: random position (kept fully on-screen), random palette color, bounce
  in (overshoot ~1.15× then settle) over 0.3s, linger 4s, fade 1.5s.
- Rate limiter drops excess spawns silently (no queueing).
- Audio: `pygame.mixer` 8 channels; if no free channel, skip the clip (never
  block). Voice and effect play together.
- Mouse: motion feeds trail (rainbow hue cycling by time); click = shape at
  cursor (rate-limited through the same bucket).
- Exit: `K_q` with `KMOD_CTRL` and `KMOD_ALT` both set → clean shutdown.
- Fullscreen mode never calls `pygame.display.set_mode` with a size — use
  `(0,0)` + `FULLSCREEN` so it takes the native mode on the Pi.
- Everything tunable lives in `config.py` with a one-line comment each.

## Tasks (serialized — one repo, one worker at a time)

Branch: `feature/initial-implementation` off `develop` (orchestrator creates
BEFORE task 1; verify with `git branch --show-current` before every commit).
One commit per task after its gate passes. Merge `--no-ff` into `develop` at
the end. Never touch `main`.

### Task 1 — pure-logic core + tests (worker: Sonnet)

**Files:** `mashpad/{__init__,config,keymap,items,ratelimit,trail}.py`,
`tests/test_{keymap,items,ratelimit,trail}.py`, `requirements-dev.txt`.

**Spec:** everything in Architecture above for those modules. No pygame
imports anywhere in these files (constants like key names are defined locally
in keymap as plain strings/ints — main.py will translate pygame keycodes).
Tests cover: letter/digit/other mapping incl. randomness seams (rng injected);
lifecycle state transitions at exact age boundaries; alpha/scale monotonic
during fade/bounce; MAX_ITEMS cap forcing oldest to FADING; token bucket
capacity/refill/drop; trail expiry.

**Gate (orchestrator):** `python -m pytest -q` green on Windows; record
pass count as baseline. `python -c "import mashpad.items"` with no pygame
installed conceptually — enforce via a test that asserts `"pygame" not in
sys.modules` after importing the pure modules.

### Task 2 — runtime shell (worker: Opus)

**Files:** `mashpad/{__main__,main,render,audio}.py`,
`assets/DejaVuSans-Bold.ttf` (orchestrator supplies the binary — worker must
NOT fabricate binary content), `sounds/*/.gitkeep`.

**Spec:** Architecture + behavioral details above. `--windowed 1280x720`
default size for dev; `--mute` skips mixer init. Audio module must survive:
missing WAV dirs, mixer init failure (log once, run silent). Render pre-builds
item surfaces at spawn; no per-frame font rendering or full-surface
smoothscale after bounce completes.

**Gate (orchestrator):** pytest still green vs task-1 baseline; then run
`python -m mashpad --windowed --mute` on Windows and observe: keys spawn
letters/digits/shapes, bounce/fade correct, cap at 20, mouse trail, click
spawns, Ctrl+Alt+Q exits cleanly. (Audio observed in task 3 gate once clips
exist.)

### Task 3 — asset generation + deploy kit (worker: Sonnet)

**Files:** `mashpad/gen_voice.py`, `mashpad/gen_effects.py`, `install.sh`,
`mashpad.service`, `README.md`.

**Spec:** `gen_voice.py` — vocabulary = a–z, 0–9, `config.SHAPES`; piper via
`piper` CLI with a downloaded en_US voice (document model choice in README);
`--engine espeak` fallback shells out to `espeak-ng -w`. `gen_effects.py` —
numpy-synthesized: 3 pops (sine burst + exp decay, varied pitch), 2 boings
(pitch slide), 2 dings (harmonic stack), 1 chirp; 44.1kHz 16-bit mono, ≤0.5s
each, peak-normalized to −3dBFS. `install.sh` — idempotent; apt: python3-pygame
python3-numpy espeak-ng; pip: piper-tts (failure tolerated → espeak path);
runs both generators; installs+enables `mashpad.service`. Unit: runs as user
`pi` on tty1, `Restart=always`, `After=sound.target`, supplementary groups
`video input audio render` for DRM/evdev access.

**Gate (orchestrator):** pytest green vs baseline; `bash -n install.sh`;
run `gen_effects.py` on Windows and play the WAVs; run `gen_voice.py
--engine espeak` if espeak-ng available on Windows, else desk-check both
engine paths line-by-line; then full app run WITH audio (`--windowed`, no
--mute) — smash test with ears.

### Task 4 — orchestrator-only: merge + Pi handoff

No worker. Re-run full suite, read the complete diff `develop..feature`,
merge `--no-ff` into `develop`. Write the Pi deploy steps for Hardy (below).
Notify via raccourier.

## Worker brief boilerplate (include verbatim in every worker prompt)

> Repo: `C:\Users\hardy\code\mashpad`, branch `feature/initial-implementation`
> (already created). Stack: Python 3.11+, pygame 2, pytest. Shell is denied —
> make file edits only and desk-check them; the orchestrator runs all
> verification and git. Do not touch files outside your task's list. Do not
> re-decide anything in the plan's "Architecture pinned" section; if the spec
> seems wrong or two requirements conflict, STOP that item and report instead
> of forcing it. Commit messages are the orchestrator's job. RETURN: files
> touched; key logic quoted verbatim; what you verified by reading vs assumed;
> explicit deviations from spec.

## Verification that only Hardy can do (Pi, after merge)

1. `git clone` / pull onto the Pi, `sudo bash install.sh`, reboot.
2. Confirms A1 (kmsdrm fullscreen), A2 (piper voice vs espeak fallback),
   A3 (audio routing), boot-to-app timing, real smash test, Ctrl+Alt+Q.
3. If kmsdrm fails: report the SDL error text — that decides the A1 fallback.

## Out of scope (recorded so it isn't re-litigated)

- No settings UI, no config file — constants in `config.py` (spec decision).
- No keyboard "lockdown" beyond owning the fullscreen tty — on Pi OS Lite
  with no desktop there is nothing to Alt-Tab to; Ctrl+Alt+F2 tty switching
  is left alone deliberately as a second grown-up escape hatch.
- No PyPI packaging; deploy is git + install.sh.
