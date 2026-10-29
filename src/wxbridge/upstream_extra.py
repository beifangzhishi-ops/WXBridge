"""Verified, UI-free loading of selected original upstream media/moment code.

Never import the full upstream package. Its __init__ loads UI and sending
modules. All extra source files must exactly match the pinned Git commit.
"""

from __future__ import annotations

import ast
import hashlib
import html
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import types

from .snapshot import PIN, SnapshotError, _upstream_dir
from .runtime import frozen, embedded_source_is_verified


def _source(name: str) -> Path:
    if name not in ("media.py", "moment.py"):
        raise SnapshotError("unapproved_extra_module")
    root = _upstream_dir()
    source = root / "wechatauto" / name
    if not source.is_file():
        raise SnapshotError("extra_upstream_missing")
    if frozen():
        if not embedded_source_is_verified(source):
            raise SnapshotError("embedded_upstream_extra_hash_mismatch")
        return source
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=5)
        expected = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD:wechatauto/" + name],
            capture_output=True, text=True, timeout=5)
        actual = subprocess.run(["git", "hash-object", str(source)],
                                capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise SnapshotError("extra_upstream_verification_failed") from None
    if (head.returncode or expected.returncode or actual.returncode
            or head.stdout.strip() != PIN or
            expected.stdout.strip() != actual.stdout.strip()):
        raise SnapshotError("extra_upstream_version_mismatch")
    return source


def load_media():
    """Load original media.py with stubbed logger and no package GUI imports."""
    source = _source("media.py")
    previous = {name: sys.modules.get(name) for name in
                ("wechatauto", "wechatauto.logger", "wechatauto.media")}
    pkg = types.ModuleType("wechatauto")
    pkg.__path__ = [str(source.parent)]
    logger = types.ModuleType("wechatauto.logger")
    logger.wxlog = logging.getLogger("wxbridge.media")
    logger.wxlog.addHandler(logging.NullHandler())
    try:
        sys.modules["wechatauto"] = pkg
        sys.modules["wechatauto.logger"] = logger
        spec = importlib.util.spec_from_file_location("wechatauto.media", source)
        if spec is None or spec.loader is None:
            raise SnapshotError("extra_module_not_loadable")
        module = importlib.util.module_from_spec(spec)
        sys.modules["wechatauto.media"] = module
        spec.loader.exec_module(module)
        return module.MediaDownloader
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def load_moment_db():
    """Compile unchanged original MomentDB and its pure XML parsing helper.

    Upstream moment.py has *top-level UI imports*, so importing it normally
    would pull in the entire GUI/send stack. Select only the read-only
    database class and XML helper, from a hash-verified original file.
    """
    source = _source("moment.py")
    parsed = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    nodes = [node for node in parsed.body
             if (isinstance(node, ast.ClassDef) and node.name == "MomentDB") or
             (isinstance(node, ast.FunctionDef) and node.name == "_parse_user_comment")]
    if len(nodes) != 2:
        raise SnapshotError("moment_read_only_source_shape_changed")
    future = ast.ImportFrom(module="__future__",
                            names=[ast.alias(name="annotations")], level=0)
    unit = ast.fix_missing_locations(ast.Module(body=[future] + nodes, type_ignores=[]))
    context = {
        "__name__": "wxbridge.pinned_moment_reader",
        "os": os, "re": re, "html": html, "io": io, "json": json,
        "hashlib": hashlib, "time": time,
        "wxlog": logging.getLogger("wxbridge.moment"),
    }
    exec(compile(unit, str(source), "exec"), context)
    return context["MomentDB"]
