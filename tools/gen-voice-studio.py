# Voice-pack batch runner — 6 voices, per-take-round calls (26 letters / 25
# phrases / 31 words per request). API call mirrors Hardy's AI Studio export
# (2026-07-05): gemini-2.5-pro-preview-tts, streamed audio, and the approved
# audio-profile/director's-note/scene/sample-context preamble with the
# "..."-between-items transcript format. Temperature 1.4 after 2.0 proved
# ~30% compliant; the "..." separator doubles per failed attempt (max 3).
# Raw WAVs are saved before any processing; oggs are cut only when the split
# validates (n-1 longest gaps + cliff margin + per-segment voiced duration),
# so a bad render never poisons a pack. Jobs whose oggs all exist are skipped
# outright — rerunning after a quota 429 only renders what's missing.
# Transcripts: tools/voice-scripts/. Keys: mashpad/.env GEMINI_VOICE_KEY,
# boxofraccoons-website/.env GEMINI_API_KEY (rotates on quota death).

import re
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from google import genai
from google.genai import types

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "tools" / "voice-scripts"
RAW = REPO / "tools" / "raw" / "voicegen"  # tools/raw/ is gitignored
MODEL = "gemini-2.5-pro-preview-tts"
TARGET_RATE = 44100
TRIM_DB = -40.0
SPLIT_DB = -45.0
MIN_GAP_S = 0.12
CALL_SPACING_S = 7.0
VOICES = ["Charon", "Fenrir", "Algenib", "Vindemiatrix", "Achernar", "Kore"]

# Preamble copied verbatim from the AI Studio export that produced the
# validated render — field order, wording, and em-dashes included.
PROMPT = """Read the following transcript based on the audio profile and director's note.

# Audio Profile
Warm and energetic teacher, excited but unhurried, recording clean takes with generous silence between them.

# Director's note
Style: The \"Vocal Smile\": The soft palate is raised to keep the tone bright, sunny, and explicitly inviting. Pace: Natural. Accent: American (Gen).

## Scene:
A sunny kindergarten classroom, quiet and empty after the children have gone home. A warm, energetic teacher sits alone at their desk, recording narration for a children's learning app. Because every clip will be cut apart later, they work slowly and deliberately: they say one item, then come to a complete stop and sit in total silence for a long moment before beginning the next. They never rush and never run two items together. They adore these words — each one is delivered like a small gift. When an item repeats, they imagine they're answering a different child each time, so the melody, emphasis, and energy are noticeably different on every repetition.

## Sample Context:
The red recording light has just come on. The teacher smiles, takes a slow breath, and begins the list. After every single item they stop completely — mouth closed, a two second silent beat, longer than feels natural — then start the next one fresh, with a new and different inflection, as if revealing it to a different child.

## Transcript:
{transcript}"""

WORDS = [str(n) for n in range(10)] + [
    "circle", "square", "triangle", "star", "heart", "diamond", "pentagon", "ring",
    "balloon", "blocks", "book", "bubbles", "draw", "drum", "hello", "hug",
    "love", "peekaboo", "sandwich", "sleep", "water",
]
TRIGGERS = ["hello", "slowdown", "screenfull", "raccoons", "fun"]  # script order


def load_items(*files):
    items = []
    for f in files:
        text = (SCRIPTS / f).read_text(encoding="utf-8")
        items += [ln.strip() for ln in text.splitlines() if ln.strip() and ln.strip() != "..."]
    return items


def chunk_defs():
    letters = load_items("01-letters-round1.txt", "02-letters-round2.txt", "03-letters-round3.txt")
    phrases = load_items("04-phrases-round1.txt", "05-phrases-round2.txt", "06-phrases-round3.txt")
    words = load_items("words-script-ellipsis.txt")
    letter_stems = [f"{ch}-{r}" for r in (1, 2, 3) for ch in "abcdefghijklmnopqrstuvwxyz"]
    phrase_stems = [f"phrase-{t}-{r * 5 + v + 1}" for r in (0, 1, 2) for t in TRIGGERS for v in range(5)]
    word_stems = [f"{w}-{r}" for r in (1, 2, 3) for w in WORDS]
    assert len(letters) == len(letter_stems) == 78
    assert len(phrases) == len(phrase_stems) == 75
    assert len(words) == len(word_stems) == 93
    return [
        ("letters", letters, letter_stems, (0.2, 2.0)),
        ("phrases", phrases, phrase_stems, (0.5, 4.5)),
        ("words", words, word_stems, (0.2, 2.5)),
    ]


TEMPERATURE = 1.4  # pass 1 ran at the AI Studio setting (2.0): 4/18 chunks passed
                   # validation. Hardy OK'd 1.25-1.5 for retries (2026-07-05).


