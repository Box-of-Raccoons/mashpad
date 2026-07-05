"""Tests for mashpad.paths — pure path resolution, no pygame.

Frozen behaviour is exercised by monkeypatching sys.frozen / sys._MEIPASS /
sys.executable / $APPDATA. monkeypatch auto-restores every attr and env var it
sets, so the process is left exactly as it was found (crucial: a leaked
sys.frozen=True would poison every later test's path resolution).
"""

import sys
from pathlib import Path

from mashpad import paths


def _repo_root() -> Path:
    """Repo root = parent of the mashpad package dir = parent of paths.py's dir."""
    return Path(paths.__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Not frozen (dev + Pi): unchanged historical behaviour
# ---------------------------------------------------------------------------

def test_not_frozen_in_test_env():
    # Sanity: the test process itself is a normal interpreter, not a bundle.
    assert not getattr(sys, "frozen", False)


def test_app_root_not_frozen_is_repo_root():
    assert paths.app_root() == _repo_root()


def test_data_dir_not_frozen_equals_app_root():
    assert paths.data_dir() == paths.app_root()


def test_data_dir_not_frozen_is_repo_root():
    assert paths.data_dir() == _repo_root()


# ---------------------------------------------------------------------------
# Frozen (PyInstaller bundle): app_root
# ---------------------------------------------------------------------------

def test_app_root_frozen_onefile_uses_meipass(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert paths.app_root() == bundle


def test_app_root_frozen_onedir_uses_exe_dir(monkeypatch, tmp_path):
    # One-dir builds have no _MEIPASS → fall back to the executable's dir.
    exedir = tmp_path / "app"
    exedir.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(sys, "executable", str(exedir / "mashpad.exe"))
    assert paths.app_root() == exedir


# ---------------------------------------------------------------------------
# Frozen: data_dir (writable, must be created)
# ---------------------------------------------------------------------------

def test_data_dir_frozen_uses_appdata_and_creates(monkeypatch, tmp_path):
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))

    d = paths.data_dir()
    assert d == appdata / "mashpad"
    assert d.is_dir()  # data_dir() must create it


def test_data_dir_frozen_missing_appdata_falls_back_to_home(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    d = paths.data_dir()
    assert d == fake_home / "mashpad"
    assert d.is_dir()


def test_data_dir_frozen_created_when_parent_missing(monkeypatch, tmp_path):
    # APPDATA itself doesn't exist yet → mkdir(parents=True) still creates the tree.
    appdata = tmp_path / "does_not_exist_yet" / "Roaming"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("APPDATA", str(appdata))

    d = paths.data_dir()
    assert d == appdata / "mashpad"
    assert d.is_dir()


# ---------------------------------------------------------------------------
# Purity: paths must not import pygame
# ---------------------------------------------------------------------------

def test_paths_no_pygame():
    """paths is a pure stdlib module — it must not pull in pygame."""
    import mashpad.paths  # noqa: F401 — ensure it is imported
    assert "pygame" not in sys.modules, "paths imported pygame!"
