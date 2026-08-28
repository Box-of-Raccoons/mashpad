# mashpad/counting.py — the sums the counting-blocks challenge asks.
#
# Pure — no pygame imports (joins the purity test). Builds the round pool that
# ChallengeDirector shuffles: entries are (target, answer) pairs, because a sum's
# answer is not spelled by its target the way "book" spells its own letters.
#
# Targets are canonical strings ("3+2", "12-5"): one small parseable thing that
# the renderer, the utterance builder and the tests all read the same way.

from __future__ import annotations

# Spoken stems for totals past nine. Digits 0-9 are their own stems already, so
# only these need naming; every voice pack that speaks a carrier has them.
NUMBER_WORDS = {
    10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
    15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
    19: "nineteen", 20: "twenty",
}

# Highest total each tier may reach. The 2-9 tier's answer is always one key
# press; the 0-20 tier's may be two, which is the real difference between them.
TIER_MAX = {"2-9": 9, "0-20": 20}


def parse(target: str):
    """('3+2') -> (3, '+', 2). The one place a target string is taken apart."""
    op = "+" if "+" in target else "-"
    left, right = target.split(op)
    return int(left), op, int(right)


def total(target: str) -> int:
    a, op, b = parse(target)
    return a + b if op == "+" else a - b


def answer(target: str) -> tuple[str, ...]:
    """The keys that answer *target*, digit by digit.

    A single-digit total is one slot, never a padded leading zero: teaching "07"
    would be worse than teaching nothing.
    """
    return tuple(str(total(target)))


def spoken(n: int) -> str:
    """The stem naming *n*: its digit clip below ten, its word from ten up.

    Every number that reaches an utterance goes through here. Asking for "12"
    would find no clip, and speak() is all-or-nothing, so one raw numeral
    anywhere in a sentence runs the whole round silent.
    """
    return NUMBER_WORDS.get(n, str(n))


def spoken_total(target: str) -> str:
    """The stem naming the total of *target*."""
    return spoken(total(target))


def pool(tier: str):
    """[(target, answer), ...] for *tier* — every sum it is allowed to ask.

    Both groups of an addition hold at least one block: an empty pile is nothing
    to count and reads as a drawing bug. Subtraction is bounded by its operands
    rather than its result, so answers of 0 and 1 are allowed and deliberate.
    """
    top = TIER_MAX.get(tier, TIER_MAX["2-9"])
    entries = []
    for a in range(1, top + 1):
        for b in range(1, top + 1):
            if 2 <= a + b <= top:
                entries.append(f"{a}+{b}")
    for a in range(2, top + 1):
        for b in range(1, a + 1):
            entries.append(f"{a}-{b}")
    return [(t, answer(t)) for t in entries]
