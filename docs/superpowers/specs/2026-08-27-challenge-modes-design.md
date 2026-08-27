# Challenge Modes: Design

**Date:** 2026-08-27
**Status:** Approved (design); pending implementation plan

## Summary

Five new play modes that turn Mashpad from pure stimulus/response into
goal-directed play, without ever taking the smashing away.

An **announcer asks for something** ("Find the letter B", "Can you spell BOOK",
"What is three plus two"), the screen shows the ask, and the child hunts for the
answer on the keyboard. Every keypress still spawns its glyph and plays its
sound exactly as it does today. What is added is a target, a much bigger
celebration when the target is found, and a hint ladder that guarantees the
round always ends in a win.

The five challenges:

1. **Find the letter** (A-Z)
2. **Find the number** (0-9)
3. **Spell a word**, guided
4. **Spell a word**, advanced (a difficulty toggle on 3, not a separate mode)
5. **Addition and subtraction with counting blocks**, in two tiers

## Who this is for

A toddler around two to three years old who recognizes some letters and cannot
read. Every design decision below follows from that:

- Wrong presses are never punished and never go unrewarded.
- No round can be failed, stalled, or abandoned.
- The correct answer is always the most visually salient thing on screen.
- Instruction is carried by color, motion, and voice, never by text.

Modes 2 and 5 are ahead of that age. They are specified and built now because
the same box should still be interesting in three years, but they are not
expected to land with the current player. Their loops cannot be validated
against a real user yet, and that is an accepted risk.

## Goals

- Add a `Challenge` setting orthogonal to `Display`, so a challenge can run over
  the existing smash renderer without a second copy of it.
- Keep the toddler payoff on every keypress: glyph, bounce, tone, spoken key,
  raccoons.
- Put all challenge logic in a pure module with no pygame imports, so the whole
  feature is testable without an audio device or a display.
- Ship code that runs before any new voice recording exists.

## Non-goals

- Scoring, streaks, stars, progress tracking, or any persistent record of
  performance.
- Any failure, timeout, or "wrong, try again" state.
- On-screen keyboard rendering or key-location hints.
- Reading instruction. This teaches letter and number recognition, not phonics.
- New spelling words outside the vocabulary already recorded in every voice pack.

## Architecture: a challenge layer, not new display modes

Every one of the five is *smash with a goal on top*. The child still presses any
key and still gets a glyph and a ding. `display_mode` is a different axis: it
picks a whole renderer (giant glyphs vs. the BabyIDE code panel). Folding these
in as five more `display_mode` values would grow the `KEYDOWN` branch in
`main.py`, the draw path, the phrase director and the mouse handling all at
once, which is the swamp this design exists to avoid.

So: a new `challenge` setting sits **beside** `display_mode`, and a new pure
module owns the round.

### `mashpad/challenge.py` (pure logic, no pygame)

Joins `items` / `keymap` / `ratelimit` / `trail` on the purity test and carries
the test suite for this feature.

`ChallengeDirector` owns exactly one round at a time:

```
ASKING --speak ask--> HUNTING --correct key--> WON --beat--> next round
                         |
                         +-- wrong key: nothing but the normal smash
```

It exposes:

- `start_round(now)`: draw the next target from the bag, emit `ASK`.
- `on_key(char, now)`: judge the press. Returns one of `IGNORED`, `WRONG`,
  `ADVANCE` (a correct letter in a multi-slot answer), `CORRECT`.
- `poll(now)`: drive the hint ladder and the post-win beat. Returns an event or
  `None`.
- `view()`: a plain data description of what to draw (target glyph, slot row,
  block groups, which slot is hot). `main.py` renders it; the director never
  touches pygame.

Events are data, not calls: `ASK`, `HINT(level)`, `ADVANCE`, `WON`, `GIMME`. The
caller decides what audio and animation each one produces.

### The hint ladder

Escalation triggers on **wrong presses OR elapsed time, whichever comes first**.
Time alone is wrong in both directions: a happily mashing toddler does not need
the announcer barging in every six seconds, and a toddler who has wandered off
does not need silence. This mirrors how `PhraseDirector` already blends spawn
counts with cooldowns.

| Step | Fires after | Utterance | Visual |
|---|---|---|---|
| 0 | immediately | "Find the letter... B!" | ghost B draws in |
| 1 | 6 presses or 8s | "Can you find B?" | ghost pulses |
| 2 | 14 presses or 18s | "B! B for balloon!" | matching sticker pops beside it |
| 3 | 24 presses or 30s | "There it is! B!" | **any key now counts** |

