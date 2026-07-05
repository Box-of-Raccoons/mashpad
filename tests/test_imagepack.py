"""Tests for mashpad.imagepack — pure logic, no pygame."""

import sys
from pathlib import Path

import pytest

from mashpad.imagepack import ImageEntry, scan, spoken_word


# ---------------------------------------------------------------------------
# spoken_word edge cases
# ---------------------------------------------------------------------------

def test_spoken_word_strips_trailing_digits():
    assert spoken_word("raccoon3") == "raccoon"


def test_spoken_word_no_trailing_digits():
    assert spoken_word("wave") == "wave"


def test_spoken_word_digit_only_kept():
    # "7" stripped to "" → keep original stem
    assert spoken_word("7") == "7"


def test_spoken_word_alpha_then_digits():
    assert spoken_word("abc123") == "abc"


def test_spoken_word_all_digits_kept():
    # "123" stripped to "" → keep "123"
    assert spoken_word("123") == "123"


def test_spoken_word_single_letter():
    assert spoken_word("a") == "a"


# ---------------------------------------------------------------------------
# scan — missing / empty directory
# ---------------------------------------------------------------------------

def test_scan_missing_dir_returns_empty(tmp_path):
    missing = tmp_path / "no_such_dir"
    assert scan(missing) == []


def test_scan_empty_dir_returns_empty(tmp_path):
    assert scan(tmp_path) == []


# ---------------------------------------------------------------------------
# scan — sorting and ImageEntry structure
# ---------------------------------------------------------------------------

def test_scan_sorted_names(tmp_path):
    # Create PNGs in reverse alphabetical order on disk; scan must sort them.
    (tmp_path / "raccoon3.png").write_bytes(b"")
    (tmp_path / "raccoon1.png").write_bytes(b"")
    (tmp_path / "wave.png").write_bytes(b"")

    entries = scan(tmp_path)
    assert [e.name for e in entries] == ["raccoon1", "raccoon3", "wave"]


def test_scan_entry_count(tmp_path):
    (tmp_path / "a.png").write_bytes(b"")
    (tmp_path / "b.png").write_bytes(b"")
    assert len(scan(tmp_path)) == 2


def test_scan_path_correct(tmp_path):
    (tmp_path / "img.png").write_bytes(b"")
    entries = scan(tmp_path)
    assert entries[0].path == tmp_path / "img.png"


def test_scan_spoken_word_folding(tmp_path):
    (tmp_path / "raccoon3.png").write_bytes(b"")
    (tmp_path / "wave.png").write_bytes(b"")
    (tmp_path / "7.png").write_bytes(b"")
    (tmp_path / "abc123.png").write_bytes(b"")

    by_name = {e.name: e for e in scan(tmp_path)}
    assert by_name["raccoon3"].spoken == "raccoon"
    assert by_name["wave"].spoken == "wave"
    assert by_name["7"].spoken == "7"
    assert by_name["abc123"].spoken == "abc"


def test_scan_ignores_non_png(tmp_path):
    (tmp_path / "img.jpg").write_bytes(b"")
    (tmp_path / "img.gif").write_bytes(b"")
    (tmp_path / "img.png").write_bytes(b"")
    entries = scan(tmp_path)
    assert len(entries) == 1
    assert entries[0].name == "img"


# ---------------------------------------------------------------------------
# Purity: imagepack must not import pygame
# ---------------------------------------------------------------------------

def test_imagepack_no_pygame():
    """imagepack is a pure module — it must not pull in pygame."""
    import mashpad.imagepack  # noqa: F401 — ensure it is imported
    assert "pygame" not in sys.modules, "imagepack imported pygame!"
