# Piano melodies on keypress (MP-1)

*Planning comments copied verbatim from Jira MP-1 (planned 2026-07-05 by Claude +
Hardy). Preserved here so the implementation is auditable against the plan.*

---

## Design plan (1 of 2)

### Goal

Replace the random effect clip ("ding") played on each spawn with piano notes
that step through children's-song melodies. Any allowed spawn (keypress **or**
mouse click — both route through `_spawn` in `main.py`) advances the melody by
one note. When a song finishes, advance to the next song, looping through the
list.

### Decisions (confirmed with Hardy)

- **Mode, not replacement:** new setting `sound_mode: "piano" | "dings"`,
  **default `"piano"`**. Dings stay available behind the toggle.
- **Voices unaffected:** the spoken word still plays on every spawn in both
  modes. Only the effect layer is swapped.
- **Mouse clicks advance the melody** — anything that triggers a "ding" today
  triggers the next note.
- **Song order:** sequential loop through the song list (shuffle deferred).
- **Timbre:** synthesized mallet-style tones (toy piano / xylophone /
  glockenspiel family), NOT plain sine dings. **Winner: xylophone** (see the
  decision note below).

### Where it slots into the code (verified against the repo at commit 303a845)

- The current "ding" is `rng.choice(self._effects)` in `Audio.play_for`
  (`mashpad/audio.py`), played at `config.EFFECT_VOLUME (0.7) × master` on a bed
  channel (channels 1–8; channel 0 is reserved for phrases). The piano note
  replaces exactly that line's behavior when `sound_mode == "piano"`.
- Bed channels are allocated first-idle, **skip when all busy** (`Audio._play`).
  With `MIXER_CHANNELS = 9` and a sustained mash rate of 6 spawns/s (token
  bucket: capacity 8, refill 6/s), and each spawn also playing a voice clip,
  **note clips must decay fast** (≤ ~0.8 s) or notes get dropped under mashing.
  This favors the xylophone/toy-piano timbres over long-ringing glockenspiel.
- A dropped note (all channels busy) still advances the sequencer — an
  occasional silent skip under extreme mashing is acceptable and matches how
  effects behave today.
- Duck envelope: notes play on bed channels, so they automatically duck while a
  reactive phrase speaks (`Audio.update` sets bed-channel volume every frame).
  No new code needed.

### Note range

Generate the diatonic C-major set **G3–C5** (11 notes: G3 A3 B3 C4 D4 E4 F4 G4
A4 B4 C5). The core songs only need C4–C5, but going down to G3 unlocks Old
MacDonald and Frère Jacques for free. Root octave is a one-constant tunable; the
audition demos were rendered at C5 root — **the winning octave shifts this whole
table up 12 semitones** (see decision: C5 root won → generate **G4–C6**).

### Song list (7 songs)

Transcriptions from memory in C major — **must be verified by ear during
implementation**. `,` = octave below, `'` = octave above.

1. **London Bridge Is Falling Down**: G A G F E F G | D E F | E F G | G A G F E F G | D G E C
2. **Twinkle Twinkle Little Star**: C C G G A A G | F F E E D D C | G G F F E E D | G G F F E E D | C C G G A A G | F F E E D D C
3. **Mary Had a Little Lamb**: E D C D E E E | D D D | E G G | E D C D E E E E | D D E D C
4. **Row Row Row Your Boat**: C C C D E | E D E F G | C' C' C' G G G E E E C C C | G F E D C
5. **Hot Cross Buns**: E D C | E D C | C C C C D D D D | E D C
6. **Frère Jacques**: C D E C | C D E C | E F G | E F G | G A G F E C | G A G F E C | C G, C | C G, C
7. **Old MacDonald Had a Farm** (verse): C C C G, A, A, G, | E E D D C | C C C G, A, A, G, | E E D D C

Song data lives in a pure module structured so adding a song = adding one list.

### Timbre synthesis recipes (winner: xylophone)

