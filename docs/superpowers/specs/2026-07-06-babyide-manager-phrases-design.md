# BabyIDE Manager Phrases — Design

**Date:** 2026-07-06
**Branch:** `feat/babyide-mode`
**Status:** Approved (design); ready to implement

## Summary

Add a set of "corporate manager praising an employee" sayings — delivered in the
existing sunny *praising-a-child* voice — that speak while a kid mashes in
**BabyIDE** mode. It layers the grown-up gag (TPS reports, standups, "great job
buddy!") onto the babyide mode's existing keypress payoff. Reuses the existing
reactive-phrase system end to end; the only genuinely new thing is the audio
content and one generator tweak.

## The sayings (trigger key: `manager`, 12 sayings)

1. "Greeaat job, buddy! Let's circle back on that!"
2. "Who's my little rockstar? You are!"
3. "Yes! Ship it! So proud of you!"
4. "Ooh, look at you moving the needle!"
5. "Don't forget your TPS reports, kiddo!"
6. "Can you demo this at standup? Good job!"
7. "Let's take this one offline, champ!"
8. "Yay! Now go update your Jira ticket!"
9. "Did you sync with the stakeholders? Attaboy!"
10. "Awesome sauce! Let's put a pin in it!"
11. "You're such a good little team player!"
12. "Remember to log your hours, superstar!"

## How it fires (reuse the "fun" cadence)

In BabyIDE mode the existing `fun` phrase trigger already arms on every
keypress-spawn (`director.note_spawn`). At the single phrase-firing site in
`main.py`, when a phrase fires and `display_mode == "babyide"`, remap the trigger
`fun → manager`:

```python
if app_settings.display_mode == "babyide" and trigger == "fun":
    trigger = "manager"
```

This reuses **all** of the phrase machinery — the spawn-counter cadence, the
global `PHRASE_COOLDOWN_S` cooldown, the `PHRASE_CHANCE` flip, the reserved phrase
channel, and the bed-ducking envelope. In Smash mode, `fun` stays `fun`. Two
lines; no change to `phrases.py` or `PhraseDirector`.

`audio.play_phrase` already no-ops silently when a trigger has no clips, so the
app never breaks if the `manager` clips are absent (e.g. before generation, or in
a build that ships without them).

## Components / changes

1. **`tools/phrases.json`** — add a `"manager"` key with the 12 sayings.
2. **`tools/gen-voice-gemini.py`** — phrase mode currently forces one take
   (`takes = 1`, ignoring `--takes`). Extend it to honor `--takes` the same
   **take-outer** way the vocabulary path does, so each saying's takes land in
   different API calls (real delivery variation, not one call reading a line
   three times). Output stays `sounds/voice/<voice>/phrase-manager-<n>.ogg` with a
   flat per-key index (12 sayings × 3 takes → `phrase-manager-1..36.ogg`).
3. **`mashpad/main.py`** — the two-line `fun → manager` remap at the phrase-firing
   site (~line 372).
4. **Generation** — render all six Gemini voices:
   ```
   python tools/gen-voice-gemini.py \
     --voices Achernar Algenib Charon Fenrir Kore Vindemiatrix \
     --phrases tools/phrases.json --takes 3
   ```
   Existing clips are skipped, so only the new `manager` clips are made. Tone is
   the existing kindergarten-teacher / Vocal-Smile prompt (`[laughing]` tag) — the
   praising-a-child delivery; tunable via `--tag`.
5. **Test** — content-guard (`tests/test_phrases.py` or a small new test): assert
   `tools/phrases.json` parses and its `manager` list has ≥10 non-empty strings,
   so an accidental deletion surfaces as a red test, not silence.

## Generation cost / risk

- **Quota:** 12 sayings × 3 takes = 36 items/voice × 6 = **216 clips**, batched at
  `PHRASE_BATCH = 10` → ~4 calls/voice × 6 = **~24 batched calls** of the 100/day
  TTS quota (`GEMINI_VOICE_KEY`). ~3 min at the 7s call spacing.
- **Split-on-silence risk:** the tool renders a batch of items in one call and
  re-splits at the longest silences. Longer manager sentences (vs single words)
  raise the chance of a mis-split. **Mitigation:** generate **one voice first**
  (Kore, ~4 calls), verify all 36 clips exist with sane durations, spot-listen,
  then generate the other five. Same total quota, catches a systemic problem after
  4 calls instead of 24.

## Out of scope

- No new PhraseDirector trigger logic, no menu option (it rides the existing
  `phrases` on/off setting and BabyIDE mode).
- No prompt/tone redesign — the existing phrase prompt already is the
  praising-a-child voice.
- Smash mode is unchanged.

## Testing

- Content-guard test (above), run in the normal `python -m pytest -q` suite.
- Generation is validated by the one-voice-first check (clip count + durations),
  then a full run; the *tone* is the user's ear check on a sample clip.
- Runtime (a phrase actually firing in BabyIDE) is the user's on-device check —
  the pygame kiosk isn't driven headless here.
