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
    image_weight: float = 0.5,
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
        Single-char image reskins are excluded by the caller before passing here.
    image_weight:
        Probability that a non-alphanumeric spawn is an image (when *extras* is
        non-empty).  Otherwise a uniform shape is chosen.  The app derives this
        from config.RACCOON_WEIGHTS[settings.raccoon_amount]; tests pass 0.0
        (never image) or 1.0 (always image when extras exist).
    """
    color = rng.choice(config.PALETTE)

    if char_or_none is not None:
        c = char_or_none.lower()
        if c.isalpha() and len(c) == 1 and 'a' <= c <= 'z':
            return ItemSpec(kind="letter", name=c, color=color)
        if c.isdigit() and len(c) == 1:
            return ItemSpec(kind="digit", name=c, color=color)

    # Anything else (None, space, enter, F-keys, etc.) → an image (weighted) or
    # a shape.  When extras exist we roll image_weight; on a hit, pick uniformly
    # from the images, else pick uniformly from config.SHAPES.  With no extras
    # the roll is skipped entirely (no rng draw consumed) → always a shape.
    if extras and rng.random() < image_weight:
        pick = rng.choice(list(extras))
        return ItemSpec(kind="image", name=pick.name, color=color, spoken=pick.spoken)
    shape = rng.choice(config.SHAPES)
    return ItemSpec(kind="shape", name=shape, color=color)
