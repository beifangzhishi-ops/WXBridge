"""Read-only, fail-closed local WeChat account discovery for API routing.

Process presence is *not* proof of an authenticated WeChat login. The
reported state is deliberately called `candidate`, never `online`.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re

from .keyvault import KeyVaultError, unseal_keys


def wechat_process_state() -> str:
    """Use Windows process metadata only; never inspect process memory/UI."""
    if os.name != "nt":
        return "unknown"
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
        return "unknown"
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(handle, ctypes.byref(entry)):
            return "unknown"
        while True:
            if entry.szExeFile.casefold() in ("weixin.exe", "wechat.exe"):
                return "present"
            if not kernel.Process32NextW(handle, ctypes.byref(entry)):
                return "absent"
    finally:
        kernel.CloseHandle(handle)


def local_identity() -> dict:
    process = wechat_process_state()
    account = None
    try:
        storage, _fingerprint, _keys = unseal_keys()
        # Match upstream WeChatDB.wxid account-directory suffix handling.
        account = re.sub(r"_\w{4}$", "", storage)
    except (KeyVaultError, OSError, ValueError):
        pass
    # Do not claim login from a process name and a potentially stale vault.
    state = ("offline" if process == "absent" else
             "candidate" if process == "present" and account else "unknown")
    return {"state": state, "accountId": account,
            "process": process, "loginVerified": False}
