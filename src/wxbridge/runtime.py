"""Runtime location and exact upstream source authentication.

Frozen EXEs include only the three reviewed upstream source files used by
read-only adapters. Source checkouts retain their Git HEAD/object checks.
No bundled WeChat keys, chat messages, or user-specific configuration.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys


SOURCE_HASHES = {
    "db.py": "8afe896bd6ee61c2f2947af111346373c2eaa98710c20f2e0a969f87bf57b125",
    "media.py": "18b55a7a1833de2de9634002ac42623a66ca8e5d476d0efcf0d6d83e12865333",
    "moment.py": "351211156480f410ac299c2af03d2b33536d7e7eda079825e05e87ca6503361f",
}


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    # PyInstaller's __file__ points inside _MEIPASS, not beside the EXE.
    if frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def embedded_root() -> Path:
    if not frozen():
        raise RuntimeError("not_a_frozen_executable")
    return Path(sys._MEIPASS) / "upstream"


def embedded_source_is_verified(source: Path) -> bool:
    if not frozen() or source.name not in SOURCE_HASHES:
        return False
    try:
        if source.parent != embedded_root() / "wechatauto":
            return False
        return hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_HASHES[source.name]
    except OSError:
        return False
