# mashpad/challenge.py — decides WHAT the app asks for and WHEN it helps.
#
# Pure — no pygame imports (joins the purity test). All time is passed in from
# the caller; the module never reads the clock. main.py feeds it presses and
# calls poll() once per frame; audio.py speaks whatever poll() returns and the
# renderer draws view().
#
# The round is always winnable. The ladder's last step accepts any key, which is
# what makes an all-26 letter pool safe for a toddler rather than needing a
# grown-up-curated subset.

from __future__ import annotations

from dataclasses import dataclass

from mashpad import config

# on_key verdicts.
IGNORED = "ignored"    # no live round, or the round is already won
MISS = "miss"          # wrong key — the caller still does the normal smash
ADVANCE = "advance"    # a slot filled, more to go
CORRECT = "correct"    # the round is won

_LETTERS = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"

# Target pools by challenge kind. Word and sum pools depend on grown-up settings
# the caller owns, so those arrive through the constructor's *pool* instead.
_POOLS = {"letter": _LETTERS, "number": _DIGITS}


@dataclass(frozen=True)
class Round:
    """One ask: what is wanted, which keys satisfy it, and what art illustrates it."""
    kind: str
    target: str                  # "b", "7", "book"
    answer: tuple[str, ...]      # expected keys, in order
    art: str | None              # sticker/shape name for the step-2 hint


@dataclass(frozen=True)
class View:
    """Everything the renderer needs. No pygame types cross this boundary."""
    kind: str
    target: str
    answer: tuple[str, ...]
    progress: int                # slots already filled
    step: int                    # current ladder step, 0-3
    gimme: bool                  # True once any key wins
    art: str | None
    # Wall time the last slot was filled. The renderer needs it to land a
    # completed letter before the next one lights: in BOOK the glow would
    # otherwise slide from one O to an identical O and read as nothing
    # happening. None until the first fill of the round.
    filled_at: float | None = None


def _art_index(art_names):
    """Group available art names by first letter, for the step-2 hint.

    Built from the names the caller actually found on disk rather than a
    hardcoded table, so the mapping can't go stale when art is added or renamed.
    """
    index: dict[str, list[str]] = {}
    for name in art_names:
        if name:
            index.setdefault(name[0].lower(), []).append(name)
    return index


