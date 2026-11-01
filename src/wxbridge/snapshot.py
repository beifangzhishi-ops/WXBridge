"""Read-only offline SQLite snapshots using the original upstream query code.

Only explicitly supplied *decrypted SQLite copies* are supported. This backend
never opens live encrypted WeChat data, never starts WeChatDB.__init__, never
extracts encryption keys, and never starts the upstream GUI/sending package.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import types
from types import MethodType

from .replica import ReplicaReader
from .process import NO_CONSOLE_FLAGS
from .runtime import embedded_root, embedded_source_is_verified, frozen, app_root
from .message_shards import is_message_shard_name

PIN = "6e603974bbac3bda93d88bbd6995510ae2547f5c"
MAX_FILES = 256
MESSAGE_NAME = re.compile(r"^(?:biz_)?message_\d+\.db$", re.IGNORECASE)


class SnapshotError(ValueError):
    """No private paths or data in messages returned to callers."""


def _upstream_dir() -> Path:
    if frozen():
        # Never load caller-supplied Python through a runtime override.
        return embedded_root()
    override = os.environ.get("WXBRIDGE_UPSTREAM_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return app_root() / ".vendor" / "replica-src"


def _load_upstream():
    """Load original pinned db.py only; never execute sending/UI __init__."""
    checkout = _upstream_dir()
    src = checkout / "wechatauto" / "db.py"
    if not src.is_file():
        raise SnapshotError("upstream_db_module_missing")
    if frozen():
        if not embedded_source_is_verified(src):
            raise SnapshotError("embedded_upstream_db_hash_mismatch")
    else:
        # A CCM-managed Windows checkout can be owned by Administrators
        # even when the worker runs as the user. Trust only this one exact
        # Git directory for metadata queries; the pinned HEAD and content
        # checks below remain mandatory.
        git = ["git", "-c", "safe.directory=" + str(checkout), "-C", str(checkout)]
        try:
            proc = subprocess.run(
                [*git, "rev-parse", "HEAD"],
                capture_output=True, text=True, check=False, timeout=5,
                creationflags=NO_CONSOLE_FLAGS,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise SnapshotError("upstream_git_not_available") from None
        if proc.returncode != 0 or proc.stdout.strip() != PIN:
            raise SnapshotError("missing_or_unapproved_upstream_version")
        # A pinned Git HEAD alone is insufficient: a modified working tree
        # could load arbitrary code. Require the exact committed file.
        try:
            expected = subprocess.run(
                [*git, "rev-parse", "HEAD:wechatauto/db.py"],
                capture_output=True, text=True, check=False, timeout=5,
                creationflags=NO_CONSOLE_FLAGS,
            )
            actual = subprocess.run(
                ["git", "hash-object", str(src)],
                capture_output=True, text=True, timeout=5,
                creationflags=NO_CONSOLE_FLAGS,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise SnapshotError("upstream_verification_failed") from None
        if (expected.returncode or actual.returncode
                or expected.stdout.strip() != actual.stdout.strip()):
            raise SnapshotError("upstream_db_file_modified")
    # Avoid importing package __init__, which loads UI/sending modules.
    pkg = types.ModuleType("wechatauto")
    pkg.__path__ = [str(src.parent)]
    logmod = types.ModuleType("wechatauto.logger")
    logmod.wxlog = logging.getLogger("wxbridge.snapshot.upstream")
    logmod.wxlog.addHandler(logging.NullHandler())
    # Temporarily substitute package names only while importing source.
    previous = {name: sys.modules.get(name)
                for name in ("wechatauto", "wechatauto.logger", "wechatauto.db")}
    try:
        sys.modules["wechatauto"] = pkg
        sys.modules["wechatauto.logger"] = logmod
        spec = importlib.util.spec_from_file_location("wechatauto.db", src)
        if spec is None or spec.loader is None:
            raise SnapshotError("upstream_db_module_missing")
        module = importlib.util.module_from_spec(spec)
        sys.modules["wechatauto.db"] = module
        try:
            spec.loader.exec_module(module)
        except ImportError:
            # Especially useful if a frozen EXE lacks a dynamic dependency.
            raise SnapshotError("upstream_db_runtime_dependency_missing") from None
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
    return module


def _snapshot_files(root: Path) -> list[tuple[str, Path, int]]:
    if not root.is_dir():
        raise SnapshotError("snapshot_directory_missing")
    found = []
    inspected = 0
    # Mirror only the upstream's decrypted snapshot filename convention.
    # Nested message/*.db and flat message__message_0.db are both accepted.
    for where, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(where) / d).is_symlink()]
        for filename in files:
            inspected += 1
            if inspected > 10_000:
                raise SnapshotError("snapshot_directory_too_large")
            path = Path(where) / filename
            if path.is_symlink():
                continue
            rel = path.relative_to(root)
            base = filename.lower()
            if base not in ("session.db", "contact.db") and not MESSAGE_NAME.fullmatch(base):
                # Upstream decrypted cache uses message__message_0.db.
                if not base.startswith("message__") or not MESSAGE_NAME.fullmatch(base[9:]):
                    continue
            if len(found) >= MAX_FILES:
                raise SnapshotError("snapshot_too_many_files")
            if path.stat().st_size < 100:
                raise SnapshotError("snapshot_invalid_sqlite_file")
            with path.open("rb") as handle:
                if handle.read(16) != b"SQLite format 3\x00":
                    raise SnapshotError("snapshot_requires_decrypted_sqlite")
            found.append((str(rel), path, path.stat().st_size))
    if not found:
        raise SnapshotError("snapshot_has_no_supported_sqlite_files")
    return found


class SnapshotReader:
    """Adapter over the genuine upstream get_sessions/get_messages implementation."""

    def __init__(self, directory: str):
        if not directory:
            raise SnapshotError("snapshot_directory_not_configured")
        root = Path(directory).expanduser().resolve(strict=False)
        files = _snapshot_files(root)
        upstream = _load_upstream()
        obj = object.__new__(upstream.WeChatDB)
        obj._db_files = [(rel, str(path), size) for rel, path, size in files]
        obj._snapshot_paths = {rel: path for rel, path, _ in files}
        msgfiles = [rel for rel, path, _ in files
                    if is_message_shard_name(path.name) or
                    (path.name.lower().startswith("message__")
                     and is_message_shard_name(path.name[9:]))]
        obj._message_dbs = MethodType(lambda self: msgfiles, obj)

        def read_only_open(self, rel):
            path = self._snapshot_paths.get(rel)
            if path is None:
                raise SnapshotError("snapshot_database_not_found")
            # immutable=1 never creates SQLite journal, WAL or SHM files;
            # the caller supplies a consistent standalone exported copy.
            con = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1",
                                  uri=True, timeout=2.0)
            con.row_factory = sqlite3.Row
            return con

        obj._open = MethodType(read_only_open, obj)
        obj._refresh_db_files = MethodType(lambda self: None, obj)
        self._adapter = ReplicaReader(obj)
        self.session_database_present = any(path.name.lower() == "session.db"
                                            for _, path, _ in files)
        self.message_shards = len(msgfiles)

    def sessions(self, *, limit: int, keyword: str | None = None) -> dict:
        if not self.session_database_present:
            raise SnapshotError("snapshot_session_database_missing")
        result = self._adapter.sessions(limit=limit, keyword=keyword)
        result["source"] = "offline_snapshot"
        result["readerImplementation"] = "wechatauto-replica"
        result["coverage"] = "explicit_offline_snapshot_only"
        return result

    def messages(self, *, chat: str, limit: int, offset: int = 0,
                 keyword: str | None = None,
                 start: str | None = None, end: str | None = None) -> dict:
        if not self.message_shards:
            raise SnapshotError("snapshot_message_database_missing")
        result = self._adapter.messages(
            chat=chat, limit=limit, offset=offset, keyword=keyword,
            start=start, end=end,
        )
        result["source"] = "offline_snapshot"
        result["readerImplementation"] = "wechatauto-replica"
        result["coverage"] = "explicit_offline_snapshot_only"
        return result
