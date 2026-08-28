# Placeholder voice pack generator — local Kokoro TTS, no API, no quota.
#
# The challenge layer asks "find the letter... B!", which needs carrier clips
# ("find the letter", "for", "plus", ...) that none of the six shipped Gemini
# packs contain. Recording those for real is gated on a human listening test, so
# this writes one COMPLETE throwaway pack to sounds/voice/_placeholder/ purely so
# the loop can be played and judged on the Pi first. It is explicitly not pretty
# audio — it only has to be complete and correctly formatted.
#
# The pack name leads with an underscore on purpose: VoiceSelector excludes
# underscore-prefixed packs from the random/cycle rotation (voiceselect.py:33),
# so the robot voice can never gatecrash normal play, while Audio.challenge_voice
# still finds it by name because it is the only pack holding the carriers.
#
# Kokoro lives in the seniordev-voice repo (read-only from here), so `speech` is
# only importable with that repo on PYTHONPATH:
#
#   PYTHONPATH=~/code/seniordev-voice python tools/gen-voice-kokoro.py
#   PYTHONPATH=~/code/seniordev-voice python tools/gen-voice-kokoro.py --force
#
# Requires kokoro-onnx, soxr, soundfile, numpy. Dev machine only — the generated
# oggs are what ships to the Pi, not this script.

from __future__ import annotations

import argparse
import json
import statistics
import string
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "sounds" / "voice" / "_placeholder"
PHRASES_JSON = REPO / "tools" / "phrases.json"

# Kokoro renders at 24000; mashpad's mixer runs at config.MIXER_FREQUENCY_HZ.
# Writing 24k into the pack is silently wrong rather than broken: pygame at a
# 44100 mixer reported get_length() 0.789s for a clip that is truly 0.811s (2.7%
# short), i.e. it plays fast and slightly sharp. Always resample before writing.
TARGET_RATE = 44100

# Sanity bounds for a single accepted clip. The longest line in phrases.json
# renders at 3.2s and the shortest word at 0.68s, so these only ever fire on a
# genuinely broken render (empty audio, a hung sentence split, a silent model).
MIN_DUR_S = 0.15
MAX_DUR_S = 4.0
MIN_PEAK = 0.05

# Spoken words the shipped packs carry, derived from sounds/voice/achernar/ —
# a stem missing here is a word the app can say in a curated voice but not in
# the placeholder, which would make the placeholder a downgrade mid-session.
WORDS = [
    "balloon", "blocks", "book", "bubbles", "circle", "diamond", "draw", "drum",
    "heart", "hello", "hug", "love", "peekaboo", "pentagon", "ring", "sandwich",
    "sleep", "square", "star", "triangle", "water",
]

DIGIT_NAMES = ["zero", "one", "two", "three", "four", "five", "six", "seven",
               "eight", "nine"]

