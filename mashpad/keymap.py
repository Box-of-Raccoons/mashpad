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
    # One of "letter", "digit", "shape", "image"
    kind: str
    # Display name: lowercase letter ("a"), digit string ("7"), shape name ("star"),
    # or image file stem ("raccoon3")
    name: str
    # RGB colour chosen from PALETTE
    color: tuple[int, int, int]
    # Spoken word for audio lookup; empty string means use name as-is.
    spoken: str = ""

    @property
    def spoken_name(self) -> str:
        """Return the word used for voice clip lookup: spoken if set, else name."""
        return self.spoken or self.name


def item_for_key(
    char_or_none: Optional[str],
    rng: _random.Random,
    extras: "tuple | list" = (),
) -> ItemSpec:
    """Return an ItemSpec for the given key character.

    Parameters
    ----------
    char_or_none:
        The unicode character of the pressed key, already case-folded to
        lowercase by the caller if it is a letter.  Pass None (or any
        character that is not a-z / 0-9) to get a random shape (or image).
    rng:
        Injected Random instance so callers can seed for tests.
    extras:
        Sequence of ImageEntry-like objects (anything with .name and .spoken).
        Non-alphanumeric input picks uniformly from config.SHAPES + extras.
        Single-char image reskins are excluded by the caller before passing here.
    """
    color = rng.choice(config.PALETTE)

    if char_or_none is not None:
        c = char_or_none.lower()
        if c.isalpha() and len(c) == 1 and 'a' <= c <= 'z':
            return ItemSpec(kind="letter", name=c, color=color)
        if c.isdigit() and len(c) == 1:
            return ItemSpec(kind="digit", name=c, color=color)

    # Anything else (None, space, enter, F-keys, etc.) → pick uniformly from
    # the combined pool of shapes + image extras.  With 8 shapes and N extras,
    # each entry is equally likely (e.g. 13 extras → extras are ~62% of spawns).
    pool: list = list(config.SHAPES) + list(extras)
    pick = rng.choice(pool)
    if isinstance(pick, str):
        # Shape name string.
        return ItemSpec(kind="shape", name=pick, color=color)
    else:
        # ImageEntry-like object — carries .name and .spoken.
        return ItemSpec(kind="image", name=pick.name, color=color, spoken=pick.spoken)
