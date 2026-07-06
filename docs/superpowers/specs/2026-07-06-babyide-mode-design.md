# BabyIDE Mode — Design

**Date:** 2026-07-06
**Status:** Approved (design); pending implementation plan

## Summary

A new selectable display mode for Mashpad. In **BabyIDE** mode, every keypress
prints the *next token of Mashpad's own source code* into a scrolling, syntax-
highlighted code panel — while still speaking the pressed key, playing a tone,
bouncing the printed word, and occasionally popping a fading raccoon. It is a
key-smasher that prints its own codebase: a gag for the grown-ups, with the
toddler's cause→effect payoff preserved.

It is **not** a real IDE. The only chrome is a single tab at the top showing the
file currently being "edited." No file tree, status bar, minimap, or line
numbers.

## Goals

- Add a `Display` mode toggle (`Smash` = today's behavior, `BabyIDE` = new).
- Preserve the toddler payoff on every keypress: **bounce, tone, spoken key,
  raccoons.**
- Print Mashpad's own source, one token per keypress, with real syntax
  highlighting.
- Reuse existing subsystems wherever possible; add exactly one substantial new
  subsystem (the scrolling code panel).

## Non-goals

- File tree, status bar, minimap, line numbers, or any other IDE chrome beyond a
  single filename tab.
- A real text editor, cursor editing, or user-authored text. All content is the
  scripted source stream.
- Printing BabySmash's source (not present in this repo). Only Mashpad's own
  source is used.

## Behavior (the mechanic)

In BabyIDE mode, each `KEYDOWN` (excluding bare modifier keys):

1. **Speaks the pressed key** — the actual letter/number bashed (existing audio
   path). Non-letter keys play the existing click/ding tone.
2. **Plays the tone** (existing audio).
3. **Prints the next source token** — one token per keypress, regardless of
   which key — into the code panel, with a **pop-in-place bounce**: the newest
   token overshoots slightly larger/brighter and settles as the next token
   arrives. Reuses the overshoot/scale math from `items.py`.
4. **Sometimes pops a raccoon** over the editor that fades exactly as today
   (existing `kind="image"` item lifecycle, gated by the existing "Raccoons"
   amount setting + a per-keypress probability).

The giant 252px centered glyph of Smash mode is **suppressed** in BabyIDE mode.
The keypress payoff is carried by the popped word + raccoon + sound.

The existing `TokenBucket` rate limiter still gates spawns, so a held or mashed
key cannot dump the whole file instantly.

## Components

### 1. `codetext.py` — source token stream (pure logic, no pygame)

Follows the app's pure-logic/pygame split (like `items.py`, `keymap.py`), so it
is unit-testable without a display.

- Holds a **curated, ordered list of Mashpad source files** to stream through.
- Each file is run through the stdlib **`tokenize`** module into a flat sequence
  of print-tokens. Each print-token carries:
  - `text` — the token's source text.
  - `category` — one of `keyword`, `string`, `comment`, `number`, `name`, `op`
    (mapped from `tokenize` token types / `keyword.kwlist`).
  - line/column info so the panel knows where line breaks and indentation occur.
- **Iterator:** `next()` returns the next **printable** print-token and
  advances. `tokenize`'s structural tokens (`NEWLINE`/`NL`/`INDENT`/`DEDENT`,
  encoding, endmarker) are **not** consumed per keypress — line breaks and
  indentation are recorded on the following printable token (via its line/column
  info) and applied by the layout, so one keypress always yields one visible
  word. At end of a file `next()` advances to the next file and signals a
  **filename change** (drives the tab). After the last file it **loops** back to
  the first.
- **Highlighting:** `category → color`, using a cute palette (keywords one hue,
  strings another, comments a muted green, numbers, names default, operators).

**Source availability (build note):** the frozen PyInstaller build will not have
`mashpad/*.py` on disk by default. Resolution: read the real installed source
files at runtime (via `__file__` / `importlib.resources`) and add them to the
PyInstaller `datas` so the frozen build ships them. This avoids duplicated,
drifting copies. Small touch to the build config; detailed in the plan.

### 2. `codepanel.py` — scrolling code panel (pure layout + thin pygame blit)

Mirrors the existing split: a **pure layout function** computes token placements;
a thin pygame layer blits them. This is the only substantial new subsystem.

- A **new font instance at ~48px** (config knob). Keeps the existing
  `DejaVuSans-Bold.ttf` (proportional — acceptable for a gag; no monospace
  bundling).
- Holds laid-out lines of placed tokens. A cursor advances `x` per token and
  wraps on line-break tokens. When content exceeds panel height, the panel
  **scrolls up.**
- Code **persists and scrolls — it never fades.** (This is the key lifecycle
  difference from Smash items.)
- The **newest token carries the bounce**; older tokens are static.
- **Soft-wrap:** a token that would overflow the right margin wraps to the next
  line. Exact source line breaks are approximated, not guaranteed — acceptable
  for the gag.

### 3. Tab bar

A single tab (rounded rect + filename text) at the top of the screen, updated
when `codetext` reports a file change. The only IDE chrome.

### 4. Wiring

- **`settings.py`:** add a validated `display_mode` field (default `smash`),
  with `DISPLAY_MODES = ("smash", "babyide")`, `_from_dict` validation, and
  `save` round-trip — matching the existing `sound_mode` pattern.
- **`menu.py`:** add one `Display` row (new `_ROW_*` constant, bump
  `_ROW_COUNT`, add `_step_*` handler + `_rows()` entry).
- **`main.py`:** branch the `KEYDOWN` / spawn / draw path on `display_mode`.
  Draw order per frame: background → code panel → raccoon items (fading, drawn on
  top) → tab bar → menu/splash overlay → flip.

## Data flow (per keypress, BabyIDE mode)

```
KEYDOWN
  → main loop (babyide branch), gated by TokenBucket
    → audio: speak pressed key + tone
    → codetext.next() → print-token (+ maybe filename change → tab update)
    → codepanel.append(token)  # placed at cursor, bounce on newest
    → maybe imagefield.spawn(raccoon)  # existing fade lifecycle

per frame:
  fill(BACKGROUND)
    → codepanel.draw()   # static lines + popped newest with bounce
    → item field draw    # raccoons fading, on top
    → tab bar draw
    → menu / splash overlay
    → display.flip()
```

## Testing (ships with the feature)

- **`codetext`:** token categories map to expected colors; exactly one token per
  `next()`; EOF advances to the next file and reports the new filename; loops
  after the last file; whitespace/newline handling.
- **`codepanel`** (pure layout): cursor advance, soft-wrap on overflow, scroll
  trigger when content exceeds panel height.
- **`settings`:** `display_mode` validation (rejects unknown values, defaults to
  `smash`) and load/save round-trip — matching existing settings tests.

## Open knobs (small, reversible defaults)

- Mode label: **`BabyIDE`**.
- Code font size: **~48px**.
- Per-keypress raccoon probability (tuned against the existing "Raccoons"
  amount setting).

## Risks / notes

- **Engagement trade-off:** small scrolling text is less viscerally engaging for
  a toddler than a 252px bouncing glyph. Mitigated by keeping the bounce, tone,
  spoken key, and fading raccoons loud on every keypress. This mode is
  grown-up-facing garnish; the toddler payoff must stay in the keypress burst.
- **Scope creep:** "render it up like an IDE" is where a one-evening gag becomes
  a week. Scope is deliberately capped at panel + one tab.
- **Frozen build source:** see the `codetext.py` build note above.