def tts(client, transcript: str, voice: str, temperature: float = None):
    """One streamed TTS call; returns (pcm bytes, rate). Mirrors the export."""
    contents = [types.Content(role="user", parts=[
        types.Part.from_text(text=PROMPT.format(transcript=transcript))])]
    config = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else TEMPERATURE,
        response_modalities=["audio"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice))),
    )
    pcm, rate = b"", 24000
    for chunk in client.models.generate_content_stream(
            model=MODEL, contents=contents, config=config):
        if chunk.candidates is None:
            continue
        for cand in chunk.candidates:
            if cand.content is None or cand.content.parts is None:
                continue
            for part in cand.content.parts:
                if part.inline_data and part.inline_data.data:
                    pcm += part.inline_data.data
                    m = re.search(r"rate=(\d+)", part.inline_data.mime_type or "")
                    if m:
                        rate = int(m.group(1))
    if not pcm:
        raise RuntimeError("no audio in response")
    return pcm, rate


def interior_gaps(x: np.ndarray, rate: int):
    """(start_sample, length_samples) for silence gaps >= MIN_GAP_S between voiced runs."""
    thresh = 10 ** (SPLIT_DB / 20)
    voiced = np.flatnonzero(np.abs(x) > thresh)
    if not len(voiced):
        return [], None
    gaps = []
    min_gap = int(rate * MIN_GAP_S)
    diffs = np.diff(voiced)
    for j in np.flatnonzero(diffs > min_gap):
        gaps.append((voiced[j] + 1, voiced[j + 1] - voiced[j] - 1))
    return gaps, (voiced[0], voiced[-1] + 1)


