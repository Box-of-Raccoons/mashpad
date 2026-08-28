"""Tests for mashpad.challenge — pure logic, no pygame.

The ladder tests are the important ones. An earlier draft of the design
escalated on "N presses OR M seconds, whichever comes first", which config.py's
own numbers defeat: BUCKET_REFILL_PER_S is 6.0 and SLOWDOWN_DROPS treats 6 drops
in 3 seconds as ordinary mashing, so a happy masher reached the any-key step in
about four seconds every round. test_mash_rate_cannot_outrun_the_time_floor and
test_burst_of_presses_counts_once pin the fix.
"""

import random
import sys

import pytest

from mashpad import config
from mashpad.challenge import ADVANCE, CORRECT, IGNORED, MISS, ChallengeDirector


@pytest.fixture
def rng():
    return random.Random(1234)


def _letter_director(rng, art_names=()):
    """A started letter round, forced to a known target for readable asserts."""
    d = ChallengeDirector("letter", rng, art_names=art_names)
    d.start_round(0.0)
    d.poll(0.0)  # consume the ask
    return d


def _force(director, target, answer=None):
    """Pin the current round's target so a test can press known keys."""
    director.force_round(target, answer)


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_challenge_no_pygame():
    import mashpad.challenge  # noqa: F401
    assert "pygame" not in sys.modules, "challenge imported pygame!"


# ---------------------------------------------------------------------------
# The ask
# ---------------------------------------------------------------------------

def test_first_poll_announces_the_ask(rng):
    d = ChallengeDirector("letter", rng)
    d.start_round(0.0)
    event = d.poll(0.0)
    assert event[0] == "ask"
    assert event[1].kind == "letter"
    assert event[1].target in "abcdefghijklmnopqrstuvwxyz"


def test_ask_is_announced_only_once(rng):
    d = ChallengeDirector("letter", rng)
    d.start_round(0.0)
    assert d.poll(0.0)[0] == "ask"
    assert d.poll(0.1) is None


def test_number_rounds_draw_digits(rng):
    d = ChallengeDirector("number", rng)
    d.start_round(0.0)
    assert d.poll(0.0)[1].target in "0123456789"


# ---------------------------------------------------------------------------
# Judging a press
# ---------------------------------------------------------------------------

def test_correct_key_wins(rng):
    d = _letter_director(rng)
    _force(d, "b")
    assert d.on_key("b", 1.0) == CORRECT


def test_wrong_key_is_a_miss(rng):
    d = _letter_director(rng)
    _force(d, "b")
    assert d.on_key("k", 1.0) == MISS


