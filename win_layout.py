"""
Win32 keyboard-layout access layer.

This module isolates ALL native Windows interaction. It exposes a clean,
typed API used by the rest of the application so that the GUI and worker
code never touch ctypes directly.

Key concepts:
- An HKL (input locale identifier) is a handle whose low word is the
  language identifier (LANGID) and whose high word identifies the
  physical keyboard layout.
- Keyboard layout is tracked PER THREAD. We therefore always operate on
  the thread that owns the current foreground window.
"""

from __future__ import annotations

import ctypes
import locale
from ctypes import wintypes
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Win32 function prototypes
# ---------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# GetKeyboardLayoutList(int nBuff, HKL* lpList) -> int
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(wintypes.HKL)]
user32.GetKeyboardLayoutList.restype = ctypes.c_int

# GetForegroundWindow() -> HWND
user32.GetForegroundWindow.restype = wintypes.HWND

# GetWindowThreadProcessId(HWND, LPDWORD) -> DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

# GetKeyboardLayout(DWORD idThread) -> HKL
user32.GetKeyboardLayout.argtypes = [wintypes.DWORD]
user32.GetKeyboardLayout.restype = wintypes.HKL

# ActivateKeyboardLayout(HKL, UINT) -> HKL
user32.ActivateKeyboardLayout.argtypes = [wintypes.HKL, wintypes.UINT]
user32.ActivateKeyboardLayout.restype = wintypes.HKL

# LoadKeyboardLayoutW(LPCWSTR pwszKLID, UINT Flags) -> HKL
user32.LoadKeyboardLayoutW.argtypes = [wintypes.LPCWSTR, wintypes.UINT]
user32.LoadKeyboardLayoutW.restype = wintypes.HKL

# PostMessageW(HWND, UINT, WPARAM, LPARAM) -> BOOL
user32.PostMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
user32.PostMessageW.restype = wintypes.BOOL

# GetLocaleInfoW(LCID, LCTYPE, LPWSTR, int) -> int
kernel32.GetLocaleInfoW.argtypes = [
    wintypes.LCID, wintypes.DWORD, wintypes.LPWSTR, ctypes.c_int
]
kernel32.GetLocaleInfoW.restype = ctypes.c_int

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WM_INPUTLANGCHANGEREQUEST = 0x0050
INPUTLANGCHANGE_FORWARD = 0x0002
KLF_ACTIVATE = 0x00000001
KLF_SETFORPROCESS = 0x00000100
LOCALE_SLOCALIZEDDISPLAYNAME = 0x00000002
LOCALE_SLANGUAGE = 0x00000002  # localized language + region name


@dataclass(frozen=True)
class KeyboardLayout:
    """Immutable description of an installed keyboard layout."""

    hkl: int           # Full input-locale identifier (HKL as integer)
    langid: int        # Low word of the HKL (LANGID / primary locale)
    display_name: str  # Human-friendly name, e.g. "English (United States)"

    @property
    def klid(self) -> str:
        """Return the 8-hex-digit Keyboard Layout ID used by LoadKeyboardLayout."""
        # The KLID is the language identifier zero-padded to 8 hex digits.
        return f"{self.langid:08x}"


def _hkl_to_int(hkl) -> int:
    """Normalise an HKL handle (which may be None/c_void_p) to a plain int."""
    if hkl is None:
        return 0
    return int(ctypes.cast(hkl, ctypes.c_void_p).value or 0)


def _language_name_from_langid(langid: int) -> str:
    """
    Resolve a friendly language name for a LANGID using the OS locale tables.
    Falls back gracefully to a hex identifier if resolution fails.
    """
    buffer = ctypes.create_unicode_buffer(256)
    # The LCID for a base layout is just the LANGID for our display purposes.
    written = kernel32.GetLocaleInfoW(
        langid & 0xFFFF, LOCALE_SLANGUAGE, buffer, len(buffer)
    )
    if written > 0 and buffer.value.strip():
        return buffer.value
    return f"Layout 0x{langid:04X}"


def list_installed_layouts() -> list[KeyboardLayout]:
    """
    Enumerate every keyboard layout currently installed on the system.

    Returns a de-duplicated, name-sorted list. Always returns at least the
    current layout so the UI is never empty.
    """
    count = user32.GetKeyboardLayoutList(0, None)
    if count <= 0:
        # Fallback: at minimum report the foreground layout.
        current = get_foreground_layout_hkl()
        langid = current & 0xFFFF
        return [
            KeyboardLayout(current, langid, _language_name_from_langid(langid))
        ]

    array_type = wintypes.HKL * count
    buffer = array_type()
    written = user32.GetKeyboardLayoutList(count, buffer)

    seen: dict[int, KeyboardLayout] = {}
    for i in range(written):
        hkl = _hkl_to_int(buffer[i])
        if hkl == 0:
            continue
        langid = hkl & 0xFFFF
        # De-duplicate by langid so we don't list the same language twice.
        if langid in seen:
            continue
        seen[langid] = KeyboardLayout(
            hkl=hkl,
            langid=langid,
            display_name=_language_name_from_langid(langid),
        )

    layouts = sorted(seen.values(), key=lambda l: l.display_name.lower())
    return layouts


def get_foreground_window():
    """Return the HWND of the current foreground window (may be 0)."""
    return user32.GetForegroundWindow()


def get_foreground_thread_id(hwnd) -> int:
    """Return the thread ID owning the given window."""
    if not hwnd:
        return 0
    pid = wintypes.DWORD(0)
    return user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))


def get_foreground_layout_hkl() -> int:
    """
    Return the active keyboard layout (HKL as int) of the foreground window's
    thread. If there is no foreground window, falls back to thread 0.
    """
    hwnd = get_foreground_window()
    thread_id = get_foreground_thread_id(hwnd)
    return _hkl_to_int(user32.GetKeyboardLayout(thread_id))


def ensure_layout_loaded(layout: KeyboardLayout) -> int:
    """
    Ensure the requested layout is loaded into the system and return its HKL.
    LoadKeyboardLayout is idempotent for already-loaded layouts.
    """
    hkl = user32.LoadKeyboardLayoutW(layout.klid, KLF_ACTIVATE)
    loaded = _hkl_to_int(hkl)
    return loaded or layout.hkl


def enforce_layout(layout: KeyboardLayout) -> bool:
    """
    Force the foreground window to the requested layout.

    Strategy (most reliable first):
      1. Post WM_INPUTLANGCHANGEREQUEST to the foreground window. This is the
         official, app-cooperative way to change layout and is what well-behaved
         games respect.
      2. Call ActivateKeyboardLayout as a belt-and-braces fallback.

    Returns True if at least one mechanism was invoked successfully.
    """
    hwnd = get_foreground_window()
    if not hwnd:
        return False

    target_hkl = layout.hkl or ensure_layout_loaded(layout)

    posted = user32.PostMessageW(
        hwnd,
        WM_INPUTLANGCHANGEREQUEST,
        INPUTLANGCHANGE_FORWARD,        # wParam flags
        wintypes.LPARAM(target_hkl),    # lParam = target HKL
    )

    # Fallback path. ActivateKeyboardLayout affects the calling thread, but
    # combined with the posted message above it materially improves reliability
    # against stubborn applications.
    user32.ActivateKeyboardLayout(wintypes.HKL(target_hkl), KLF_ACTIVATE)

    return bool(posted)


def langname_for_hkl(hkl: int) -> str:
    """Friendly name for an arbitrary HKL value (used by the live status)."""
    return _language_name_from_langid(hkl & 0xFFFF)