class ChallengeDirector:
    """Owns one round at a time: the ask, the judging, and the hint ladder."""

    def __init__(self, kind: str, rng, art_names=(), pool=None) -> None:
        self._kind = kind
        self._rng = rng
        # The pool has to live in here rather than being fed a round at a time:
        # poll() restarts the round itself after the win beat, and a director
        # with nothing to draw from would strand every round after the first.
        self._pool = list(pool) if pool is not None else _POOLS.get(kind, "")
        self._art = _art_index(art_names)
        self._bag: list[str] = []
        self._last_target: str | None = None
        self._round: Round | None = None
        self._progress = 0
        self._filled_at: float | None = None
        # Ladder state. _elapsed is round time, not wall time: it stops while
        # paused (grown-up menu, splash) and while parked (nobody is playing).
        self._step = 0
        self._counted = 0
        self._last_counted_at: float | None = None
        self._elapsed = 0.0
        self._last_tick = 0.0
        self._paused = False
        self._parked = False
        self._last_input_at = 0.0
        self._pending_ask = False
        self._pending_hint: int | None = None
        self._won_at: float | None = None

    # ------------------------------------------------------------------ state

    @property
    def step(self) -> int:
        return self._step

    @property
    def progress(self) -> int:
        return self._progress

    @property
    def counted_presses(self) -> int:
        return self._counted

    @property
    def parked(self) -> bool:
        return self._parked

    @property
    def round(self) -> "Round | None":
        return self._round

    # ----------------------------------------------------------------- rounds

    def start_round(self, now: float) -> None:
        """Draw the next target and arm its ask (delivered by the next poll)."""
        self._round = self._build(self._draw())
        self._progress = 0
        self._filled_at = None
        self._won_at = None
        self._parked = False
        self._last_input_at = now
        self._reset_ladder(now)
        self._pending_ask = True

    def force_round(self, target: str, answer=None) -> None:
        """Replace the current round without disturbing the ladder.

        Used by tests, and by challenges whose pool the caller owns (spelling
        words, sums) rather than this module.
        """
        self._round = self._build(target, answer)
        self._progress = 0
        self._filled_at = None

    def _build(self, target, answer=None) -> Round:
        # A pool entry is either a bare target ("book"), whose answer is its own
        # letters, or a (target, answer) pair ("3+2", ("5",)) for an ask the
        # target does not spell out.
        if answer is None and not isinstance(target, str):
            target, answer = target
        return Round(
            kind=self._kind,
            target=target,
            answer=tuple(answer) if answer else tuple(target),
            art=self._art_for(target),
        )

    def _art_for(self, target: str) -> "str | None":
        # A word round IS its own picture — "book" its sticker, "star" the shape.
        # Falling through to the first-letter index would stand a sandwich beside
        # STAR, because no star.png exists.
        if len(target) > 1:
            return target if target.isalpha() else None
        if target in self._art.get(target[:1], ()):
            return target                      # the target IS a sticker (word rounds)
        options = self._art.get(target[:1].lower())
        return self._rng.choice(options) if options else None

    def _draw(self):
        """Next entry from a shuffled bag, never the same one twice running."""
        if not self._bag:
            self._bag = list(self._pool)
            self._rng.shuffle(self._bag)
        if len(self._bag) > 1 and self._bag[0] == self._last_target:
            self._bag[0], self._bag[1] = self._bag[1], self._bag[0]
        target = self._bag.pop(0)
        self._last_target = target
        return target

    # ----------------------------------------------------------------- ladder

    def _reset_ladder(self, now: float) -> None:
        self._step = 0
        self._counted = 0
        self._last_counted_at = None
        self._elapsed = 0.0
        self._last_tick = now
        self._pending_hint = None

    def _tick(self, now: float) -> None:
        """Advance round time. Stops while paused, parked, or celebrating."""
        if not self._paused and not self._parked and self._won_at is None:
            self._elapsed += max(0.0, now - self._last_tick)
        self._last_tick = now

    def pause(self, now: float) -> None:
        self._tick(now)
        self._paused = True

    def resume(self, now: float) -> None:
        self._tick(now)
        self._paused = False

    # ------------------------------------------------------------------ input

    def on_key(self, char, now: float) -> str:
        """Judge one baby-input event. *char* is None for space/enter/clicks.

        Every event counts as a press, whether or not the rate limiter dropped
        its spawn and whether or not it maps to a character: the child pressed
        something, and the bucket's opinion says nothing about whether they are
        trying. Only the spacing rule decides what counts toward escalation.
        """
        self._tick(now)
        if self._round is None or self._won_at is not None:
            return IGNORED

        if self._parked:
            # Coming back after a long absence starts the round over rather than
            # dropping the child into an already-escalated ladder.
            self._parked = False
            self._reset_ladder(now)
            self._pending_hint = 0
        self._last_input_at = now

        if (self._last_counted_at is None
                or now - self._last_counted_at >= config.CHALLENGE_PRESS_SPACING_S):
            self._counted += 1
            self._last_counted_at = now

        expected = self._round.answer[self._progress]
        if char != expected and self._step < len(config.CHALLENGE_LADDER):
            return MISS

        self._progress += 1
        self._filled_at = now
        if self._progress >= len(self._round.answer):
            self._won_at = now
            return CORRECT
        self._reset_ladder(now)    # each slot gets a fresh ladder
        return ADVANCE

    # ------------------------------------------------------------------- poll

    def poll(self, now: float):
        """Return one event to act on, or None. At most one per call.

        Events: ("ask", Round) and ("hint", level). The caller turns those into
        an utterance and a visual; this module never decides how they sound.
        """
        self._tick(now)
        if self._round is None:
            return None

        if self._pending_ask:
            self._pending_ask = False
            return ("ask", self._round)

        if self._won_at is not None:
            if now - self._won_at >= config.CHALLENGE_WIN_BEAT_S:
                self.start_round(now)
                self._pending_ask = False
                return ("ask", self._round)
            return None

        if not self._paused and now - self._last_input_at > config.CHALLENGE_IDLE_S:
            self._parked = True
            return None

        if self._pending_hint is not None:
            level = self._pending_hint
            self._pending_hint = None
            return ("hint", level)

        if self._paused or self._parked:
            return None

        # Highest satisfied step wins, so a child who has stopped pressing skips
        # the lower rungs and gets the gimme rather than waiting them out.
        for level in range(len(config.CHALLENGE_LADDER), self._step, -1):
            presses, seconds = config.CHALLENGE_LADDER[level - 1]
            if self._elapsed >= seconds and (presses is None or self._counted >= presses):
                self._step = level
                return ("hint", level)
        return None

    # ------------------------------------------------------------------- view

    def view(self) -> "View | None":
        if self._round is None:
            return None
        return View(
            kind=self._round.kind,
            target=self._round.target,
            answer=self._round.answer,
            progress=self._progress,
            step=self._step,
            gimme=self._step >= len(config.CHALLENGE_LADDER),
            art=self._round.art,
            filled_at=self._filled_at,
        )
