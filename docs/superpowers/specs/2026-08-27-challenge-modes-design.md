# Challenge Modes: Design

**Date:** 2026-08-27
**Status:** Approved (design); revised after an adversarial review pass; pending
implementation plan

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
- `on_key(char, now)`: judge the press. Returns one of `IGNORED`, `MISS`,
  `ADVANCE` (a correct letter or digit in a multi-slot answer), `CORRECT`.
- `poll(now)`: drive the hint ladder and the post-win beat. Returns an event or
  `None`.
- `pause(now)` / `resume(now)`: stop and restart the round clock (see Pausing).
- `view()`: a plain data description of what to draw (target glyph, slot row,
  block groups, which slot is hot). `main.py` renders it; the director never
  touches pygame.

Events are data, not calls: `ASK`, `HINT(level)`, `ADVANCE`, `WON`, `GIMME`. The
caller decides what audio and animation each one produces.

### The hint ladder

**A naive press count does not work here, and this was the single biggest defect
found in review.** `config.py:43-46` sets `BUCKET_CAPACITY = 8` and
`BUCKET_REFILL_PER_S = 6.0`, and `config.py:136-139` treats 6 rate-limiter drops
inside 3 seconds as ordinary mashing worth a "slow down!" phrase. So a happily
mashing toddler produces more than six presses per second. A plain
"escalate after N presses OR M seconds, whichever comes first" ladder would
reach its final any-key step in roughly four seconds of normal play, every
round, forever. The mode would teach that mashing wins, which is the exact
opposite of its purpose.

Two rules fix the trigger shape:

- **A press counts toward escalation only if it lands at least
  `LADDER_PRESS_SPACING_S` (default 0.7s) after the last counted press.** Bursts
  count once. This measures deliberate attempts rather than mash rate.
- **Each step requires BOTH its counted-press floor AND its time floor.** The
  two arms are an AND, not an OR, so neither a fast masher nor a still child can
  outrun the ladder.

| Step | Requires (both) | Utterance | Visual |
|---|---|---|---|
| 0 | immediately | "Find the letter... B!" | ghost B draws in |
| 1 | 4 counted presses and 10s | "Can you find B?" | ghost pulses |
| 2 | 8 counted presses and 25s | "B! B for balloon!" | sticker pops beside it |
| 3 | 45s (time only) | "There it is! B!" | **any key now counts** |

Step 3 is time-only on purpose: the gimme exists to rescue a stuck child, and a
child who is not pressing at all is exactly the one who needs it. It is
load-bearing in a second way too, because it is what makes an all-26 letter pool
safe rather than needing a grown-up-curated subset.

The table above is the find-the-letter ladder. Each challenge supplies its own
four utterances and its own step-2 visual; the thresholds, the spacing rule and
the AND rule are shared.

### What counts as "a press"

Left undefined, this decision gets made four different ways by accident. It is:

- **Any baby-input event**: a `KEYDOWN` or a mouse click, since clicks spawn
  items through the same path (`main.py:352-365`).
- **Including presses the rate limiter dropped.** The child pressed the key; the
  bucket's opinion is irrelevant to whether they are trying.
- **Including non-alphanumeric keys.** `_char_for_event` returns `None` for
  space, enter and arrows (`main.py:55-67`), but space is a toddler's
  most-mashed key, and at step 3 it wins like anything else.
- **Subject to the spacing rule above** before it counts toward escalation.

**An `ADVANCE` resets the ladder to step 0**, so each letter of a word gets a
full fresh ladder. Without this rule a four-letter word inherits an
already-escalated ladder and collapses into gimmes.

### Target selection

A shuffled bag, not independent random draws, so the same letter cannot come up
three times running. The bag reshuffles when empty, with a guard against the
last item of one bag being the first of the next.

### Pausing

The round clock stops whenever the child cannot act on it:

- **While the grown-up menu is open** (`main.py:256-265` swallows all events but
  `now` keeps advancing). Otherwise a 40-second options visit silently escalates
  the round to a gimme and the child's next press celebrates nothing.
- **While the splash is visible.** The first `ASK` waits for splash dismissal,
  which also keeps it from colliding with the startup `hello` phrase. A new
  phrase interrupts the playing one on `PHRASE_CHANNEL` (`audio.py:167-176`), so
  an un-gated first ask would cut `hello` off mid-word.
- **After `CHALLENGE_IDLE_S` with no input**, the round parks: no further hint
  utterances fire, and the current step re-announces on the next press. A Pi
  kiosk idling in an empty room must not have an announcer nagging it, and a
  child returning after twenty minutes must not walk into a context-free
  instant win.