def test_press_after_the_win_is_ignored(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.on_key("b", 1.0)
    assert d.on_key("k", 1.1) == IGNORED


def test_non_answer_keys_still_count_as_presses(rng):
    """Space is a toddler's most-mashed key; it must feed the ladder."""
    d = _letter_director(rng)
    _force(d, "b")
    assert d.on_key(None, 1.0) == MISS
    assert d.counted_presses == 1


# ---------------------------------------------------------------------------
# The hint ladder — trigger shape
# ---------------------------------------------------------------------------

def test_burst_of_presses_counts_once(rng):
    """Ten presses inside the spacing window are one deliberate attempt."""
    d = _letter_director(rng)
    _force(d, "b")
    t = 1.0
    for _ in range(10):
        d.on_key("k", t)
        t += 0.05
    assert d.counted_presses == 1


def test_mash_rate_cannot_outrun_the_time_floor(rng):
    """Six presses a second for three seconds must not reach any hint.

    This is the defect the design review caught. Under the old OR rule this
    reached the any-key gimme; under the AND rule the 10s floor holds it at
    step 0.
    """
    d = _letter_director(rng)
    _force(d, "b")
    t = 0.0
    for _ in range(18):          # 6/s for 3s, the repo's own definition of mashing
        t += 1.0 / 6.0
        d.on_key("k", t)
        assert d.poll(t) is None
    assert d.step == 0


def test_presses_alone_do_not_escalate(rng):
    """The press floor is met but the time floor is not."""
    d = _letter_director(rng)
    _force(d, "b")
    t = 0.0
    for _ in range(6):           # well spaced, so all six count
        t += 1.0
        d.on_key("k", t)
    assert d.counted_presses >= 4
    assert d.poll(t) is None
    assert d.step == 0


def test_time_alone_does_not_escalate_to_step_one(rng):
    """No presses at all: step 1 needs its press floor too."""
    d = _letter_director(rng)
    _force(d, "b")
    assert d.poll(11.0) is None
    assert d.step == 0


def test_both_floors_met_escalates(rng):
    d = _letter_director(rng)
    _force(d, "b")
    t = 0.0
    for _ in range(4):
        t += 1.0
        d.on_key("k", t)
    assert d.poll(11.0) == ("hint", 1)
    assert d.step == 1


def test_gimme_is_time_only(rng):
    """A child who has stopped pressing is exactly who the gimme rescues."""
    d = _letter_director(rng)
    _force(d, "b")
    assert d.poll(46.0) == ("hint", 3)
    assert d.step == 3


def test_gimme_accepts_any_key(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.poll(46.0)
    assert d.on_key("q", 47.0) == CORRECT


def test_hints_do_not_repeat(rng):
    d = _letter_director(rng)
    _force(d, "b")
    assert d.poll(46.0) == ("hint", 3)
    assert d.poll(47.0) is None


# ---------------------------------------------------------------------------
# Multi-slot answers
# ---------------------------------------------------------------------------

def test_advance_fills_one_slot(rng):
    d = _letter_director(rng)
    _force(d, "book", answer=("b", "o", "o", "k"))
    assert d.on_key("b", 1.0) == ADVANCE
    assert d.progress == 1


def test_out_of_order_letter_in_the_word_is_a_miss(rng):
    """The K is in BOOK, but only the glowing letter counts."""
    d = _letter_director(rng)
    _force(d, "book", answer=("b", "o", "o", "k"))
    assert d.on_key("k", 1.0) == MISS
    assert d.progress == 0


def test_last_slot_wins(rng):
    d = _letter_director(rng)
    _force(d, "hug", answer=("h", "u", "g"))
    assert d.on_key("h", 1.0) == ADVANCE
    assert d.on_key("u", 2.0) == ADVANCE
    assert d.on_key("g", 3.0) == CORRECT


def test_advance_resets_the_ladder(rng):
    """Each letter gets a fresh ladder; otherwise long words collapse to gimmes."""
    d = _letter_director(rng)
    _force(d, "hug", answer=("h", "u", "g"))
    d.poll(46.0)
    assert d.step == 3
    d.on_key("h", 46.5)          # gimme is live, so this advances
    assert d.step == 0
    assert d.counted_presses == 0
    assert d.poll(47.0) is None


def test_gimme_fills_only_one_slot(rng):
    d = _letter_director(rng)
    _force(d, "hug", answer=("h", "u", "g"))
    d.poll(46.0)
    assert d.on_key("z", 47.0) == ADVANCE
    assert d.progress == 1


# ---------------------------------------------------------------------------
# Pausing and idling
# ---------------------------------------------------------------------------

def test_pause_freezes_the_ladder_clock(rng):
    """A 40-second options visit must not escalate the round."""
    d = _letter_director(rng)
    _force(d, "b")
    d.pause(1.0)
    assert d.poll(41.0) is None
    d.resume(41.0)
    # 46s of wall clock have passed but only ~6s of round time.
    assert d.poll(46.5) is None
    assert d.step == 0
    assert d.poll(86.5) == ("hint", 3)


def test_idle_parks_the_round(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.on_key("k", 1.0)
    parked_at = 1.0 + config.CHALLENGE_IDLE_S + 1.0
    assert d.poll(parked_at) is None
    assert d.parked


def test_input_after_idle_re_announces(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.on_key("k", 1.0)
    parked_at = 1.0 + config.CHALLENGE_IDLE_S + 1.0
    d.poll(parked_at)
    d.on_key("k", parked_at + 1.0)
    assert not d.parked
    assert d.poll(parked_at + 1.0) == ("hint", 0)


# ---------------------------------------------------------------------------
# Rounds and the bag
# ---------------------------------------------------------------------------

def test_next_round_starts_after_the_beat(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.on_key("b", 1.0)
    assert d.poll(1.0) is None                      # celebrating
    event = d.poll(1.0 + config.CHALLENGE_WIN_BEAT_S + 0.1)
    assert event[0] == "ask"


def test_bag_never_repeats_back_to_back(rng):
    """Includes the reshuffle boundary, where naive bags collide."""
    d = ChallengeDirector("number", rng)
    seen = []
    for i in range(60):
        d.start_round(float(i))
        seen.append(d.poll(float(i))[1].target)
    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert len(set(seen)) == 10                      # the whole pool gets used


def test_bag_covers_the_pool_before_repeating(rng):
    d = ChallengeDirector("number", rng)
    seen = []
    for i in range(10):
        d.start_round(float(i))
        seen.append(d.poll(float(i))[1].target)
    assert sorted(seen) == list("0123456789")


# ---------------------------------------------------------------------------
# Sticker art for the step-2 hint
# ---------------------------------------------------------------------------

def test_art_is_chosen_by_first_letter(rng):
    d = ChallengeDirector("letter", rng, art_names=("balloon", "book", "water"))
    d.start_round(0.0)
    d.poll(0.0)
    d.force_round("w")
    assert d.view().art == "water"


def test_art_is_none_when_no_sticker_starts_with_the_letter(rng):
    d = ChallengeDirector("letter", rng, art_names=("balloon", "book"))
    d.start_round(0.0)
    d.poll(0.0)
    d.force_round("q")
    assert d.view().art is None


# ---------------------------------------------------------------------------
# The view
# ---------------------------------------------------------------------------

def test_view_reports_progress_and_step(rng):
    d = _letter_director(rng)
    _force(d, "hug", answer=("h", "u", "g"))
    d.on_key("h", 1.0)
    v = d.view()
    assert v.target == "hug"
    assert v.answer == ("h", "u", "g")
    assert v.progress == 1
    assert v.step == 0
    assert v.gimme is False


def test_view_flags_the_gimme(rng):
    d = _letter_director(rng)
    _force(d, "b")
    d.poll(46.0)
    assert d.view().gimme is True


# ---------------------------------------------------------------------------
# Caller-supplied pools: spelling words and sums
# ---------------------------------------------------------------------------

def test_a_word_pool_supplies_rounds(rng):
    d = ChallengeDirector("spell", rng, pool=["book", "star"])
    d.start_round(0.0)
    assert d.round.target in ("book", "star")
    assert d.round.answer == tuple(d.round.target)


def test_a_word_round_restarts_from_its_own_pool(rng):
    # poll() starts the next round itself, so a director fed one round at a time
    # would strand every round after the first with an empty pool.
    d = ChallengeDirector("spell", rng, pool=["hug"])
    d.start_round(0.0)
    d.poll(0.0)
    for i, ch in enumerate("hug"):
        d.on_key(ch, float(i))
    kind, round_ = d.poll(10.0)
    assert kind == "ask"
    assert round_.target == "hug"


def test_a_pool_entry_may_carry_its_own_answer(rng):
    # A sum's answer is not spelled by its target, so the pool supplies both.
    d = ChallengeDirector("math", rng, pool=[("3+2", ("5",))])
    d.start_round(0.0)
    assert d.round.target == "3+2"
    assert d.round.answer == ("5",)
    assert d.round.art is None


def test_a_word_is_its_own_picture(rng):
    # No star.png exists, so the first-letter index would stand a sandwich beside
    # STAR. A word round draws the word, and the renderer picks sticker or shape.
    d = ChallengeDirector("spell", rng,
                          art_names=("sandwich", "sleep", "book"))
    d.force_round("star")
    assert d.round.art == "star"


def test_a_single_letter_target_still_borrows_a_sticker(rng):
    d = ChallengeDirector("letter", rng, art_names=("sandwich",))
    d.force_round("s")
    assert d.round.art == "sandwich"


# ---------------------------------------------------------------------------
# When a slot landed (the renderer's double-letter cue)
# ---------------------------------------------------------------------------

def test_view_reports_when_the_last_slot_landed(rng):
    d = ChallengeDirector("spell", rng, pool=["hug"])
    d.start_round(0.0)
    assert d.view().filled_at is None
    d.on_key("h", 3.0)
    assert d.view().filled_at == 3.0


def test_a_fresh_round_forgets_the_previous_landing(rng):
    d = ChallengeDirector("spell", rng, pool=["hug", "book"])
    d.start_round(0.0)
    d.on_key(d.round.answer[0], 1.0)
    d.start_round(5.0)
    assert d.view().filled_at is None
