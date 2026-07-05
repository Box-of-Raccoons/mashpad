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