## The five challenges

### 1. Find the letter

Pool of all 26. The target renders as a large dim outline glyph centered on
screen. **The target is always uppercase, regardless of the `letter_case`
setting.** Physical keycaps are uppercase, and a lowercase ghost "b" is both
unmatched to the keyboard and easily confused with "d". `letter_case` continues
to govern the echoed glyphs, where it belongs.

A correct press floods the outline with color, fires confetti and a raccoon pop,
and plays a celebration line. **A correct press does not additionally spawn a
random-position glyph**: the flood is the payoff, and two Bs on screen muddies
which one was the answer.

Hint step 2 uses the sticker art where the letter has one and falls back to a
plain re-ask where it does not. **This is the exception, not the rule:**
`assets/images/` holds 13 stickers covering initial letters b, d, h, l, p, s and
w only, so 19 of 26 letters take the fallback. Expanding that coverage is an art
task, not a code task, and is out of scope here.

### 2. Find the number

Identical machinery, pool 0-9. Digit clips already exist in every voice pack, so
this costs no new audio.

### 3. Spell a word, guided

A row of ghost letters with the word's art above it. Completed letters sit in
full color; the next letter glows and pulses and is the only bright thing in the
row. Strict left to right: a letter that appears later in the word but is not
the current one is a `MISS` and behaves like any other wrong press. Letting a
non-glowing letter count would contradict the exact signal the glow exists to
send.

**Double letters need an unmistakable advance.** After the first O in BOOK the
glow moves to an adjacent, identical O, which to a toddler reads as "nothing
happened". The completed letter must visibly land (flood, settle, then the next
slot lights) rather than the glow simply sliding sideways.

Word pool is limited to what is already spoken in every pack and short enough
for this age: BOOK, STAR, DRUM, RING, HUG, LOVE. Of those, BOOK, DRUM, HUG and
LOVE have PNG stickers; STAR and RING are **shapes**, drawn by the existing
shape renderer (`render.py:68-99`) rather than loaded as images.

### 4. Spell a word, advanced

The same row with blank underscored slots instead of ghost letters, so nothing
but the announcer and the picture tells you the letter. This is the
`answer_style` setting, not a separate challenge, and the same setting governs
two-digit math answers.

Longer already-recorded words (WATER, HEART, CIRCLE, SQUARE, BALLOON, BUBBLES)
belong to this tier. HEART, CIRCLE and SQUARE are shapes, as above.

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
`answer_style` applies there too (ghost digits vs. blank slots). **A single-digit
answer in this tier shows one slot, never a leading zero**; teaching "07" would
be worse than teaching nothing.

**Subtraction** shows one colored group with the subtracted blocks draining to
grey and drifting off, rather than a second color appearing. The numerals read
`5 - 2` in the same color scheme. Answers of 0 and 1 are allowed in both tiers;
the tier names bound the operands, not the results.

No new art: blocks are flat squares, and Mashpad already draws squares from
`PALETTE`.

## Rendering

`main.py` keeps one smash path and asks `ChallengeDirector.view()` what to
overlay. The target overlay draws **under** the flying items and over the
background, so it never blocks the smash payoff, and it is rebuilt every frame
from `view()` rather than held as mutable render state.

That draw order is in tension with "the correct answer is always the most
visually salient thing on screen", and the tension is real: `MAX_ITEMS = 20`
(`config.py:25`) at `ITEM_SIZE_PX = 280` covers a large fraction of a 1080p
frame with fully saturated glyphs on a near-black ground, and occlusion peaks
during heavy mashing, which is exactly when hints are escalating. Three
mechanisms, all config constants, keep the target readable:

- Non-target spawns render at `CHALLENGE_ITEM_SCALE` (default 0.7) of
  `ITEM_SIZE_PX`.
- The live-item cap drops to `CHALLENGE_MAX_ITEMS` (default 12) while a
  challenge is running.
- A keep-out rectangle around the target is excluded from random spawn
  positions, so items never land directly on top of it.

Whether the flood-to-color moment reads as a reward to an actual two-year-old is
not settled by any of this. It is a named thing the slice-4 Pi gate exists to
test.

## Audio

### The utterance queue

`play_for` and `play_phrase` are one-shots today. "Find the letter... B" is two
clips with a gap, and "what is two plus three" is four. `Audio` gains:

- `speak(clips, gaps)`: play a sequence on the reserved `PHRASE_CHANNEL`, duck
  the bed through `duck.py`, and expose a cancel for when a new round starts
  mid-sentence.

