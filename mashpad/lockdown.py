# mashpad/lockdown.py — OS-level keyboard lockdown (Windows only, no-op elsewhere).
#
# In fullscreen on Windows a baby can hit the Windows key, Alt+Tab, Alt+F4,
# Alt+Esc or Ctrl+Esc and escape the app (or shut it down). This installs a
# WH_KEYBOARD_LL low-level keyboard hook via ctypes — no pywin32 dependency —
# that swallows exactly those combos while the app runs, mirroring the original
# BabySmash. Ctrl+Alt+Del is a Secure Attention Sequence the OS reserves; it
# CANNOT and MUST NOT be intercepted (and this hook never sees it).
#
# On every non-Windows platform, and on ANY ctypes/OS failure, start() logs one
# line and stays inactive — it NEVER crashes the app. So Raspberry Pi / Linux
# behaviour is byte-for-byte unchanged (a silent no-op). Importing this module
# is safe and side-effect-free everywhere: it imports only `sys` + `threading`
# at module load and defers all ctypes/wintypes work into the Windows-only code
# path (some old CPython builds can't import ctypes.wintypes off Windows). It
# must NEVER import pygame.

from __future__ import annotations

import sys
import threading

# --- Win32 constants ---------------------------------------------------------

WH_KEYBOARD_LL = 13     # low-level keyboard hook id
HC_ACTION = 0           # nCode value: lParam/wParam hold a real event
WM_QUIT = 0x0012        # posted to the pump thread to end GetMessageW loop

# Virtual-key codes.
VK_TAB = 0x09
VK_CONTROL = 0x11
VK_ESCAPE = 0x1B
VK_F4 = 0x73
VK_LWIN = 0x5B
VK_RWIN = 0x5C

# KBDLLHOOKSTRUCT.flags bit: the Alt key was down when the key was struck.
LLKHF_ALTDOWN = 0x20

# --- Accessibility shortcut suppression (SystemParametersInfo) ---------------
# A baby hammering Shift 5x (StickyKeys), holding Shift ~8s (FilterKeys), or
# hitting NumLock (ToggleKeys) pops an OS dialog OVER the fullscreen app and
# steals focus — the LL hook can't stop these because they trigger on plain
# Shift, which we deliberately pass through. So while locked down we clear only
# the *hotkey* activation flags (session-only, never persisted to the registry),
# and only for features the user hasn't already turned on. Mirrors BabySmash.
SPI_GETSTICKYKEYS = 0x003A
SPI_SETSTICKYKEYS = 0x003B
SPI_GETFILTERKEYS = 0x0032
SPI_SETFILTERKEYS = 0x0033
SPI_GETTOGGLEKEYS = 0x0034
SPI_SETTOGGLEKEYS = 0x0035

# "feature is currently ON" bit — if set, the user genuinely uses it: leave it.
SKF_STICKYKEYSON = 0x00000001
FKF_FILTERKEYSON = 0x00000001
TKF_TOGGLEKEYSON = 0x00000001

# Hotkey-activation bits we clear so the Shift/NumLock gesture stops popping the
# dialog. Same bit values across the SKF_/FKF_/TKF_ families.
ACCESS_HOTKEYACTIVE = 0x00000004   # the keyboard gesture can turn the feature on
ACCESS_CONFIRMHOTKEY = 0x00000008  # show the confirmation dialog on the gesture
ACCESS_HOTKEYSOUND = 0x00000010    # play the rising/falling siren on the gesture
_ACCESS_HOTKEY_BITS = ACCESS_HOTKEYACTIVE | ACCESS_CONFIRMHOTKEY | ACCESS_HOTKEYSOUND

# GetAsyncKeyState high bit → the key is currently down.
_KEY_DOWN_BIT = 0x8000

# Module-level reference to the live HOOKPROC. ctypes does NOT keep the Python
# callback object alive on its behalf, so if the only reference were a local it
# could be garbage-collected while Windows still holds the hook — a classic
# ctypes crash. Anchoring it here keeps it alive for the hook's whole lifetime.
_HOOK_PROC_REF = None


