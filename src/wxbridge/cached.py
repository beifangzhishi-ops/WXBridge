"""Explicit cached-key read-only DB backend: NO Weixin.exe memory scanning.

The original upstream query methods are reused, but its live constructor and
automatic key extraction are never called. Cached per-file keys are loaded
from a Windows DPAPI vault and validated against encrypted DB page headers.
Only transient decrypted SQLite copies are made during the requested query.
"""

from __future__ import annotations

from contextlib import contextmanager, redirect_stdout, redirect_stderr
import io
import os
from pathlib import Path
import tempfile
from types import MethodType

from .keyvault import KeyVaultError, _fingerprint, unseal_keys
from .paths import STATE
from .replica import ReplicaReader
from .snapshot import _load_upstream
from .message_shards import message_shards


class CachedError(ValueError):
    """Safe, non-secret failure code."""


def _blocked(*_args, **_kwargs):
    raise CachedError("automatic_key_extraction_disabled")


def _prepare(upstream, temporary_directory: str):
    # Read the existing DPAPI vault only; absolutely no WeChat process calls.
    account, fingerprint, keys = unseal_keys()
    db_cls = upstream.WeChatDB
    db_dir = upstream.auto_detect_db_dir()
    if not db_dir:
        raise CachedError("database_root_unavailable")
    account_dir = os.path.join(db_dir, account)
    if _fingerprint(account_dir) != fingerprint or not os.path.isdir(account_dir):
        raise CachedError("cached_account_does_not_match_storage")
    obj = object.__new__(db_cls)
    obj.db_dir = db_dir
    obj.account = account
    obj.account_dir = account_dir
    obj.workdir = temporary_directory
    obj.keys_file = str(Path(temporary_directory) / "never-written.json")
    obj.master_key = None
    obj.cfg_dword = None
    obj._db_files = obj._collect_db_files()
    obj._keys = keys
    # Original upstream _message_dbs() ignores biz_message_N.db, where
    # WeChat 4.x stores many official-account/service-account notifications.
    # Keep a fixed inventory per cached-only query: no memory/key refresh.
    obj._message_dbs = MethodType(lambda self: message_shards(self._db_files), obj)
    # Prevent implicit extraction via _refresh_db_files and failure handlers.
    # The database inventory is fixed for each short-lived query.
    obj._refresh_db_files = MethodType(lambda self: None, obj)
    obj._save_keys = MethodType(lambda self: None, obj)
    obj.extract_keys = MethodType(_blocked, obj)
    obj.extract_master_key = MethodType(_blocked, obj)
    obj._all_key_candidates = MethodType(_blocked, obj)
    obj._auto_diagnose_key_failure = MethodType(_blocked, obj)
    missing = [rel for rel, _, _ in obj._db_files
               if rel not in keys or not obj._key_works(rel)]
    if not obj._db_files or missing:
        raise CachedError("cache_missing_or_stale_for_current_databases")
    obj.unkeyed = []
    return obj


@contextmanager
def open_cached_reader():
    """One explicitly requested local DB query. No live key extraction ever."""
    upstream = _load_upstream()
    # Place scratch data in the *invoking workspace*.  A CCM worker in a
    # different registered project has host-wide read access to the DPAPI
    # vault, but must not need write access inside the WXBridge source tree.
    # The entire directory disappears when the one-shot query completes.
    with tempfile.TemporaryDirectory(prefix="wxbridge-cached-", dir=str(Path.cwd())) as temp:
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                db = _prepare(upstream, temp)
        except (KeyVaultError, CachedError):
            raise
        except Exception as exc:
            raise CachedError("cached_setup_" + type(exc).__name__) from None
        try:
            yield ReplicaReader(db)
        except (KeyVaultError, CachedError):
            raise
        except Exception as exc:
            raise CachedError("cached_query_" + type(exc).__name__) from None
