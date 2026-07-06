"""Tests for mashpad.lockdown — import safety + construction only.

The hook itself needs the real Windows OS and is verified manually by the
orchestrator; these tests deliberately never call start() so no global keyboard
hook is installed during the suite (which would be disruptive on the Windows dev
machine and a no-op on the Pi). We only assert the module is import-safe and
side-effect-free everywhere, and that a fresh Lockdown reports inactive.
"""

import sys

from mashpad import lockdown


def test_lockdown_import_no_pygame():
    """lockdown may use ctypes but must never pull in pygame."""
    import mashpad.lockdown  # noqa: F401 — ensure it is imported
    assert "pygame" not in sys.modules, "lockdown imported pygame!"


def test_lockdown_constructs_inactive():
    lock = lockdown.Lockdown()
    assert lock.active is False


def test_lockdown_stop_before_start_is_safe():
    # stop() must be a harmless no-op when the hook was never installed.
    lock = lockdown.Lockdown()
    lock.stop()
    assert lock.active is False


def test_lockdown_saved_access_starts_empty():
    # No accessibility shortcuts have been suppressed on a fresh instance.
    lock = lockdown.Lockdown()
    assert lock._saved_access == {}


def test_restore_accessibility_is_safe_with_nothing_saved():
    # With an empty save-set, restore is a pure no-op on ANY platform: it must
    # never touch ctypes / SystemParametersInfo (so it can't change the dev
    # machine's settings) and must leave the save-set empty.
    lock = lockdown.Lockdown()
    lock._restore_accessibility_shortcuts()
    assert lock._saved_access == {}


def test_stop_is_idempotent_and_clears_saved_access():
    # stop() called repeatedly (never started) stays a safe no-op and the
    # restore path leaves nothing saved behind.
    lock = lockdown.Lockdown()
    lock.stop()
    lock.stop()
    assert lock.active is False
    assert lock._saved_access == {}
