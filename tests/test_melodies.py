"""Tests for mashpad.melodies — pure song data + sequential note sequencer."""

import sys

import pytest

from mashpad import melodies
from mashpad.melodies import SONGS, MelodySequencer, Song, _parse


# ---------------------------------------------------------------------------
# Notation parser
# ---------------------------------------------------------------------------

def test_parse_octave_marks():
    # unmarked = base octave 5; "'" up one; "," down one.
    assert _parse("C") == ("c5",)
    assert _parse("C'") == ("c6",)
    assert _parse("G,") == ("g4",)


def test_parse_ignores_bars_and_whitespace():
    assert _parse("C D E | C") == ("c5", "d5", "e5", "c5")
    assert _parse("  C   E  ") == ("c5", "e5")


def test_parse_rejects_bad_token():
    with pytest.raises(ValueError):
        _parse("H")          # no such note letter
    with pytest.raises(ValueError):
        _parse("C#")         # accidentals unsupported


# ---------------------------------------------------------------------------
# Song data / validation
# ---------------------------------------------------------------------------

def test_all_songs_in_range():
    for song in SONGS:
        assert song.notes, f"{song.name} is empty"
        for note in song.notes:
            assert note in melodies.NOTE_RANGE, f"{song.name}: {note} out of range"


def test_song_list_matches_ticket():
    names = [s.name for s in SONGS]
    # The three headline songs must all be present (initial ticket list).
    for required in (
        "London Bridge Is Falling Down",
        "Twinkle Twinkle Little Star",
        "Mary Had a Little Lamb",
    ):
        assert required in names


def test_note_range_matches_generator():
    # Drift guard: the pure NOTE_RANGE literal must match gen_notes' output set.
    from mashpad import gen_notes
    assert set(melodies.NOTE_RANGE) == set(gen_notes.NOTE_NAMES)


# ---------------------------------------------------------------------------
# MelodySequencer
# ---------------------------------------------------------------------------

def test_steps_through_a_full_song_in_order():
    twinkle = Song("t", _parse("C C G G A A G"))
    seq = MelodySequencer([twinkle])
    got = [seq.next() for _ in range(len(twinkle.notes))]
    assert got == list(twinkle.notes)


def test_advances_to_next_song_at_boundary():
    a = Song("a", ("c5", "d5"))
    b = Song("b", ("e5", "f5"))
    seq = MelodySequencer([a, b])
    assert [seq.next() for _ in range(4)] == ["c5", "d5", "e5", "f5"]


def test_wraps_after_last_song():
    a = Song("a", ("c5",))
    b = Song("b", ("e5",))
    seq = MelodySequencer([a, b])
    # c5 (song a) → e5 (song b) → wrap → c5 (song a) again.
    assert [seq.next() for _ in range(3)] == ["c5", "e5", "c5"]


def test_current_song_tracks_boundary():
    a = Song("a", ("c5", "d5"))
    b = Song("b", ("e5",))
    seq = MelodySequencer([a, b])
    assert seq.current_song == "a"
    seq.next()                     # c5, still in a
    assert seq.current_song == "a"
    seq.next()                     # d5, last note of a → advance
    assert seq.current_song == "b"


def test_full_loop_returns_to_start():
    seq = MelodySequencer()
    total = sum(len(s.notes) for s in SONGS)
    first = seq.next()
    for _ in range(total - 1):
        seq.next()
    # After exactly one full pass over every note, the next note is the very
    # first note of the first song again.
    assert seq.next() == first
    assert seq.current_song == SONGS[0].name


def test_empty_song_list_rejected():
    with pytest.raises(ValueError):
        MelodySequencer([])


# ---------------------------------------------------------------------------
# Purity
# ---------------------------------------------------------------------------

def test_melodies_no_pygame():
    import mashpad.melodies  # noqa: F401
    assert "pygame" not in sys.modules, "melodies imported pygame!"
