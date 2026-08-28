"""The spelling word pools must be speakable and showable in every voice pack.

Pure — no pygame. A word that a pack cannot say runs the round silently, and a
word with neither a sticker nor a shape runs it with an empty picture; either is
a half-round that no other test would catch, because both fail quietly.
"""

import sys

from mashpad import config, paths


def _packs():
    """Shipped voice packs. Underscore-prefixed packs are throwaway placeholders."""
    voice_dir = paths.app_root() / "sounds" / "voice"
    return sorted(p for p in voice_dir.iterdir()
                  if p.is_dir() and not p.name.startswith("_"))


def _speaks(pack, word: str) -> bool:
    """True when *pack* has at least one take of *word* (word.ogg or word-2.ogg)."""
    return any(f.stem == word or f.stem.startswith(f"{word}-")
               for f in pack.iterdir() if f.suffix in (".ogg", ".wav"))


def test_the_module_is_pure():
    assert "pygame" not in sys.modules


def test_the_guided_pool_is_a_prefix_of_the_advanced_pool():
    # Advanced is harder because its slots are blank, not because the short
    # words vanish; a six-word bag on blank slots would also repeat constantly.
    assert (config.SPELL_WORDS_ADVANCED[:len(config.SPELL_WORDS_GUIDED)]
            == config.SPELL_WORDS_GUIDED)


def test_every_shipped_pack_can_speak_every_spelling_word():
    packs = _packs()
    assert packs, "no voice packs found"
    missing = [(pack.name, word) for pack in packs
               for word in config.SPELL_WORDS_ADVANCED if not _speaks(pack, word)]
    assert not missing, missing


def test_every_spelling_word_has_a_picture():
    stickers = {p.stem for p in (paths.app_root() / "assets" / "images").glob("*.png")}
    unshowable = [w for w in config.SPELL_WORDS_ADVANCED
                  if w not in stickers and w not in config.SHAPES]
    assert not unshowable, unshowable


def test_every_spelling_word_is_spelled_with_keyboard_letters():
    # The answer is pressed key by key, so a word with a hyphen or an accent
    # would have a slot no key can fill.
    assert all(w.isalpha() and w.isascii() and w.islower()
               for w in config.SPELL_WORDS_ADVANCED)
