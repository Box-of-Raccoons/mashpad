# mashpad/gen_effects.py — synthesize all sound effects with numpy + stdlib wave.
#
# Usage:
#   python -m mashpad.gen_effects [--force]
#
# Produces 8 short clips (≤0.5 s each) at 44100 Hz / 16-bit / mono.
# All clips are peak-normalized to −3 dBFS (peak amplitude ≈ 0.708) AFTER
# summing any partials, so partial-heavy sounds (dings) cannot clip.
#
# No pygame import — this script runs before/without a display.

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


# ── Low-level helpers ─────────────────────────────────────────────────────────

def _t(duration_s: float) -> np.ndarray:
    """Time array of `duration_s` seconds at SAMPLE_RATE (endpoint excluded)."""
    n = int(SAMPLE_RATE * duration_s)
    return np.linspace(0.0, duration_s, n, endpoint=False)


def _fade_end(samples: np.ndarray) -> np.ndarray:
    """Fade the last _FADE_SAMPLES to zero to prevent output clicks."""
    n = len(samples)
    f = min(_FADE_SAMPLES, n)
    out = samples.copy()
    out[-f:] *= np.linspace(1.0, 0.0, f)
    return out


def _normalize(samples: np.ndarray) -> np.ndarray:
    """Peak-normalize to PEAK_TARGET.  Silent arrays pass through unchanged."""
    peak = np.max(np.abs(samples))
    if peak == 0.0:
        return samples
    return samples * (PEAK_TARGET / peak)


def _write_wav(path: Path, samples: np.ndarray) -> None:
    """Write a 16-bit mono WAV.  samples must be in [-1, 1] (clipping guard included)."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)          # 16-bit = 2 bytes per sample
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())


# ── Synthesis functions ───────────────────────────────────────────────────────

def _make_pop(freq: float, decay: float = 30.0, duration: float = 0.15) -> np.ndarray:
    """Sine burst with fast exponential decay.

    f(t) = sin(2π·freq·t) · exp(−decay·t)

    decay=30 means amplitude falls to exp(−30·0.15) ≈ 0.011 at the end —
    nearly silent before the 10 ms tail fade.
    """
    t = _t(duration)
    raw = np.sin(2.0 * np.pi * freq * t) * np.exp(-decay * t)
    return _normalize(_fade_end(raw))


def _make_boing(
    f0: float,
    f1: float,
    duration: float = 0.4,
    decay: float = 8.0,
    vibrato_hz: float = 6.0,
    vibrato_depth: float = 2.0,
) -> np.ndarray:
    """Pitch-sliding sine with moderate decay and slight vibrato.

    The instantaneous phase is the integral of a linear frequency ramp from f0
    to f1 over `duration` seconds:
        phase(t) = 2π · (f0·t + (f1−f0)·t²/(2·duration))

    Vibrato adds a small sinusoidal phase modulation (FM depth = vibrato_depth
    radians ≈ vibrato_depth·vibrato_hz Hz of peak frequency deviation — subtle
    at depth=2.0, giving ±12 Hz on a 600 Hz tone).
    """
    t = _t(duration)
    inst_phase = 2.0 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2.0 * duration))
    vibrato = vibrato_depth * np.sin(2.0 * np.pi * vibrato_hz * t)
    raw = np.sin(inst_phase + vibrato) * np.exp(-decay * t)
    return _normalize(_fade_end(raw))


def _make_ding(
    fundamental: float,
    duration: float = 0.5,
    decay: float = 3.0,
) -> np.ndarray:
    """Harmonic stack: fundamental + 2.7x + 5.4x partials (inharmonic bell tone).

    Partials are weighted 1.0 / 0.5 / 0.25 before summing, then the whole
    mixture is normalized — so no individual partial can clip even though the
    raw sum can reach 1.75× amplitude.
    """
    t = _t(duration)
    h1 = np.sin(2.0 * np.pi * fundamental * t)
    h2 = np.sin(2.0 * np.pi * (fundamental * 2.7) * t) * 0.5
    h3 = np.sin(2.0 * np.pi * (fundamental * 5.4) * t) * 0.25
    # Sum BEFORE normalizing (spec constraint).
    raw = (h1 + h2 + h3) * np.exp(-decay * t)
    return _normalize(_fade_end(raw))


def _make_chirp(
    f0: float = 300.0,
    f1: float = 1200.0,
    duration: float = 0.25,
) -> np.ndarray:
    """Rising frequency sweep with a gentle sin² bell envelope.

    The envelope is sin²(π·t/T), which is 0 at both endpoints (no clicks
    even without the tail fade) and peaks at the midpoint.  The tail fade
    is still applied as an extra guard.
    """
    t = _t(duration)
    inst_phase = 2.0 * np.pi * (f0 * t + (f1 - f0) * t**2 / (2.0 * duration))
    envelope = np.sin(np.pi * t / duration) ** 2
    raw = np.sin(inst_phase) * envelope
    return _normalize(_fade_end(raw))


# ── Effect catalogue ──────────────────────────────────────────────────────────

def _build_effects() -> dict[str, np.ndarray]:
    """Return all 8 effects keyed by output filename stem."""
    return {
        "pop1":   _make_pop(400.0),
        "pop2":   _make_pop(650.0),
        "pop3":   _make_pop(900.0),
        "boing1": _make_boing(600.0, 150.0),
        "boing2": _make_boing(900.0, 250.0),
        "ding1":  _make_ding(880.0),
        "ding2":  _make_ding(1320.0),
        "chirp1": _make_chirp(300.0, 1200.0),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m mashpad.gen_effects",
        description=(
            "Synthesize mashpad's 8 sound effects (pops, boings, dings, chirp) "
            "and write them to sounds/effects/ as 44100 Hz 16-bit mono WAV files."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing WAV files instead of skipping them",
    )
    args = parser.parse_args(argv)

    out_dir = app_root() / "sounds" / "effects"
    out_dir.mkdir(parents=True, exist_ok=True)

    effects = _build_effects()
    written = 0
    skipped = 0

    for stem, samples in effects.items():
        out_path = out_dir / f"{stem}.wav"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        _write_wav(out_path, samples)
        rel = out_path.relative_to(app_root())
        print(f"  wrote {rel}")
        written += 1

    print(
        f"[gen_effects] done: {written} written, {skipped} skipped"
        f" (use --force to regenerate all)."
    )


if __name__ == "__main__":
    main()
