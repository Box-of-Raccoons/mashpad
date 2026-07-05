# mashpad/gen_voice.py — pre-generate all voice WAV clips once at install time.
#
# Usage:
#   python -m mashpad.gen_voice [--engine piper|espeak] [--voice MODEL] [--force]
#
# Vocabulary: a–z (26), 0–9 (10), plus every shape in config.SHAPES (8) = 44 clips.
# Output: sounds/voice/<stem>.wav  (stem = the keymap name).
#
# No pygame import — this script runs before/without a display.

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from mashpad.audio import repo_root
from mashpad import config, imagepack

# ── Vocabulary ────────────────────────────────────────────────────────────────

def _vocabulary() -> list[tuple[str, str]]:
    """Return list of (stem, spoken_text) pairs.

    For a single letter or digit, TTS engines pronounce it as the letter/digit
    name ("A", "seven", etc.) when given the bare character — no special markup
    needed.  Shape names are plain words.

    Image spoken words are added after the base vocabulary, deduped: all entries
    that share the same spoken word (e.g. raccoon1..raccoon13 → "raccoon") produce
    exactly ONE clip.  The stem written is the spoken word itself.
    """
    pairs: list[tuple[str, str]] = []
    for ch in "abcdefghijklmnopqrstuvwxyz":
        pairs.append((ch, ch))
    for ch in "0123456789":
        pairs.append((ch, ch))
    for shape in config.SHAPES:          # single source of truth — never hardcoded
        pairs.append((shape, shape))

    # Add distinct spoken words from the image pack, skipping words already in
    # the vocabulary.  raccoon1..raccoon13 → one clip: raccoon.wav.
    existing = {stem for stem, _ in pairs}
    images_dir = repo_root() / "assets" / config.IMAGES_DIR_NAME
    for entry in imagepack.scan(images_dir):
        if entry.spoken not in existing:
            pairs.append((entry.spoken, entry.spoken))
            existing.add(entry.spoken)

    return pairs


# ── Model resolution ──────────────────────────────────────────────────────────

DEFAULT_PIPER_MODEL = "en_US-lessac-medium"
_VOICES_CACHE = Path.home() / ".local" / "share" / "piper-voices"


def _resolve_piper_model(model: str) -> str:
    """Resolve a model name or path for piper's --model flag.

    If `model` already looks like a path (contains a separator or ends in
    .onnx), return it as-is.  Otherwise treat it as a voice name and look in
    the standard per-user cache that install.sh populates.
    """
    if model.endswith(".onnx") or "/" in model or os.sep in model:
        return model
    return str(_VOICES_CACHE / f"{model}.onnx")


# ── Engine functions ──────────────────────────────────────────────────────────

def _generate_piper(text: str, out_path: Path, model: str) -> None:
    """Generate one WAV via the piper CLI, with text piped via stdin.

    Equivalent to:  echo TEXT | piper --model MODEL --output_file OUT
    but uses subprocess.run with input= so no shell quoting is needed.
    """
    subprocess.run(
        ["piper", "--model", model, "--output_file", str(out_path)],
        input=text.encode(),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _generate_espeak(text: str, out_path: Path) -> None:
    """Generate one WAV via espeak-ng."""
    subprocess.run(
        ["espeak-ng", "-w", str(out_path), text],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m mashpad.gen_voice",
        description=(
            "Pre-generate voice WAV clips for mashpad's full 44-word vocabulary.\n\n"
            "Default engine: piper (natural neural voice).  install.sh downloads the\n"
            f"  model (~60 MB) from huggingface rhasspy/piper-voices to\n"
            f"  {_VOICES_CACHE}.\n"
            "If the piper binary is absent, re-run with --engine espeak."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--engine",
        choices=["piper", "espeak"],
        default="piper",
        help="TTS engine (default: piper)",
    )
    parser.add_argument(
        "--voice",
        default=DEFAULT_PIPER_MODEL,
        metavar="MODEL",
        help=(
            f"piper model name or path to .onnx file "
            f"(default: {DEFAULT_PIPER_MODEL}); ignored for espeak"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing WAV files instead of skipping them",
    )
    args = parser.parse_args(argv)

    # Verify the engine binary before looping over the vocabulary.
    binary = "piper" if args.engine == "piper" else "espeak-ng"
    if shutil.which(binary) is None:
        if args.engine == "piper":
            sys.exit(
                "[gen_voice] ERROR: 'piper' binary not found in PATH.\n"
                "  Run install.sh to install piper-tts via pip, or use:\n"
                "    python -m mashpad.gen_voice --engine espeak"
            )
        else:
            sys.exit(
                "[gen_voice] ERROR: 'espeak-ng' not found in PATH.\n"
                "  Install with: sudo apt-get install espeak-ng"
            )

    model_path = _resolve_piper_model(args.voice) if args.engine == "piper" else ""

    out_dir = repo_root() / "sounds" / "voice"
    out_dir.mkdir(parents=True, exist_ok=True)

    vocab = _vocabulary()
    written = 0
    skipped = 0

    for stem, text in vocab:
        out_path = out_dir / f"{stem}.wav"
        if out_path.exists() and not args.force:
            skipped += 1
            continue
        if args.engine == "piper":
            _generate_piper(text, out_path, model_path)
        else:
            _generate_espeak(text, out_path)
        rel = out_path.relative_to(repo_root())
        print(f"  wrote {rel}")
        written += 1

    print(
        f"[gen_voice] done: {written} written, {skipped} skipped"
        f" (use --force to regenerate all)."
    )


if __name__ == "__main__":
    main()