Additive synthesis: per-partial exponential decay + a short noise-burst strike
transient, peak-normalized to −3 dBFS after summing (same conventions as
`gen_effects.py`).

| Candidate | Partial ratios | Weights | Decay rates (/s) | Duration | Strike click | Detune |
|-----------|----------------|---------|-------------------|----------|--------------|--------|
| toy-piano | 1.0, 2.6, 5.2 | 1.0, 0.45, 0.18 | 5, 9, 13 | 0.8 s | 6 ms @ 0.20 | ±0.4% |
| **xylophone** | 1.0, 3.0, 6.7 | 1.0, 0.40, 0.12 | 9, 16, 22 | 0.5 s | 4 ms @ 0.25 | none |
| glockenspiel | 1.0, 2.756, 5.404 | 1.0, 0.35, 0.12 | 3, 5, 8 | 1.2 s | 2 ms @ 0.12 | none |

---

## Implementation plan (2 of 2)

### Preconditions

- Start a fresh branch off the integration branch (`feature/MP-1-piano-melodies`).
  Never commit to `main`/`develop` directly.
- Winning timbre + root octave: **xylophone at C5 root** (decided 2026-07-05).
- First step: copy the planning comments into `docs/` (this file), commit as the
  branch's first commit.

### Steps (each with its own gate)

1. **`mashpad/gen_notes.py`** — note synthesis script. Follows `gen_effects.py`
   exactly: numpy + stdlib `wave`, no pygame, `--force` flag, −3 dBFS peak
   normalization, 10 ms tail fade, 44100 Hz 16-bit mono. Port `synth()` with the
   xylophone parameters. Output: `sounds/notes/<name>.wav` for the 11 diatonic
   notes **G4–C6** (`g4.wav` … `c6.wav`), the design table shifted +12 semitones.
2. **`mashpad/melodies.py`** — pure module (no pygame) + `tests/test_melodies.py`.
   `SONGS: list[Song]`; a `Song` is a name + a tuple of note names (`"g4"`…`"c6"`
   matching the WAV filenames). `MelodySequencer.next() -> str` returns the next
   note name and advances; end of song → first note of the next song; last song
   wraps to the first. Validate at import/test time that every song note is in
   the generated range.
3. **`mashpad/audio.py`** — load + play notes. `_load()` scans `sounds/notes/`
   into `self._notes: dict[str, Sound]` (eager). New method `play_note(name)`.
   `play_for(spec, rng, voice=None, note=None)` — when `note` is not None, play
   that note instead of the random effect; voice clip half unchanged.
4. **`mashpad/settings.py`** — `sound_mode` field (`"piano"` default, accepted
   `("piano", "dings")`) + tests.
5. **`mashpad/menu.py`** — "Sounds" row (Piano/Dings toggle).
6. **`mashpad/main.py`** — construct `MelodySequencer()`, compute
   `note = sequencer.next() if sound_mode == "piano" else None` at the spawn call
   sites, pass into `play_for`.
7. **Verify melodies by ear.**
8. **Full gate + close.** Record baseline test counts before step 1; re-run at
   the end, report the delta.

### Decision: timbre = xylophone

Hardy picked the **xylophone** candidate (2026-07-05), auditioned at **C5 root**
— so `gen_notes.py` uses the xylophone dict and generates the diatonic set
**G4–C6** (design table shifted +12 semitones:
`g4 a4 b4 c5 d5 e5 f5 g5 a5 b5 c6`). Song data uses the same note names.

### Risks / notes

- **Frozen-build packaging:** `sounds/notes/` ships in the frozen bundle because
  `mashpad.spec` bundles the whole `sounds/` dir — verified, no spec change
  needed.
- **Pi performance:** 11 eager Sounds is negligible (same order as the 8
  effects). Don't lazy-load; effects precedent applies.
- **Settings written by older builds** lack `sound_mode` → `_from_dict` default
  (`"piano"`) applies. That flips existing installs to piano on upgrade —
  intended (it's the headline feature).
