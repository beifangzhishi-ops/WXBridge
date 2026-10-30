"""Read-only WeChat account discovery with strictly binary login state.

The main window may be hidden in the system tray while WeChat is logged in.
Inspecting a hidden large main window is useful positive local evidence
provided no login dialog is present. A process or old key vault alone is
not enough; ambiguous UI is always offline.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re

from .keyvault import KeyVaultError, unseal_keys


def _wechat_process_ids() -> set[int] | None:
    """Find WeChat PIDs from the Windows process list, without memory reads."""
    if os.name != "nt":
        return None
    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
        ]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32NextW.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    invalid = ctypes.c_void_p(-1).value
    if not handle or handle == invalid:
        return None
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
            return None
        pids = set()
        while True:
            if entry.szExeFile.casefold() in ("weixin.exe", "wechat.exe"):
                pids.add(int(entry.th32ProcessID))
            if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                return pids
    finally:
        kernel.CloseHandle(handle)


def wechat_process_state() -> str:
    pids = _wechat_process_ids()
    return "unknown" if pids is None else "present" if pids else "absent"


def _window_evidence(process_count: int, sizes: list[tuple[int, int]],
                     hidden_sizes: list[tuple[int, int]] | None = None) -> str:
    """Read-only geometry heuristic, including tray-hidden main windows.

    A visible login dialog takes precedence over a hidden main window; logout
    may retain a previously hidden window whose content is no longer valid.
    """
    hidden_sizes = hidden_sizes or []
    def is_main(size):
        return size[0] >= 650 and size[1] >= 480

    def is_login(size):
        return 200 <= size[0] <= 480 and 200 <= size[1] <= 550

    if any(is_main(size) for size in sizes):
        return "main_window"
    # WeChat 4.x may show two overlapping small login dialogs on logout.
    if sizes and len(sizes) <= 3 and all(is_login(size) for size in sizes):
        return "login_window"
    if any(is_main(size) for size in hidden_sizes) and not sizes:
        return "main_window"
    return "unknown"


def wechat_window_state() -> str:
    """Inspect only window class/geometry; no screenshot or UI automation."""
    pids = _wechat_process_ids()
    if pids is None:
        return "unknown"
    if not pids:
        return "absent"
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    class Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                    ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class Point(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class WindowPlacement(ctypes.Structure):
        _fields_ = [("length", wintypes.UINT), ("flags", wintypes.UINT),
                    ("showCmd", wintypes.UINT), ("minPosition", Point),
                    ("maxPosition", Point), ("normalPosition", Rect)]

    cb_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = (cb_type, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(Rect))
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.GetWindowPlacement.argtypes = (wintypes.HWND,
                                         ctypes.POINTER(WindowPlacement))
    sizes: list[tuple[int, int]] = []
    hidden_sizes: list[tuple[int, int]] = []

    @cb_type
    def on_window(hwnd, _param):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value not in pids:
            return True
        name = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, name, len(name))
        # Only top-level WeChat windows, not unrelated utility windows.
        if name.value != "WeChatMainWndForPC" and not name.value.endswith("QWindowIcon"):
            return True
        bounds = Rect()
        if user32.IsIconic(hwnd):
            placement = WindowPlacement()
            placement.length = ctypes.sizeof(WindowPlacement)
            if user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
                bounds = placement.normalPosition
            else:
                return True
        elif not user32.GetWindowRect(hwnd, ctypes.byref(bounds)):
            return True
        if bounds.right > bounds.left and bounds.bottom > bounds.top:
            size = (bounds.right - bounds.left, bounds.bottom - bounds.top)
            (sizes if user32.IsWindowVisible(hwnd) else hidden_sizes).append(size)
        return True

    if not user32.EnumWindows(on_window, 0):
        return "unknown"
    return _window_evidence(len(pids), sizes, hidden_sizes)


def local_identity() -> dict:
    process = wechat_process_state()
    window = wechat_window_state() if process == "present" else "absent"
    account = None
    try:
        storage, _fingerprint, _keys = unseal_keys()
        # Match upstream WeChatDB.wxid account-directory suffix handling.
        account = re.sub(r"_\w{4}$", "", storage)
    except (KeyVaultError, OSError, ValueError):
        pass
    # A cached account/Weixin.exe alone can survive logout. An observed
    # large main window (visible or tray-hidden), without a login dialog,
    # is positive heuristic evidence but never a server-side verification.
    state = ("online" if process == "present" and window == "main_window" and account
             else "offline")
    return {"state": state, "accountId": account,
            "process": process, "windowState": window, "loginVerified": False}
