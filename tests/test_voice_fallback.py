# Tests for Audio._load_voices fallback logic:
#   - subdir packs present → flat files must NOT become "default" voice/phrases
#   - flat files only (no subdir packs) → flat files become "default"
#   - empty directory → both maps empty
#   - flat phrase files + subdir with phrase clips → "default" not in phrases
#   - flat phrase files + subdir with no phrase clips → "default" in phrases
#
# Runs each scenario in a subprocess (following the test_phrase_channel.py
# pattern) so mashpad.audio / pygame are never imported into the pytest process
# and cannot break the purity assertion in test_keymap.py.

import subprocess
import sys


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_subdir_packs_present_flat_files_not_default():
    """subdir pack + flat word files → 'default' must NOT appear in voices."""
    proc = _run(r"""
import sys, tempfile
from pathlib import Path
from mashpad.audio import Audio

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    # A curated subdir pack.
    (root / "charon").mkdir()
    (root / "charon" / "a.wav").touch()
    # Flat files from install.sh sitting beside it.
    (root / "b.wav").touch()
    (root / "c.wav").touch()

    a = Audio.__new__(Audio)
    voices, phrases = a._load_voices(root)

    if "charon" not in voices:
        print(f"FAIL: charon not in voices={list(voices)}")
        sys.exit(1)
    if "default" in voices:
        print(f"FAIL: 'default' in voices={list(voices)} — flat files leaked into rotation")
        sys.exit(1)
sys.exit(0)
""")
    assert proc.returncode == 0, (
        f"subdir+flat test failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_flat_only_becomes_default_voice():
    """No subdir packs, only flat word files → they become the 'default' voice."""
    proc = _run(r"""
import sys, tempfile
from pathlib import Path
from mashpad.audio import Audio

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    (root / "a.wav").touch()
    (root / "b.wav").touch()

    a = Audio.__new__(Audio)
    voices, phrases = a._load_voices(root)

    if "default" not in voices:
        print(f"FAIL: 'default' not in voices={list(voices)}")
        sys.exit(1)
    if list(voices.keys()) != ["default"]:
        print(f"FAIL: unexpected voices={list(voices)}")
        sys.exit(1)
sys.exit(0)
""")
    assert proc.returncode == 0, (
        f"flat-only test failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_empty_directory_empty_result():
    """Empty directory → voices and phrases are both empty."""
    proc = _run(r"""
import sys, tempfile
from pathlib import Path
from mashpad.audio import Audio

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    # Nothing here.
    a = Audio.__new__(Audio)
    voices, phrases = a._load_voices(root)

    if voices != {} or phrases != {}:
        print(f"FAIL: expected empty, got voices={list(voices)}, phrases={list(phrases)}")
        sys.exit(1)
sys.exit(0)
""")
    assert proc.returncode == 0, (
        f"empty-dir test failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_subdir_with_phrases_flat_phrases_not_default():
    """Subdir pack has phrase clips + flat phrase files → 'default' not in phrases."""
    proc = _run(r"""
import sys, tempfile
from pathlib import Path
from mashpad.audio import Audio

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    # Subdir pack with a word AND a phrase clip.
    (root / "charon").mkdir()
    (root / "charon" / "a.wav").touch()
    (root / "charon" / "phrase-hello.wav").touch()
    # Flat phrase file beside it.
    (root / "phrase-slowdown.wav").touch()

    a = Audio.__new__(Audio)
    voices, phrases = a._load_voices(root)

    if "charon" not in phrases:
        print(f"FAIL: charon not in phrases={list(phrases)}")
        sys.exit(1)
    if "default" in phrases:
        print(f"FAIL: 'default' in phrases={list(phrases)} — flat phrases leaked in")
        sys.exit(1)
sys.exit(0)
""")
    assert proc.returncode == 0, (
        f"subdir+flat-phrases test failed:\n{proc.stdout}\n{proc.stderr}"
    )


def test_flat_phrases_become_default_when_subdir_has_no_phrases():
    """Subdir pack has only word clips (no phrases) + flat phrase files → 'default' in phrases."""
    proc = _run(r"""
import sys, tempfile
from pathlib import Path
from mashpad.audio import Audio

with tempfile.TemporaryDirectory() as d:
    root = Path(d)
    # Subdir with a word clip only (no phrase clips).
    (root / "charon").mkdir()
    (root / "charon" / "a.wav").touch()
    # Flat phrase file.
    (root / "phrase-slowdown.wav").touch()

    a = Audio.__new__(Audio)
    voices, phrases = a._load_voices(root)

    # The subdir contributed words → voices should have "charon" not "default".
    if "default" in voices:
        print(f"FAIL: 'default' in voices={list(voices)}")
        sys.exit(1)
    # But phrases is empty (subdir had none) → flat phrases become "default".
    if "default" not in phrases:
        print(f"FAIL: 'default' not in phrases={list(phrases)}")
        sys.exit(1)
sys.exit(0)
""")
    assert proc.returncode == 0, (
        f"flat-phrases-with-subdir-words test failed:\n{proc.stdout}\n{proc.stderr}"
    )