**The correct answer's letter clip rides the utterance queue, not the bed.** The
bed allocator silently drops a clip when all eight bed channels are busy
(`audio.py:305-316`), and the mash burst that empties the rate-limit bucket is
exactly what fills those channels. The one press that must always be heard
cannot go through a path that drops under load.

### `DuckWindow` needs a release

`duck.py:22-57` exposes only `open()` and `factor()`, and `_hold_end` only ever
grows through `max()`. Cancelling a mid-sentence utterance therefore stops the
speech but leaves the bed at `PHRASE_DUCK_FACTOR = 0.075` until the dead
utterance's precomputed hold end. For the math tier, where counting to a total
can run tens of seconds, that would mute the smash payoff for a long stretch
after a round change. Slice 2 adds `DuckWindow.release(now)`, which shrinks
`_hold_end` to `now` and lets the existing fade-up run.

Separately, ducking asks to 0.075 may make the spoken-key reward inaudible
during every hint, which fights the "payoff on every keypress" goal. A gentler
`CHALLENGE_DUCK_FACTOR` is provided as a knob but its value is a Pi-tuning
question, not a paper one.

### Which voice speaks an utterance

No shipped pack contains the carriers, so this cannot be left implicit.
Challenge utterances resolve to a **challenge voice**: the first pack that
contains every stem the challenge needs, preferring the currently selected
voice. Before the Gemini round only `_placeholder` qualifies, so asks are spoken
in the placeholder voice while smash echoes stay in the selected pack. After the
Gemini round all six qualify and the selected voice always wins, so the rule
retires itself.

Every clip within a single utterance comes from the same pack, so a sentence is
never half one voice and half another. If no pack qualifies, or audio is muted
with `--mute`, the round runs visual-only: the ghost target, slot row and blocks
carry it, and the ladder still escalates on its visual steps.

## Voice assets

Two tiers, so no code is ever blocked on an API key.

**Tier 1, placeholders.** One complete `sounds/voice/_placeholder/` pack
generated locally by Kokoro via `seniordev-voice`'s `speech.py`: carriers,
letters, digits, words, everything. It appears in the grown-up menu as its own
selectable voice. Generating only the carriers into the six Gemini packs was
rejected: a Kokoro "find the letter" followed by a Gemini "B" sounds like two
people finishing each other's sentence. A self-contained placeholder directory
also makes "what still needs real audio" a directory listing rather than a
memory.

**Underscore-prefixed packs are selectable but never rotated.** `audio.py:69-71`
returns pack names `sorted()`, so `_placeholder` sorts ahead of every real pack;
`voiceselect.py:49-50` seeds cycle mode with `voices[0]`; random picks uniformly;
and `voiceselect.py:95-101` accepts unknown-gender packs *preferentially* in
cycle rotation. Without an exclusion rule, shipping the placeholder pack would
put robot TTS into ordinary smash sessions and would specifically undo the
guarantee `audio.py` already documents, that curated packs shut robot clips out
of the rotation. `VoiceSelector` skips any pack whose name starts with `_` in
both random and cycle modes; only an explicit menu selection reaches it.

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

Three new rows in the grown-up menu beside `Display`. **Each menu row offers
only the values whose slice has shipped**, so slice 1 cannot select `spell` or
`math` months before they exist. The option list widens as slices land.

**The menu panel is close to full.** Measured with the real font (DejaVuSans-Bold
at `MENU_FONT_PX = 48`, linesize 56): today's 8 rows produce an 828px panel, and
11 rows produce 1050px. At 1080p that fits with 30px to spare; at the 1280x720
windowed dev default it already overflows today, before these rows. The menu has
no scrolling. Slice 1 must either shrink the font, two-column the rows, or add
paging; whichever it picks, the 720p dev window is a pre-existing bug this
change makes worse rather than one it introduces.

## Constraints that fall out of the existing code

- **A correct press must bypass the rate limiter.** `bucket.try_take` gates
  every spawn today, and a mashing toddler empties that bucket. If the child
  finally finds the B and the bucket eats it, the mode is broken. Bypassing is
  simply not calling `try_take`; `ratelimit.py:22-40` has no side channel, so
  skipping it is harmless.
- **Challenge speech outranks reactive phrases.** Both want `PHRASE_CHANNEL`.
  While an utterance is queued or playing, `PhraseDirector.poll` is suppressed,
  otherwise "You're doing amazing!" talks over "Find the letter B". Suppression
  cannot build a backlog, because armed triggers expire via `PHRASE_ARM_TTL_S`
  (`phrases.py:118-122`).
