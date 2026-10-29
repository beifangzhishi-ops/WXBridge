"""Safe, metadata-only WeChat environment diagnosis.

Never opens a WeChat DB, extracts a key, reads messages or touches processes.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

MAX_FILES = 10000


def check_database_candidates(config_root: Path) -> tuple[int, bool]:
    """Count file names with a .db suffix, without opening them.

    A bound prevents excessive traversal of unexpected directory trees.
    """
    seen = 0
    count = 0
    try:
        for _root, dirs, files in os.walk(config_root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for filename in files:
                seen += 1
                if filename.lower().endswith(".db"):
                    count += 1
                if seen >= MAX_FILES:
                    return count, True
    except OSError:
        return count, True
    return count, False


def preflight(*, appdata: str | None = None) -> dict:
    """Return deliberately coarse signals, never identifying the account."""
    if appdata is None:
        appdata = os.environ.get("APPDATA")
    root = Path(appdata) / "Tencent" / "xwechat" if appdata else None
    config_found = bool(root and (root / "config").is_dir())
    count, truncated = check_database_candidates(root) if root and root.is_dir() else (0, False)
    return {
        "source": "WeChat 4.x local files",
        "platformSupported": sys.platform == "win32",
        "configPresent": config_found,
        "candidateDbFileCount": count,
        "scanTruncated": truncated,
        "databaseReadable": None,
        "realMessageReadVerified": False,
        "processMemoryReadAttempted": False,
        "messageContentReadAttempted": False,
        "note": (
            "File existence is not proof of decryptability or correct account "
            "binding. No chat database was opened."
        ),
    }
