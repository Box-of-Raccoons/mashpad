# mashpad voice packs via Gemini TTS (dev machine only — needs GEMINI_API_KEY).
#
# Usage:
#   python gen-voice-gemini.py --voices Charon Fenrir [--takes 3] [--force]
#   python gen-voice-gemini.py --voices Charon --phrases phrases.json [--takes 3]
#
# Renders the full mashpad vocabulary (letters, digits, shapes, image words —
# pulled live from mashpad.gen_voice._vocabulary so it can never drift) in each
# named Gemini prebuilt voice, N takes per word, using the approved
# "director's note" style prompt (bright kindergarten-teacher delivery).
# With --phrases, renders the phrase catalogue from a JSON file instead:
#   {"slowdown": ["Haha, slow down!", ...], ...} → <voice>/phrase-<key>-<n>.ogg
#
# Output: sounds/voice/<voice-lowercase>/<word>-<take>.ogg
#   (silence-trimmed, 5ms anti-click fades, 44100 Hz mono OGG — matches the
#    app mixer rate exactly so nothing resamples at runtime)
#
# Key: read from boxofraccoons-website/.env (sibling checkout, gitignored).
# Requires: pip install numpy soundfile

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import soundfile as sf

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from mashpad.gen_voice import _vocabulary  # noqa: E402

SITE_ENV = REPO.parent / "boxofraccoons-website" / ".env"
MODEL = "gemini-2.5-flash-preview-tts"  # validated by ear against 3.1-preview
TARGET_RATE = 44100
TRIM_DB = -40.0
RETRIES = 4
WORKERS = 3  # TTS preview is ~10 RPM — more workers just churn 429s

# The approved style prompt (Hardy, 2026-07-05). {text} is one word or phrase;
# {tag} is the delivery tag: [enthusiasm] for vocabulary, [laughing] for phrases.
PROMPT = """Read the following transcript based on the director's note.

# Director's note
Style: The "Vocal Smile": The soft palate is raised to keep the tone bright, sunny, and explicitly inviting. Pace: Natural conversational pace.

## Scene:
A kindergarten teacher is teaching words and letters to children

## Transcript:
[{tag}]
{text}"""

TAG = "enthusiasm"  # set from --tag in main()