class Lockdown:
    """Swallows OS keyboard-escape combos on Windows; a no-op everywhere else.

    Owns one low-level keyboard hook installed on a dedicated daemon thread (an
    LL hook must be serviced by a message pump on its installing thread).
    start()/stop() are idempotent. `active` reflects whether the hook is live.
    """

    def __init__(self) -> None:
        self._active = False
        self._thread = None
        self._thread_id = None   # GetCurrentThreadId of the pump thread
        self._hook = None        # the HHOOK handle
        self._user32 = None      # cached WinDLL for PostThreadMessageW from stop()
        # Accessibility shortcuts we suppressed: label -> (set_action, size, raw
        # original struct bytes) so stop() can SPI_SET each back verbatim. Empty
        # dict = nothing to restore (also the idempotency guard).
        self._saved_access = {}

    @property
    def active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------ start

    def start(self) -> None:
        """Install the keyboard hook. No-op (with a log line) off Windows / on failure."""
        if self._active:
            return
        if sys.platform != "win32":
            print("[mashpad lockdown] non-Windows platform; keyboard lockdown disabled")
            return
        # Suppress the accessibility-shortcut popups first, on THIS (calling)
        # thread — SystemParametersInfo has no thread affinity, so it needn't go
        # on the pump thread and must stay out of the hook callback. It applies
        # even if the hook below fails to install (stop() still restores).
        self._suppress_accessibility_shortcuts()
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(ready,), name="mashpad-lockdown", daemon=True
        )
        self._thread.start()
        # Block until the pump thread has installed the hook (or failed) so that
        # `active` is trustworthy the moment start() returns.
        ready.wait(timeout=5.0)

    # ------------------------------------------------------------------- stop

    def stop(self) -> None:
        """Remove the hook and stop the pump thread. Safe to call when never started.

        Always restores the accessibility shortcuts we changed — even if the hook
        never installed — so a parent's session settings are never left altered.
        """
        if self._thread is not None:
            # End the pump thread's GetMessageW loop; it then unhooks on its own
            # (installing thread) before exiting.
            if self._thread_id and self._user32 is not None:
                try:
                    self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
                except Exception as exc:  # noqa: BLE001 — never crash on teardown
                    print(f"[mashpad lockdown] error posting WM_QUIT ({exc})")
            self._thread.join(timeout=5.0)
            self._thread = None
            self._thread_id = None
            self._user32 = None
        # Restore regardless of hook state; idempotent (clears the saved dict).
        self._restore_accessibility_shortcuts()
        self._active = False

    # ------------------------------------------- accessibility shortcut guard

    def _suppress_accessibility_shortcuts(self) -> None:
        """Clear the Sticky/Filter/Toggle Keys HOTKEY flags (Windows, session-only).

        For each feature: read the current struct; if the feature is already ON
        (the user relies on it) leave it entirely; otherwise save the original
        struct and SPI_SET a copy with the hotkey-activation bits cleared. Uses
        fWinIni=0 so nothing is written to the registry. Wrapped so any failure
        logs one line and never crashes the app; a no-op off Windows.
        """
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SystemParametersInfoW.argtypes = [
                wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
            ]
            user32.SystemParametersInfoW.restype = wintypes.BOOL

            # STICKYKEYS / TOGGLEKEYS are {DWORD cbSize; DWORD dwFlags}.
            class STICKYKEYS(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD)]

            class TOGGLEKEYS(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD)]

            # FILTERKEYS carries four extra timing fields we must round-trip.
            class FILTERKEYS(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.UINT),
                    ("dwFlags", wintypes.DWORD),
                    ("iWaitMSec", wintypes.DWORD),
                    ("iDelayMSec", wintypes.DWORD),
                    ("iRepeatMSec", wintypes.DWORD),
                    ("iBounceMSec", wintypes.DWORD),
                ]

            # (label, GET action, SET action, struct type, "feature is ON" bit).
            specs = [
                ("stickykeys", SPI_GETSTICKYKEYS, SPI_SETSTICKYKEYS,
                 STICKYKEYS, SKF_STICKYKEYSON),
                ("filterkeys", SPI_GETFILTERKEYS, SPI_SETFILTERKEYS,
                 FILTERKEYS, FKF_FILTERKEYSON),
                ("togglekeys", SPI_GETTOGGLEKEYS, SPI_SETTOGGLEKEYS,
                 TOGGLEKEYS, TKF_TOGGLEKEYSON),
            ]
            for label, get_action, set_action, struct_type, on_bit in specs:
                size = ctypes.sizeof(struct_type)
                st = struct_type()
                st.cbSize = size
                if not user32.SystemParametersInfoW(
                    get_action, size, ctypes.byref(st), 0
                ):
                    continue  # couldn't read this one — leave it untouched
                if st.dwFlags & on_bit:
                    continue  # user actively uses it → never fight them
                if not (st.dwFlags & _ACCESS_HOTKEY_BITS):
                    continue  # hotkey already disabled — nothing to do
                # Save the FULL original struct so restore round-trips every field.
                self._saved_access[label] = (set_action, size, bytes(st))
                new = struct_type.from_buffer_copy(st)
                new.dwFlags = st.dwFlags & ~_ACCESS_HOTKEY_BITS
                user32.SystemParametersInfoW(
                    set_action, size, ctypes.byref(new), 0
                )
        except Exception as exc:  # noqa: BLE001 — never crash on this convenience
            print(f"[mashpad lockdown] could not adjust accessibility shortcuts ({exc})")

    def _restore_accessibility_shortcuts(self) -> None:
        """SPI_SET each saved struct back verbatim. Idempotent; a no-op if nothing saved."""
        if not self._saved_access:
            return
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.SystemParametersInfoW.argtypes = [
                wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
            ]
            user32.SystemParametersInfoW.restype = wintypes.BOOL
            for set_action, size, raw in self._saved_access.values():
                try:
                    buf = ctypes.create_string_buffer(raw, size)
                    user32.SystemParametersInfoW(set_action, size, buf, 0)
                except Exception as exc:  # noqa: BLE001 — one bad restore mustn't stop the rest
                    print(f"[mashpad lockdown] error restoring accessibility flags ({exc})")
        except Exception as exc:  # noqa: BLE001 — never crash on teardown
            print(f"[mashpad lockdown] could not restore accessibility shortcuts ({exc})")
        finally:
            self._saved_access = {}  # idempotent: a second stop() does nothing

    # ------------------------------------------------------- pump thread body

    def _run(self, ready) -> None:
        """Thread entry: install + pump; log and stay inactive on any failure."""
        try:
            self._pump(ready)
        except Exception as exc:  # noqa: BLE001 — any ctypes/OS failure → no lockdown
            print(f"[mashpad lockdown] could not install keyboard hook ({exc}); disabled")
            self._active = False
            ready.set()

    def _pump(self, ready) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # LRESULT is pointer-width signed. Using LPARAM (LONG_PTR) for it — and
        # for every handle/param below — is what keeps the LL-hook callback from
        # crashing on x64, where an int-width return truncates the pointer.
        LRESULT = wintypes.LPARAM
        HHOOK = wintypes.HANDLE
        HINSTANCE = wintypes.HANDLE
        ULONG_PTR = wintypes.WPARAM

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ("vkCode", wintypes.DWORD),
                ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", ULONG_PTR),
            ]

        HOOKPROC = ctypes.WINFUNCTYPE(
            LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        # --- prototypes: argtypes/restype for EVERY call we make (x64 safety) ---
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, HOOKPROC, HINSTANCE, wintypes.DWORD
        ]
        user32.SetWindowsHookExW.restype = HHOOK
        user32.CallNextHookEx.argtypes = [
            HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.CallNextHookEx.restype = LRESULT
        user32.UnhookWindowsHookEx.argtypes = [HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
        ]
        user32.GetMessageW.restype = ctypes.c_int  # 0 on WM_QUIT, -1 on error
        user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user32.GetAsyncKeyState.restype = wintypes.SHORT
        user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        ]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = HINSTANCE
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

        def _low_level_keyboard_proc(nCode, wParam, lParam):
            # Only inspect real key events; forward everything else untouched.
            if nCode == HC_ACTION:
                kb = ctypes.cast(
                    lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)
                ).contents
                vk = kb.vkCode
                alt_down = bool(kb.flags & LLKHF_ALTDOWN)
                if vk in (VK_LWIN, VK_RWIN):
                    return 1  # swallow the Windows key (Start menu / Win+combos)
                if alt_down and vk in (VK_TAB, VK_F4, VK_ESCAPE):
                    return 1  # Alt+Tab (switch), Alt+F4 (close), Alt+Esc (cycle)
                if vk == VK_ESCAPE and (
                    user32.GetAsyncKeyState(VK_CONTROL) & _KEY_DOWN_BIT
                ):
                    return 1  # Ctrl+Esc (opens the Start menu)
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        proc = HOOKPROC(_low_level_keyboard_proc)
        # Anchor the callback module-level so it is not GC'd while hooked.
        global _HOOK_PROC_REF
        _HOOK_PROC_REF = proc

        self._user32 = user32
        self._thread_id = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, proc, kernel32.GetModuleHandleW(None), 0
        )
        if not hook:
            err = ctypes.get_last_error()
            print(f"[mashpad lockdown] SetWindowsHookExW failed (err {err}); disabled")
            _HOOK_PROC_REF = None
            self._active = False
            ready.set()
            return

        self._hook = hook
        self._active = True
        ready.set()

        # Message pump: WH_KEYBOARD_LL events are delivered by dispatching the
        # installing thread's message queue. GetMessageW blocks until a message
        # arrives; it returns 0 on the WM_QUIT posted by stop() and -1 on error.
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

        user32.UnhookWindowsHookEx(hook)
        self._hook = None
        self._active = False
        _HOOK_PROC_REF = None
