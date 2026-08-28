# Challenge slice 7: the carrier recording round

**Date:** 2026-08-28
**Spec:** `docs/superpowers/specs/2026-08-27-challenge-modes-design.md` (slice 7)
**Status:** written ahead of execution; **blocked on the slice-4 playtest gate**
**Branch when it runs:** `feat/challenge-voice` off `develop`

Slices 1 through 6 are merged and pushed. Every challenge mode works today, but
the announcer speaks in a robot voice: the phrases that carry an ask ("find the
letter", "what is", "plus") exist only in a locally generated Kokoro pack at
`sounds/voice/_placeholder/`. This slice records them properly into all six
shipped voices and retires that pack.

## Stakes

**Low-blast in code, high-friction in audio.** The code changes here are small
and reversible. The recording is neither: it costs API quota, it runs against a
preview model, and redoing it because the wording changed costs the whole round
again. Everything expensive in this slice is downstream of one decision, which
is *what the announcer says*.

So the ordering rule for this slice is: **freeze the words before spending any
quota.** Every other risk is recoverable.

## The gate this is blocked on

Slice 4 is a playtest on the Pi, not a branch. It is still open. Some of what it
returns changes this plan and some does not, and the difference matters because
only one kind blocks recording:

**Does not block. Tune afterwards, free.**

- Ladder thresholds (`CHALLENGE_LADDER`, currently 4 presses/10s, 8/25, 45s) and
  `CHALLENGE_PRESS_SPACING_S` (0.7s). Pure config.
- `CHALLENGE_ITEM_SCALE`, `CHALLENGE_MAX_ITEMS`, keep-out margins, the counting
  cadence, the post-win beat. All config.
- Which spelling words are in the pool, as long as they stay inside the twelve
  already recorded in every pack.

**Blocks. Settle before recording.**

- **The wording of every ask and hint.** "Find the letter B" versus "Where is
  the B?" versus anything else. Changing this after the round means recording
  again.
- **Whether the hint ladder needs a carrier it does not have today.** Adding
  "try again" or "nearly" later is a second round.
- **Whether the loop works at all.** If the playtest says the challenge layer
  does not hold her, do not record. Six voices of carriers for a mode nobody
  plays is the most expensive possible way to be wrong.

**One question the playtest cannot cleanly answer:** whether a warm human-ish
voice would rescue a loop that the robot placeholder failed to sell. The
placeholder is deliberately ugly. If she is engaged but visibly indifferent to
the announcer, that is worth weighing before concluding the loop is dead.

## What is actually missing (derived, not remembered)

Enumerated from the code on 2026-08-28 by walking every challenge kind, every
target, and every ladder level through `main._challenge_stems`, then diffing
against each pack on disk. The app can ask for **74 distinct stems**. Of those,
**20 are missing from all six shipped packs**, uniformly:

```
can-you-spell   find-the-letter   find-the-number   for
what-is         plus              minus             makes      how-many
ten  eleven  twelve  thirteen  fourteen  fifteen
sixteen  seventeen  eighteen  nineteen  twenty
```

The other 54 (letters, digits 0 to 9, shape and sticker words) are already in
every pack from the original round.

**20 stems x 3 takes x 6 voices = 360 clips.** The spec estimated 19 stems and
about 340 clips, so it was close but not exact. Do not hand-type this list at
execution time; re-derive it, because the code may have moved. Step 0 adds a
tool that prints it.

## Assumptions, marked

- **A1 (confirmed, 2026-08-28):** all 20 stems are missing from all six packs.
  Verified by listing `sounds/voice/<pack>/` and diffing against the enumerated
  stem set.
- **A2 (confirmed):** hyphenated stems load correctly. `Audio._load_pack` splits
  only a trailing `-<digits>`, so `find-the-letter-2.ogg` resolves to the word
  `find-the-letter`, take 2. The placeholder pack already proves this at
  runtime.
- **A3 (confirmed, 2026-08-28):** **there are no Gemini API keys on the Mac.**
  `mashpad/.env` does not exist here, `~/code/.env` holds no `GEMINI_*` key, and
  `boxofraccoons-website` has no `.env` on this machine. `gen-voice-studio.py`
  also hardcodes a Windows path, `C:\Users\hardy\code\boxofraccoons-website\.env`,
  and reads it eagerly, so it crashes on import of its key list here.
- **A4 (inferred):** the keys still exist on the Windows box, where the original
  round ran. Confirm by opening `C:\Users\hardy\code\mashpad\.env` before
  planning a run there.
- **A5 (inferred, and the one most likely to be wrong):** the model
  `gemini-2.5-pro-preview-tts` still exists and still accepts the same request
  shape. It was a preview model when the first round ran on 2026-07-05. Check
  this first; a renamed or retired preview model changes the whole step.
- **A6 (unknown):** cost. The first round ran on free-tier quota across rotating
  keys and hit 429s repeatedly. Check current pricing before running; 18 calls
  is a much smaller round than the original 54, so it may fit in one sitting.

## Decided forks

- **Record on the machine that has the keys.** Almost certainly Windows. The
  outputs are ogg files committed to the repo, so where they are generated does
  not matter to the app.
- **Three takes, matching everything else in the packs.** The variety rule that
  applies to letters applies to carriers: a child hears "find the letter" many
  times a session, and one fixed reading gets old faster than a letter clip
  does.
- **Keep the underscore-exclusion rule in `voiceselect.py` after the placeholder
  is gone.** It is a cheap general guard, its tests use synthetic pack names,
  and it costs nothing to leave in place.
- **Keep `tools/gen-voice-kokoro.py`.** It is how a placeholder gets rebuilt if
  a future slice ever needs a carrier that has not been recorded yet.

## Steps

Each step has a gate that must pass before the next begins.

### Step 0. Pre-flight, before any API call

1. Confirm A5: does `gemini-2.5-pro-preview-tts` still exist and answer? One
   throwaway call with a two-word transcript.
2. Confirm A4: keys present on the recording machine.
3. Add `tools/list-challenge-stems.py`, which prints the stems the app can ask
   for and which packs lack them. The recording script is generated from this,
   never typed.
4. **Freeze the wording** against the playtest result and write it down here.

**Gate:** the tool prints exactly 20 missing stems, the model answers, and the
wording is settled in writing.

### Step 1. Write the carrier script and teach the runner about it

`tools/gen-voice-studio.py` renders one call per take-round and cuts the result
at the longest silences. Adding carriers means:

1. A script file in `tools/voice-scripts/` in the existing ellipsis format, one
   item per line separated by `...` lines, ordered to match the stem list.
2. A `carriers` entry in `chunk_defs()` with its own length assertion, mirroring
   how `letters`, `phrases` and `words` are defined.
3. Duration bounds for `split_validate`. The words chunk uses `(0.2, 2.5)`
   seconds. Carriers span "for" at roughly 0.3s to "find the letter" at roughly
   1.1s, so `(0.2, 2.5)` should hold, but confirm against the first render
   rather than assuming.
4. **Fix the key loading so it does not crash off Windows** (A3). The eager read
   of a hardcoded absolute path should become a search over candidate paths that
   skips what is not there.

**Gate:** `chunk_defs()` asserts pass and the job list prints 18 jobs (6 voices
x 3 rounds) without making a call.

### Step 2. One voice first

Render and cut a single voice, then listen to all 20 of its carriers before
spending quota on the other five.

Listen for two things specifically:

- **Does it split cleanly?** 20 items in one call needs 19 unambiguous gaps.
  Short items are the risk. If the cliff is ambiguous the runner already
  quarantines the raw and escalates the pause cue, but if that keeps failing,
  split the carriers into two calls of 10 rather than fighting the prompt.
- **Does it match the letters already in that pack?** This is the real
  acceptance test and the reason the placeholder exists at all. Play "find the
  letter" immediately followed by that pack's own "b" clip. They were recorded
  months apart; the prebuilt voice is fixed, but pace and level can drift, and a
  carrier that does not match its own letters recreates the exact
  two-people-talking problem the placeholder was built to avoid.

**Gate:** one pack has 20 carriers that cut cleanly and sound like the same
person as its existing letters.

### Step 3. The remaining five voices

Run the rest. The runner skips jobs whose oggs already exist, so a quota 429 is
resumable: rerun and it renders only what is missing.

**Gate:** `tools/list-challenge-stems.py` reports zero missing stems across all
six packs. 360 new files.

### Step 4. Listen to whole asks, not clips

Add a small script that speaks complete utterances end to end in a chosen voice:
"find the letter... B", "can you spell... book", "what is... three... plus...
two", "makes... seventeen". Isolated stems can each sound fine while the
assembled sentence does not, because `UTTERANCE_GAP_S` (0.35s) sits between
every clip.

**Gate:** each of the four sentence shapes sounds like one person saying one
sentence, in at least two different voices.

### Step 5. Retire the placeholder

Deliberately a **separate commit from step 3**, so the new audio can be reverted
without losing the fallback and vice versa.

1. Delete `sounds/voice/_placeholder/` (114 files, 1.6MB).
2. `tests/test_challenge_wiring.py::test_every_counting_stem_exists_in_the_placeholder_pack`
   asserts against the placeholder pack by name. **This is an existing assertion
   that must change**: it becomes a check that every shipped pack can say every
   stem, which is a stronger test and the natural acceptance gate for this
   slice. Flag it when it happens rather than editing it quietly.
3. Add that generalized test: every stem in the enumeration exists in every
   shipped pack, with three takes.
4. Update the docstring on `Audio.challenge_voice`, which currently says "only
   the generated placeholder qualifies". The function itself needs no change:
   once every pack has the carriers, the preferred voice always wins and the
   rule retires itself exactly as designed.
5. README: rewrite the "Which voice speaks an ask" section, which currently
   documents the placeholder as the current state.
6. Design spec: mark slice 7 done in the slices list.

**Gate:** full suite green against the recorded baseline, and grep finds no
stale `_placeholder` reference outside `gen-voice-kokoro.py` and the design
spec's history.

### Step 6. Hear it on the Pi

The only acceptance that counts. Start a challenge round on the Pi with a
specific voice selected, not Random, and confirm the ask and the smash echo are
the same person.

**Gate:** Hardy hears one voice, in a real round, on the device.

## Risks

- **The model is a preview and may be gone.** A5. Check first, before writing a
  script file.
- **Split validation on 20 short items.** More items in one call means more
  chances for two gaps to be indistinguishable. Mitigations already in the
  runner: escalating "..." separators, raw quarantine, resume. Fallback: two
  calls of 10.
- **Timbre drift between recording sessions.** The whole justification for a
  self-contained placeholder pack was that a Kokoro carrier plus a Gemini letter
  sounds like two people finishing each other's sentence. A Gemini carrier
  recorded a month later against a preview model that has since been retrained
  could do the same thing more subtly. Step 2 exists to catch this on one voice
  before it costs six.
- **Quota.** The original round needed key rotation across projects and did not
  finish in one sitting. This round is a third the size.
- **Doing this before the loop is validated.** The largest risk in the slice,
  and the reason it is gated. Recording is the point of no return on spend.

## Rollback

Everything is in git and nothing here is deployed.

- Bad audio: `git checkout -- sounds/voice/` before committing, or revert the
  add-clips commit after.
- Placeholder deleted too early: revert the retire commit; the pack comes back.
- Keep the two commits separate so either can be undone without the other.
