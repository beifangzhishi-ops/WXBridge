"""Connect a console-free Windows executable to its caller's output pipes.

The Windows GUI subsystem avoids flashing a console window. Python's windowed
bootloader leaves sys.stdout/sys.stderr unset, so restore only inherited
standard handles if a caller (PowerShell, CCM or Codex) supplied them.
"""

from __future__ import annotations

import os
import sys


def restore_inherited_output() -> None:
    if os.name != "nt":
        return
    import ctypes
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetStdHandle.argtypes = (ctypes.c_ulong,)
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetFileType.argtypes = (ctypes.c_void_p,)
    kernel.GetFileType.restype = ctypes.c_ulong

    for name, handle_id in (("stdout", -11), ("stderr", -12)):
        if getattr(sys, name) is not None:
            continue
        handle = kernel.GetStdHandle(handle_id)
        if handle not in (None, 0, ctypes.c_void_p(-1).value) and kernel.GetFileType(handle):
            try:
                fd = msvcrt.open_osfhandle(handle, os.O_WRONLY)
                setattr(sys, name, os.fdopen(
                    fd, "w", encoding="utf-8", errors="replace", buffering=1))
                continue
            except OSError:
                pass
        # Double-click launch has no stdout reader. Never show a dialog.
        setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