- **Lazy audio loading stays lazy.** This roughly doubles the clip count per
  pack, and eager decoding was already a boot-time and memory problem on the Pi.
- **Challenge is ignored in BabyIDE display mode.** The two are orthogonal in
  the settings, but BabyIDE has no glyph field to overlay, so a challenge simply
  does not run there. Its `KEYDOWN` branch already ends in an early `continue`.
- **Key auto-repeat is not a factor.** `pygame.key.set_repeat` is never called,
  so a held key emits one `KEYDOWN`; the ladder's time arm covers a child who is
  leaning on a key.
- **Nothing new persists.** No progress is tracked by design, so shutdown needs
  no challenge teardown and `main.py`'s `finally` block is unaffected.

## Testing (ships with the feature)

`challenge.py` is pure, so it carries the suite:

- The spacing rule: a burst of presses inside `LADDER_PRESS_SPACING_S` counts
  once, and a 6-per-second mash cannot reach step 1 before its time floor.
- Both ladder arms as an AND: neither the press floor alone nor the time floor
  alone escalates.
- Step 3 gimme: time-only, any key wins, and the round always terminates.
- `ADVANCE` resets the ladder to step 0.
- Pause and resume: elapsed time while paused does not escalate.
- Idle parking and re-announce on next input.
- Shuffled bag: no immediate repeat, including across a reshuffle.
- Strict left-to-right spelling, including a later-in-word letter counting as a
  miss.
- Two-digit math answer entry, including a wrong first digit, and single-digit
  answers rendering one slot.
- Round cancellation mid-utterance.

`Audio.speak` and `DuckWindow.release` get tests in the style of the existing
fallback tests, with no device required. `VoiceSelector` gets a test that an
underscore-prefixed pack never appears in random or cycle rotation but is
reachable by explicit selection.

## Slices (branches off `develop`; item 4 is a gate, not a branch)

1. `feat/challenge-core`: settings, menu rows (with per-slice option lists and a
   fix for the panel height), `ChallengeDirector`, tests
2. `feat/challenge-audio`: utterance queue, `DuckWindow.release`, underscore-pack
   rotation exclusion, challenge-voice resolution, Kokoro placeholder pack
   generator
3. `feat/challenge-letter`: find-the-letter and find-the-number, **plus all of
   the `main.py` wiring**: where `on_key` is called relative to the bucket, the
   rate-limit bypass, the draw order and keep-out zone, the pause hooks for menu
   and splash, and the `PhraseDirector` suppression. This slice owns the
   integration at the level of detail the BabyIDE spec's "Wiring" section used.
4. **Gate:** play it on the Pi and decide whether the loop holds her attention.
   Test specifically whether the flood-to-color reads as a reward and whether
   the ladder thresholds feel right against real mashing. Everything after this
   assumes a yes, and the Gemini round assumes it hard.
5. `feat/challenge-spell`: the slot row, guided and advanced
6. `feat/challenge-math`: counting blocks, both tiers
7. `feat/challenge-voice`: the Gemini carrier round, placeholder pack retires

Version bumps to 1.2.0 only at release.

## Open knobs (small, reversible defaults)

- Ladder thresholds (4/8 counted presses, 10/25/45 seconds) and
  `LADDER_PRESS_SPACING_S` (0.7s). All invented, all to be tuned at the slice-4
  gate against real play.
- `CHALLENGE_ITEM_SCALE` (0.7), `CHALLENGE_MAX_ITEMS` (12), keep-out margin.
- `CHALLENGE_DUCK_FACTOR` versus the existing `PHRASE_DUCK_FACTOR` of 0.075.
- `CHALLENGE_IDLE_S` before a round parks.
- Post-win beat before the next ask.
- Whether an out-of-order letter that is in the word should light up anyway
  (currently no).

## Risks

- **The loop may simply not hold a two-year-old.** This is why slice 4 is a hard
  gate before any recording spend.
- **The ladder thresholds are still invented.** The trigger *shape* was fixed in
  review, but the numbers have never met a real child. They are the first thing
  to retune at the gate.
- **Modes 2 and 5 cannot be validated against the current player.** Accepted
  deliberately.
- **Six short spelling words is a thin pool.** Expanding it costs a Gemini
  round, so the vocabulary limit is a real constraint, not an oversight.
- **Target occlusion is mitigated but unmeasured.** Three constants push against
  it; whether they are enough is a thing to look at on the Pi, not on paper.
- **Per-frame overlay cost on the Pi is unmeasured.** A large outlined glyph plus
  a slot row rebuilt every frame is plausible given the existing surface-cache
  discipline, but nothing has been run on hardware.