The table above is the find-the-letter ladder. Each challenge supplies its
own four utterances and its own step-2 visual; the thresholds and the
press-or-time rule are shared.

Step 3 is load-bearing. There is no state in which the child can be stuck, which
is also why the letter pool can safely be all 26 rather than a grown-up-curated
subset.

Counters and timers reset on every correct answer. All four thresholds are
config constants.

### Target selection

A shuffled bag, not independent random draws, so the same letter cannot come up
three times running. The bag reshuffles when empty, with a guard against the
last item of one bag being the first of the next.

## The five challenges

### 1. Find the letter

Pool of all 26. The target renders as a large dim outline glyph centered on
screen, honoring the existing `letter_case` setting. Normal smash glyphs
continue to spawn around it at reduced size (see Rendering). A correct press
floods the outline with color, fires confetti and a raccoon pop, and plays a
celebration line.

Hint step 2 uses the sticker art where the letter has one (B for balloon, W for
water) and falls back to a plain re-ask where it does not.

### 2. Find the number

Identical machinery, pool 0-9. Digit clips already exist in every voice pack, so
this costs no new audio.

### 3. Spell a word, guided

A row of ghost letters with the sticker art above it. Completed letters sit in
full color; the next letter glows and pulses and is the only bright thing in the
row. Strict left to right: a letter that appears later in the word but is not
the current one behaves like any other wrong press. Letting a non-glowing letter
count would contradict the exact signal the glow exists to send.

Word pool is limited to what is already spoken in every pack and short enough
for this age: BOOK, STAR, DRUM, RING, HUG, LOVE.

### 4. Spell a word, advanced

The same row with blank underscored slots instead of ghost letters, so nothing
but the announcer and the picture tells you the letter. This is the
`answer_style` setting, not a separate challenge, and the same setting governs
two-digit math answers.

Longer already-recorded words (WATER, HEART, CIRCLE, SQUARE, BALLOON, BUBBLES)
belong to this tier.

### 5. Addition and subtraction with counting blocks

Two tiers that differ in **input**, not only in difficulty.

**Totals 2-9.** The answer is a single keypress. Two groups of flat colored
squares sit side by side with a `+` between them. Each group takes its own color
from `PALETTE`, chosen far enough apart in hue to be unmistakable (no blue
beside azure), and **the numeral under each group is drawn in that group's
color**. That color pairing is the teaching mechanic: a child who cannot yet
read "3" as a symbol can still see that the blue word belongs to the blue pile.
The mode teaches numeral recognition passively while it teaches counting.

The hint ladder does the counting aloud, which is the actual skill at this age
(one-to-one correspondence): step 1 counts the first group with each block
popping in turn, step 2 counts the second group, step 3 counts the whole line to
the total and lights the answer.

**Totals 0-20.** The answer needs two digits, a genuinely different input
problem. The answer becomes a row of slots and the child presses 1 then 3, using
the exact widget from challenges 3 and 4. No new input machinery, and
`answer_style` applies there too (ghost digits vs. blank slots).

**Subtraction** shows one colored group with the subtracted blocks draining to
grey and drifting off, rather than a second color appearing. The numerals read
`5 - 2` in the same color scheme.

No new art: blocks are flat squares, and Mashpad already draws squares from
`PALETTE`.

## Rendering

`main.py` keeps one smash path and asks `ChallengeDirector.view()` what to
overlay. Two adjustments while a challenge is active:

- Normal (non-target) spawns render at about 70% of `ITEM_SIZE_PX`, so a
  screenful of glyphs cannot bury the target. A config constant.
- The target overlay draws **under** the flying items but over the background,
  so it never blocks the smash payoff, and it is redrawn every frame from
  `view()` rather than held as mutable render state.

## Audio: an utterance queue

`play_for` and `play_phrase` are one-shots today. "Find the letter... B" is two
clips with a gap, and "what is two plus three" is four. `Audio` gains:

- `speak(clips, gaps)`: play a sequence on the reserved `PHRASE_CHANNEL`, duck
  the bed through the existing `duck.py` envelope, and expose a cancel for when
  a new round starts mid-sentence.

## Voice assets

Two tiers, so no code is ever blocked on an API key.

