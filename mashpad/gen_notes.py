# mashpad/gen_notes.py — synthesize the piano-melody note set (numpy + stdlib wave).
#
# Usage:
#   python -m mashpad.gen_notes [--force]
#
# Produces the 11 diatonic C-major notes G4–C6 (g4.wav … c6.wav) at 44100 Hz /
# 16-bit / mono, each an additive "xylophone" mallet tone (the timbre Hardy
# picked from the audition — see docs/piano-melodies-plan.md). All clips are
# peak-normalized to −3 dBFS AFTER summing partials + strike, so no clip can
# overshoot into hard clipping.
#
# Same conventions as gen_effects.py (no pygame import — runs without a display).
# The note names double as the WAV filenames and as the note tokens in
# mashpad.melodies, so keep NOTE_NAMES in sync with the melody data.

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

from mashpad.paths import app_root

# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_RATE: int = 44100
PEAK_TARGET: float = 10 ** (-3.0 / 20)   # −3 dBFS ≈ 0.708
_FADE_SAMPLES: int = int(SAMPLE_RATE * 0.010)  # 10 ms anti-click tail

# Semitone offset of each natural note within an octave (C = 0).
_SEMITONE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

# The generated diatonic C-major set, G4 → C6 (11 notes). The design table
# (G3–C5) shifted +12 semitones because the C5-root xylophone won the audition.
NOTE_NAMES: tuple[str, ...] = (
    "g4", "a4", "b4", "c5", "d5", "e5", "f5", "g5", "a5", "b5", "c6",
)

# Xylophone mallet timbre (winning audition candidate). Additive partials at
# quint tuning (2nd partial at 3×), each with its own exponential decay, plus a
# short noise-burst strike transient. Short 0.5 s tail so notes clear the bed
# channels before the next mash — see docs/piano-melodies-plan.md.
_PARTIALS = (1.0, 3.0, 6.7)
_WEIGHTS = (1.0, 0.40, 0.12)
_DECAYS = (9.0, 16.0, 22.0)
_DURATION_S = 0.5
_CLICK_MS = 4.0
_CLICK_AMP = 0.25
_DETUNE = 0.0


# ── Low-level helpers ─────────────────────────────────────────────────────────

def note_to_midi(name: str) -> int:
    """'c5' → 72, 'g4' → 67, 'c6' → 84. MIDI note number for a note filename."""
    letter, octave = name[0], int(name[1:])
    return (octave + 1) * 12 + _SEMITONE[letter]


def _freq(midi: int) -> float:
    """Equal-tempered frequency of a MIDI note (A4 = 69 = 440 Hz)."""
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _fade_end(samples: np.ndarray) -> np.ndarray:
    """Fade the last _FADE_SAMPLES to zero to prevent output clicks."""
    n = len(samples)
    f = min(_FADE_SAMPLES, n)
    out = samples.copy()
    out[-f:] *= np.linspace(1.0, 0.0, f)
    return out


def _click(dur_s: float, amp: float, rng: np.random.Generator) -> np.ndarray:
    """Short noise transient (the mallet/hammer strike)."""
    n = int(SAMPLE_RATE * dur_s)
    noise = rng.uniform(-1.0, 1.0, n)
    return noise * np.linspace(1.0, 0.0, n) ** 2 * amp


def synth(f0: float) -> np.ndarray:
    """Additive xylophone tone at fundamental *f0*: partials + strike click.

    Each partial is a sine at f0·ratio, weighted and shaped by its own
    exp(−decay·t) envelope; partials past ~Nyquist are dropped. A deterministic
    noise burst (seeded on the pitch) fakes the mallet strike. The summed signal
    is peak-normalized to −3 dBFS, then the 10 ms tail is faded.
    """
    t = np.linspace(0.0, _DURATION_S, int(SAMPLE_RATE * _DURATION_S), endpoint=False)
    out = np.zeros_like(t)
    for ratio, w, d in zip(_PARTIALS, _WEIGHTS, _DECAYS):
        f = f0 * ratio
        if f > SAMPLE_RATE / 2 * 0.9:
            continue  # drop partials past ~Nyquist
        if _DETUNE > 0.0:
            tone = 0.5 * (np.sin(2 * np.pi * f * (1 - _DETUNE) * t)
                          + np.sin(2 * np.pi * f * (1 + _DETUNE) * t))
        else:
            tone = np.sin(2 * np.pi * f * t)
        out += w * tone * np.exp(-d * t)
    rng = np.random.default_rng(int(f0))  # deterministic strike per pitch
    click = _click(_CLICK_MS / 1000.0, _CLICK_AMP, rng)
    out[: len(click)] += click
    peak = np.max(np.abs(out))
    if peak > 0.0:
        out *= PEAK_TARGET / peak
    return _fade_end(out)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    """Write a 16-bit mono WAV. samples must be in [-1, 1] (clipping guard included)."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit = 2 bytes per sample
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m mashpad.gen_notes",
        description=(
            "Synthesize mashpad's 11 piano-melody notes (xylophone timbre, "
            "G4–C6) and write them to sounds/notes/ as 44100 Hz 16-bit mono WAV."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing WAV files instead of skipping them",
    )
    args = parser.parse_args(argv)

    out_dir = app_root() / "sounds" / "notes"
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    skipped = 0
    for name in NOTE_NAMES:
        out_path = out_dir / f"{name}.wav"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        _write_wav(out_path, synth(_freq(note_to_midi(name))))
        rel = out_path.relative_to(app_root())
        print(f"  wrote {rel}")
        written += 1

    print(
        f"[gen_notes] done: {written} written, {skipped} skipped"
        f" (use --force to regenerate all)."
    )


if __name__ == "__main__":
    main()
