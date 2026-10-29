"""Windows-user DPAPI encryption for locally provisioned WeChat database keys."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(contents: bytes):
    buffer = (ctypes.c_ubyte * len(contents)).from_buffer_copy(contents)
    return DATA_BLOB(len(contents), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _transform(contents: bytes, *, protect: bool) -> bytes:
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    source, _buffer = _blob(contents)
    output = DATA_BLOB()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    if protect:
        func = crypt32.CryptProtectData
        func.argtypes = [ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(DATA_BLOB)]
        args = (ctypes.byref(source), "WXBridge database keys", None, None, None,
                flags, ctypes.byref(output))
    else:
        func = crypt32.CryptUnprotectData
        func.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                         ctypes.POINTER(DATA_BLOB)]
        args = (ctypes.byref(source), None, None, None, None,
                flags, ctypes.byref(output))
    func.restype = wintypes.BOOL
    if not func(*args):
        raise OSError(ctypes.get_last_error(), "Windows DPAPI credential operation failed")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))