**Tier 1, placeholders.** One complete `sounds/voice/_placeholder/` pack
generated locally by Kokoro via `seniordev-voice`'s `speech.py`: carriers,
letters, digits, words, everything. It appears in the grown-up menu as its own
voice. Generating only the carriers into the six Gemini packs was rejected: a
Kokoro "find the letter" followed by a Gemini "B" sounds like two people
finishing each other's sentence, which is a poor test of the loop. A
self-contained placeholder directory also makes "what still needs real audio" a
directory listing rather than a memory.

Kokoro emits 24kHz and the mixer runs at 44.1k, so placeholders resample on the
way out. Never ship 24k.

**Tier 2, the Gemini round.** Runs once, only after the loop has been validated
on the Pi. Roughly 19 new stems per pack, about 340 clips across six voices at
three takes, using the existing `tools/gen-voice-studio.py` recipe:

- Carriers: "find the letter", "find the number", "can you spell", "for",
  "what is", "plus", "minus", "makes", "how many"
- Numbers ten through twenty

The placeholder pack retires when this lands.

## Settings and menu

Three new fields on `Settings`, each validated field-wise like the existing ones
so one bad value never discards its valid siblings:

- `challenge`: `none` | `letter` | `number` | `spell` | `math` (default `none`)
- `answer_style`: `guided` | `advanced` (default `guided`)
- `math_range`: `2-9` | `0-20` (default `2-9`)

Three new rows in the grown-up menu beside `Display`.

## Constraints that fall out of the existing code

- **A correct press must bypass the rate limiter.** `bucket.try_take` gates
  every spawn today, and a mashing toddler empties that bucket. If the child
  finally finds the B and the bucket eats it, the mode is broken. Correct
  answers take a reserved path.
- **Challenge speech outranks reactive phrases.** Both want `PHRASE_CHANNEL`.
  While an utterance is queued or playing, `PhraseDirector.poll` is suppressed,
  otherwise "You're doing amazing!" talks over "Find the letter B".
- **Lazy audio loading stays lazy.** This roughly doubles the clip count per
  pack, and eager decoding was already a boot-time and memory problem on the Pi.
- **Challenge is ignored in BabyIDE display mode.** The two are orthogonal in
  the settings but BabyIDE has no glyph field to overlay, so a challenge simply
  does not run there.

## Testing (ships with the feature)

`challenge.py` is pure, so it carries the suite:

- Ladder escalation on press count and on elapsed time, each independently.
- Step 3 gimme: any key wins, and the round always terminates.
- Shuffled bag: no immediate repeat, including across a reshuffle.
- Strict left-to-right spelling, including a later-in-word letter counting as a
  miss.
- Two-digit math answer entry, including a wrong first digit.
- Round cancellation mid-utterance.

`Audio.speak` gets tests in the style of the existing fallback tests, with no
device required.

## Slices (branches off `develop`; item 4 is a gate, not a branch)

1. `feat/challenge-core`: settings, menu rows, `ChallengeDirector`, tests
2. `feat/challenge-audio`: utterance queue, duck integration, Kokoro placeholder
   pack generator
3. `feat/challenge-letter`: find-the-letter and find-the-number
4. **Gate:** play it on the Pi and decide whether the loop holds her attention.
   Everything after this assumes a yes, and the Gemini round assumes it hard.
5. `feat/challenge-spell`: the slot row, guided and advanced
6. `feat/challenge-math`: counting blocks, both tiers
7. `feat/challenge-voice`: the Gemini carrier round, placeholder pack retires

Version bumps to 1.2.0 only at release.

## Open knobs (small, reversible defaults)

- Hint ladder thresholds (6/14/24 presses, 8/18/30 seconds).
- Non-target spawn scale during a challenge (70%).
- Post-win beat before the next ask.
- Whether an out-of-order letter that is in the word should light up anyway
  (currently no).

## Risks

- **The loop may simply not hold a two-year-old.** This is why slice 4 is a hard
  gate before any recording spend.
- **Modes 2 and 5 cannot be validated against the current player.** Accepted
  deliberately.
- **Six short spelling words is a thin pool.** Expanding it costs a Gemini
  round, so the vocabulary limit is a real constraint, not an oversight.
- **The announcer may feel naggy.** The press-or-time ladder is the mitigation,
  and every threshold is tunable against real play on the Pi.
