"""Tests for mashpad.counting — the sums the counting-blocks challenge asks.

Pure logic, no pygame. The tier rules are the interesting part: which sums each
tier is allowed to ask, and how many keys their answers take.
"""

import sys

from mashpad import counting


def test_the_module_is_pure():
    import mashpad.counting  # noqa: F401 — the import IS the assertion
    assert "pygame" not in sys.modules, "counting imported pygame!"


def test_a_target_parses_into_its_two_operands():
    assert counting.parse("3+2") == (3, "+", 2)
    assert counting.parse("12-5") == (12, "-", 5)
    assert counting.parse("20-20") == (20, "-", 20)


def test_an_answer_is_one_key_per_digit():
    assert counting.answer("3+2") == ("5",)
    assert counting.answer("9+8") == ("1", "7")


def test_a_single_digit_total_never_grows_a_leading_zero():
    # "07" would be worse than teaching nothing.
    assert counting.answer("5-5") == ("0",)
    assert counting.answer("20-19") == ("1",)


def test_the_small_tier_always_answers_in_one_key():
    # This is the real difference between the tiers: one key press, or two.
    assert all(len(a) == 1 for _t, a in counting.pool("2-9"))


def test_the_big_tier_asks_two_digit_answers_too():
    assert any(len(a) == 2 for _t, a in counting.pool("0-20"))


def test_no_tier_asks_a_sum_it_cannot_show():
    for tier, top in (("2-9", 9), ("0-20", 20)):
        for target, _answer in counting.pool(tier):
            a, op, b = counting.parse(target)
            assert 1 <= a <= top and 1 <= b <= top, (tier, target)
            total = counting.total(target)
            assert 0 <= total <= top, (tier, target)
            if op == "+":
                assert total >= 2, (tier, target)   # both piles hold a block
            else:
                assert b <= a, (tier, target)       # never a negative answer


def test_subtraction_may_answer_zero_or_one():
    # The tier names bound the operands, not the results.
    answers = {counting.total(t) for t, _a in counting.pool("2-9")}
    assert 0 in answers and 1 in answers


def test_a_total_past_nine_is_spoken_as_a_word():
    assert counting.spoken_total("3+2") == "5"
    assert counting.spoken_total("9+8") == "seventeen"
    assert counting.spoken_total("10+10") == "twenty"


def test_an_unknown_tier_falls_back_to_the_small_one():
    # A hand-edited settings.json must not produce an empty pool: the director
    # would raise on its first draw.
    assert counting.pool("nonsense") == counting.pool("2-9")


def test_a_number_past_nine_is_spoken_as_a_word_everywhere():
    # speak() is all-or-nothing, so one raw "12" anywhere in a sentence runs the
    # whole round silent. Every number reaching an utterance goes through here.
    assert counting.spoken(9) == "9"
    assert counting.spoken(10) == "ten"
    assert counting.spoken(20) == "twenty"
