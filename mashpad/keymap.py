# mashpad/keymap.py — maps a key character to an ItemSpec.
# Pure — no pygame imports. main.py translates pygame keycodes to plain chars.

from __future__ import annotations

import random as _random
from dataclasses import dataclass
from typing import Optional

from mashpad import config


@dataclass
class ItemSpec:
    """Describes what kind of item to spawn (determined at key-press time)."""
    # One of "letter", "digit", "shape"
    kind: str
    # Display name: lowercase letter ("a"), digit string ("7"), or shape name ("star")
    name: str
    # RGB colour chosen from PALETTE
    color: tuple[int, int, int]


def item_for_key(char_or_none: Optional[str], rng: _random.Random) -> ItemSpec:
    """Return an ItemSpec for the given key character.

    Parameters
    ----------
    char_or_none:
        The unicode character of the pressed key, already case-folded to
        lowercase by the caller if it is a letter.  Pass None (or any
        character that is not a-z / 0-9) to get a random shape.
    rng:
        Injected Random instance so callers can seed for tests.
    """
    color = rng.choice(config.PALETTE)

    if char_or_none is not None:
        c = char_or_none.lower()
        if c.isalpha() and len(c) == 1 and 'a' <= c <= 'z':
            return ItemSpec(kind="letter", name=c, color=color)
        if c.isdigit() and len(c) == 1:
            return ItemSpec(kind="digit", name=c, color=color)

    # Anything else (None, space, enter, F-keys, etc.) → random shape.
    shape = rng.choice(config.SHAPES)
    return ItemSpec(kind="shape", name=shape, color=color)
