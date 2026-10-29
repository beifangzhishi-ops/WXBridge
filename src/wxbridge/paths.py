"""Writable per-user application paths; nothing private lives in the source tree."""

import os
from pathlib import Path
from .runtime import app_root


def state_directory() -> Path:
    explicit = os.environ.get("WXBRIDGE_STATE_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    # Running from a source checkout in a restricted workspace? Keep its
    # private state under the checkout, covered by the .gitignore rule.
    checkout = app_root()
    # A portable frozen EXE placed inside the WXBridge source checkout
    # reuses the existing DPAPI cache. An EXE copied to another directory
    # uses the installed-style per-user app data path by default.
    if (checkout / "pyproject.toml").is_file() and (checkout / ".gitignore").is_file():
        return checkout / ".state"
    # An installed distribution has no writable project root, so use user
    # application data instead.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "WXBridge"
    return Path.home() / ".local" / "state" / "wxbridge"


STATE = state_directory()
