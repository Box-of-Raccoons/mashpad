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
        """Remove the hook and stop the pump thread. Safe to call when never started."""
        if self._thread is None:
            self._active = False
            return
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
        self._active = False

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