def tts(text: str, voice: str, key: str) -> tuple[bytes, int]:
    body = {
        "contents": [{"parts": [{"text": PROMPT.format(tag=TAG, text=text)}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(body).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    rate = int(re.search(r"rate=(\d+)", part["mimeType"]).group(1)) if "rate=" in part["mimeType"] else 24000
    return base64.b64decode(part["data"]), rate


def process(pcm: bytes, rate: int) -> np.ndarray:
    """PCM s16le mono -> silence-trimmed, resampled float32 at TARGET_RATE."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    thresh = 10 ** (TRIM_DB / 20)
    loud = np.flatnonzero(np.abs(x) > thresh)
    if len(loud):
        pad = int(rate * 0.03)
        x = x[max(0, loud[0] - pad):min(len(x), loud[-1] + pad)]
    if rate != TARGET_RATE:
        n_out = int(round(len(x) * TARGET_RATE / rate))
        x = np.interp(np.linspace(0, len(x) - 1, n_out), np.arange(len(x)), x).astype(np.float32)
    f = int(TARGET_RATE * 0.005)
    if len(x) > 2 * f:
        x[:f] *= np.linspace(0, 1, f, dtype=np.float32)
        x[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return x


def spoken_form(stem: str, text: str) -> str:
    """Single letters render uppercase in the transcript ('A' reads as the letter name)."""
    if len(text) == 1 and text.isalpha():
        return text.upper()
    return text


def call_with_backoff(text: str, voice: str, key: str):
    """tts() with 429-aware backoff. Raises after RETRIES failures."""
    for attempt in range(RETRIES):
        try:
            return tts(text, voice, key)
        except urllib.error.HTTPError as exc:
            if attempt == RETRIES - 1:
                raise
            # Honor Retry-After when the quota window is saturated.
            wait = int(exc.headers.get("Retry-After", 0) or 0) if exc.code == 429 else 0
            time.sleep(max(wait, 10 * (attempt + 1)))
        except Exception:  # noqa: BLE001 — transient network failure
            if attempt == RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))


def one_clip(job, key):
    voice, stem, text, out = job
    try:
        pcm, rate = call_with_backoff(text, voice, key)
        x = process(pcm, rate)
        sf.write(str(out), x, TARGET_RATE, format="OGG", subtype="VORBIS")
        return (job, None)
    except Exception as exc:  # noqa: BLE001
        return (job, exc)


# ── Batch mode: many words per call, split on silence ─────────────────────────

BATCH_SIZE = 10
SPLIT_DB = -45.0          # below this is "silence" for segmentation
MIN_GAP_S = 0.25          # a silence must be at least this long to split on
MIN_SEG_S = 0.15          # segments shorter than this are noise, not words


def split_on_silence(x: np.ndarray, rate: int) -> list[np.ndarray]:
    """Split audio into voiced segments separated by >= MIN_GAP_S of silence."""
    thresh = 10 ** (SPLIT_DB / 20)
    voiced = np.abs(x) > thresh
    # Close sub-gap holes so intra-word quiet moments don't split a word.
    gap = int(rate * MIN_GAP_S)
    segs, start, last_true = [], None, -gap
    for i in np.flatnonzero(voiced):
        if start is None:
            start = i
        elif i - last_true >= gap:
            segs.append((start, last_true + 1))
            start = i
        last_true = i
    if start is not None:
        segs.append((start, last_true + 1))
    return [x[a:b] for a, b in segs if (b - a) >= rate * MIN_SEG_S]


def one_batch(batch_job, key):
    """One API call for a list of words; returns (batch_job, err)."""
    voice, entries = batch_job  # entries: [(stem, text, out_path), ...]
    transcript = "\n\n".join(text for _, text, _ in entries)
    try:
        pcm, rate = call_with_backoff(transcript, voice, key)
        raw = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        segs = split_on_silence(raw, rate)
        if len(segs) != len(entries):
            raise ValueError(f"expected {len(entries)} segments, got {len(segs)}")
        for (stem, _text, out), seg in zip(entries, segs):
            pcm_seg = (np.clip(seg, -1, 1) * 32767).astype(np.int16).tobytes()
            x = process(pcm_seg, rate)
            sf.write(str(out), x, TARGET_RATE, format="OGG", subtype="VORBIS")
        return (batch_job, None)
    except Exception as exc:  # noqa: BLE001
        return (batch_job, exc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voices", nargs="+", required=True)
    ap.add_argument("--takes", type=int, default=3)
    ap.add_argument("--phrases", help="JSON file {key: [phrase, ...]} — render phrases instead of the vocabulary")
    ap.add_argument("--tag", default=None, help="delivery tag (default: enthusiasm for words, laughing for phrases)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    global TAG
    TAG = args.tag or ("laughing" if args.phrases else "enthusiasm")

    key = re.search(r"GEMINI_API_KEY=(\S+)", SITE_ENV.read_text()).group(1)

    if args.phrases:
        catalogue = json.loads(Path(args.phrases).read_text())
        items = [(f"phrase-{k}-{i + 1}", v)
                 for k, variants in catalogue.items()
                 for i, v in enumerate(variants)]
        takes = 1  # variants replace takes for phrases
    else:
        items = [(stem, spoken_form(stem, text)) for stem, text in _vocabulary()]
        takes = args.takes

    pending = []  # (voice, stem, text, out)
    for voice in args.voices:
        out_dir = REPO / "sounds" / "voice" / voice.lower()
        out_dir.mkdir(parents=True, exist_ok=True)
        for stem, text in items:
            for take in range(1, takes + 1):
                name = f"{stem}-{take}.ogg" if not args.phrases else f"{stem}.ogg"
                out = out_dir / name
                if out.exists() and not args.force:
                    continue
                pending.append((voice, stem, text, out))

    failed = 0
    if args.phrases:
        # Phrases: one per call (their internal punctuation pauses would fool
        # the silence splitter).
        print(f"{len(pending)} phrase clips on {MODEL} (one per call)", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(one_clip, j, key) for j in pending]
            for n, fut in enumerate(as_completed(futures), 1):
                job, err = fut.result()
                if err:
                    failed += 1
                    print(f"  FAIL {job[0]}/{job[3].name}: {err}", flush=True)
                if n % 10 == 0:
                    print(f"  {n}/{len(pending)}", flush=True)
    else:
        # Words: batch BATCH_SIZE words per call, split the audio on silences.
        # 10x fewer calls — the TTS preview model is rate-limited (~10 RPM).
        batches = []
        by_voice: dict[str, list] = {}
        for voice, stem, text, out in pending:
            by_voice.setdefault(voice, []).append((stem, text, out))
        for voice, entries in by_voice.items():
            for i in range(0, len(entries), BATCH_SIZE):
                batches.append((voice, entries[i:i + BATCH_SIZE]))
        print(f"{len(pending)} word clips in {len(batches)} batched calls on {MODEL}", flush=True)
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(one_batch, b, key) for b in batches]
            for n, fut in enumerate(as_completed(futures), 1):
                batch_job, err = fut.result()
                if err:
                    failed += len(batch_job[1])
                    print(f"  FAIL {batch_job[0]} [{batch_job[1][0][0]}..]: {err}", flush=True)
                print(f"  batch {n}/{len(batches)}", flush=True)
    print(f"done: {len(pending) - failed} ok, {failed} failed"
          + (" — rerun to retry failures (existing clips are skipped)" if failed else ""), flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