TEENS = ["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]

# The carriers that justify this whole pack. Hyphenated stems are safe because
# Audio._split_word_take() only splits a trailing "-<digits>" (audio.py:393-398),
# so "find-the-letter-1.ogg" parses as ("find-the-letter", 1).
CARRIERS = [
    ("find-the-letter", "find the letter"),
    ("find-the-number", "find the number"),
    ("can-you-spell", "can you spell"),
    ("for", "for"),
    ("what-is", "what is"),
    ("plus", "plus"),
    ("minus", "minus"),
    ("makes", "makes"),
    ("how-many", "how many"),
]


def items():
    """[(filename stem, text to speak), ...] for the whole pack, in write order."""
    out = []
    # A bare single letter phonemizes to its NAME, not its sound: espeak-ng
    # gives 'a' -> 'ˈeɪ', 'w' -> 'dˈʌbəljˌuː', 'y' -> 'wˈaɪ'. Verified for all
    # 26 against kokoro's tokenizer, so no spelling-out hack is needed.
    out += [(f"{ch}-1", ch) for ch in string.ascii_lowercase]
    # Filenames stay digits (the app looks up spec.spoken_name "7"); the spoken
    # text is the number word.
    out += [(f"{d}-1", DIGIT_NAMES[d]) for d in range(10)]
    out += [(f"{w}-1", w) for w in TEENS]
    out += [(f"{w}-1", w) for w in WORDS]
    out += [(f"{stem}-1", text) for stem, text in CARRIERS]
    # Reactive phrases: the triggers and their lines are the app's own copy —
    # read them rather than restating them, so the pack cannot drift from
    # whatever the shipped packs were cut from.
    phrases = json.loads(PHRASES_JSON.read_text(encoding="utf-8"))
    for trigger in sorted(phrases):
        for i, line in enumerate(phrases[trigger], start=1):
            out.append((f"phrase-{trigger}-{i}", line))
    return out


def render(kokoro, speech, text: str) -> np.ndarray:
    """Synthesize *text* and resample to TARGET_RATE. Raises on a bad render."""
    audio, rate = speech.synthesize(kokoro, text, speech.DEFAULT_VOICE)
    if rate != TARGET_RATE:
        audio = soxr.resample(audio, rate, TARGET_RATE)
    dur = len(audio) / TARGET_RATE
    peak = float(np.max(np.abs(audio))) if len(audio) else 0.0
    if not (MIN_DUR_S <= dur <= MAX_DUR_S):
        raise ValueError(f"duration {dur:.2f}s outside {MIN_DUR_S}-{MAX_DUR_S}s")
    if peak < MIN_PEAK:
        raise ValueError(f"peak {peak:.3f} below {MIN_PEAK} — silent render")
    return audio


def verify(path: Path) -> float:
    """Read the written file back and confirm its rate. Returns duration."""
    info = sf.info(str(path))
    # The rate that matters is the one on disk, not the one we passed to write:
    # a 24k file here is the fast-and-sharp playback bug, and it is invisible
    # until someone listens on the Pi.
    if info.samplerate != TARGET_RATE:
        raise ValueError(f"wrote {info.samplerate} Hz, expected {TARGET_RATE}")
    return info.frames / info.samplerate


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="re-render stems whose ogg already exists")
    args = ap.parse_args()

    try:
        import speech
    except ImportError:
        print("cannot import `speech` — run with "
              "PYTHONPATH=<path to seniordev-voice checkout>", file=sys.stderr)
        return 2

    plan = items()
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [(s, t) for s, t in plan
            if args.force or not (OUT / f"{s}.ogg").exists()]
    print(f"{len(plan)} stems planned, {len(todo)} to render into {OUT}", flush=True)

    kokoro = None
    if todo:
        t0 = time.time()
        # One load for the whole run: the ONNX model is 325MB and costs ~0.5s.
        kokoro = speech.Speech()._load_kokoro()
        print(f"kokoro loaded in {time.time() - t0:.1f}s", flush=True)

    written, failed = 0, []
    for i, (stem, text) in enumerate(todo, start=1):
        path = OUT / f"{stem}.ogg"
        try:
            audio = render(kokoro, speech, text)
            sf.write(str(path), audio, TARGET_RATE, format="OGG")
            dur = verify(path)
        except Exception as exc:  # noqa: BLE001 — one bad stem must not kill the run
            # Remove the reject so a rerun without --force retries it rather
            # than treating a broken file as done.
            path.unlink(missing_ok=True)
            failed.append((stem, str(exc)))
            print(f"[FAIL {i}/{len(todo)}] {stem}: {exc}", flush=True)
            continue
        written += 1
        print(f"[{i}/{len(todo)}] {stem}.ogg  {dur:.2f}s  {text!r}", flush=True)

    present = [OUT / f"{s}.ogg" for s, _ in plan if (OUT / f"{s}.ogg").exists()]
    durs = sorted(sf.info(str(p)).duration for p in present)
    total = sum(p.stat().st_size for p in present)
    print(f"DONE: {written} written, {len(present)}/{len(plan)} clips present, "
          f"{total / 1024:.0f} KiB", flush=True)
    if durs:
        print(f"duration min/median/max: {durs[0]:.2f}s / "
              f"{statistics.median(durs):.2f}s / {durs[-1]:.2f}s", flush=True)
    if failed:
        print(f"FAILURES ({len(failed)}): {failed}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