def split_validate(x: np.ndarray, rate: int, n: int, dur_lo: float, dur_hi: float):
    """Split at the n-1 longest gaps; validate cliff + per-segment voiced durations."""
    gaps, span = interior_gaps(x, rate)
    if span is None:
        raise ValueError("no voiced audio")
    if len(gaps) < n - 1:
        raise ValueError(f"only {len(gaps)} gaps for {n} items")
    by_len = sorted(gaps, key=lambda g: -g[1])
    cliff_hi = by_len[n - 2][1] / rate
    cliff_lo = by_len[n - 1][1] / rate if len(by_len) >= n else 0.0
    cuts = sorted(s + ln // 2 for s, ln in by_len[: n - 1])
    bounds = [span[0]] + cuts + [span[1]]
    segs = [x[bounds[i]:bounds[i + 1]] for i in range(n)]
    thresh = 10 ** (SPLIT_DB / 20)
    voiced_durs = []
    for s in segs:
        v = np.flatnonzero(np.abs(s) > thresh)
        voiced_durs.append((v[-1] - v[0]) / rate if len(v) else 0.0)
    report = (f"boundary gaps >= {cliff_hi:.2f}s, next gap {cliff_lo:.2f}s, "
              f"voiced dur {min(voiced_durs):.2f}-{max(voiced_durs):.2f}s")
    bad = [(i + 1, round(d, 2)) for i, d in enumerate(voiced_durs) if not (dur_lo <= d <= dur_hi)]
    if bad:
        raise ValueError(f"segments outside {dur_lo}-{dur_hi}s: {bad} ({report})")
    if cliff_lo > 0 and cliff_hi - cliff_lo < 0.05:
        raise ValueError(f"ambiguous cliff ({report})")
    return segs, report


def process(seg: np.ndarray, rate: int) -> np.ndarray:
    """Silence-trim, resample to TARGET_RATE, 5ms anti-click fades (generator spec)."""
    thresh = 10 ** (TRIM_DB / 20)
    loud = np.flatnonzero(np.abs(seg) > thresh)
    if len(loud):
        pad = int(rate * 0.03)
        seg = seg[max(0, loud[0] - pad):min(len(seg), loud[-1] + pad)]
    if rate != TARGET_RATE:
        n_out = int(round(len(seg) * TARGET_RATE / rate))
        seg = np.interp(np.linspace(0, len(seg) - 1, n_out), np.arange(len(seg)), seg).astype(np.float32)
    f = int(TARGET_RATE * 0.005)
    if len(seg) > 2 * f:
        seg = seg.copy()
        seg[:f] *= np.linspace(0, 1, f, dtype=np.float32)
        seg[-f:] *= np.linspace(1, 0, f, dtype=np.float32)
    return seg


def main():
    # Key rotation, freshest quota first: GEMINI_VOICE_KEY2 (new project,
    # 2026-07-05 evening), then the website key and the original — both
    # quota-dead today but they reset at midnight PT.
    env = (REPO / ".env").read_text()
    keys = [
        re.search(r"GEMINI_VOICE_KEY2=(\S+)", env).group(1),
        re.search(r"GEMINI_API_KEY=(\S+)",
                  Path(r"C:\Users\hardy\code\boxofraccoons-website\.env").read_text()).group(1),
        re.search(r"GEMINI_VOICE_KEY=(\S+)", env).group(1),
    ]
    clients = [genai.Client(api_key=k) for k in keys]
    key_idx = 0
    RAW.mkdir(parents=True, exist_ok=True)
    # Round-level jobs (pass 3+): one call per take-round — 26/25/31 items.
    # A whole-chunk raw that already validated in an earlier pass still covers
    # its chunk; otherwise the chunk is (re)built from three per-round renders.
    jobs = []
    for v in VOICES:
        for cname, items, stems, rng in chunk_defs():
            whole = RAW / f"{v.lower()}-{cname}.wav"
            if whole.exists():
                jobs.append((v, (cname, items, stems, rng)))
                continue
            per_round = len(items) // 3
            for r in range(3):
                sl = slice(r * per_round, (r + 1) * per_round)
                jobs.append((v, (f"{cname}-r{r + 1}", items[sl], stems[sl], rng)))
    print(f"{len(jobs)} jobs planned on {MODEL}", flush=True)
    ok, failed = 0, []
    for voice, (cname, items, stems, (lo, hi)) in jobs:
        raw_path = RAW / f"{voice.lower()}-{cname}.wav"
        label = f"{voice}/{cname}"
        # A job whose oggs all exist already passed validation in a prior pass:
        # skip it outright so resumes never burn quota re-rendering good rounds.
        pack_dir = REPO / "sounds" / "voice" / voice.lower()
        if all((pack_dir / f"{s}.ogg").exists() for s in stems):
            ok += 1
            print(f"[done] {label}: all {len(stems)} oggs present", flush=True)
            continue
        if raw_path.exists():
            print(f"[skip-api] {label}: raw exists", flush=True)
        else:
            # Escalate pause cues with each failed attempt: one extra "..."
            # line between items per quarantined take of this job (max 3).
            n_bad = len(list(RAW.glob(f"{raw_path.stem}.bad*.wav")))
            sep = "\n" + "...\n" * min(1 + n_bad, 3)
            if n_bad:
                print(f"[escalate] {label}: {min(1 + n_bad, 3)}x '...' separator", flush=True)
            quota_dead = False
            transient_retries = 0
            while True:
                try:
                    time.sleep(CALL_SPACING_S)
                    t0 = time.time()
                    pcm, rate = tts(clients[key_idx], sep.join(items), voice)
                    sf.write(str(raw_path), np.frombuffer(pcm, dtype=np.int16), rate)
                    print(f"[render] {label}: {len(pcm) / 2 / rate:.0f}s audio in "
                          f"{time.time() - t0:.0f}s", flush=True)
                    break
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    print(f"[FAIL] {label}: {msg[:300]}", flush=True)
                    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                        if key_idx + 1 < len(clients):
                            key_idx += 1
                            print(f"[key-switch] quota dead, rotating to key {key_idx + 1}",
                                  flush=True)
                            continue
                        quota_dead = True
                        break
                    if transient_retries < 1 and (
                            "500" in msg or "INTERNAL" in msg or "no audio" in msg):
                        transient_retries += 1
                        time.sleep(30)
                        continue
                    break
            if quota_dead:
                failed.append((label, "quota"))
                print("QUOTA EXHAUSTED - stopping run; rerun to resume (raws are kept)", flush=True)
                break
            if not raw_path.exists():
                failed.append((label, "render failed"))
                continue
        try:
            x, rate = sf.read(str(raw_path), dtype="float32")
            segs, report = split_validate(x, rate, len(stems), lo, hi)
            out_dir = REPO / "sounds" / "voice" / voice.lower()
            out_dir.mkdir(parents=True, exist_ok=True)
            for stem, seg in zip(stems, segs):
                sf.write(str(out_dir / f"{stem}.ogg"), process(seg, rate), TARGET_RATE,
                         format="OGG", subtype="VORBIS")
            ok += 1
            print(f"[cut] {label}: {len(stems)} oggs ({report})", flush=True)
        except ValueError as exc:
            # Quarantine the bad raw so the next pass re-renders this chunk.
            k = 1
            while (bad := raw_path.with_name(f"{raw_path.stem}.bad{k}.wav")).exists():
                k += 1
            raw_path.rename(bad)
            print(f"[SPLIT-FAIL] {label}: {exc} - raw quarantined to {bad.name}", flush=True)
            failed.append((label, f"split: {exc}"))
    print(f"DONE: {ok}/{len(jobs)} chunks cut; failures: {failed if failed else 'none'}", flush=True)


if __name__ == "__main__":
    main()
