"""Private DPAPI vault for already-authorized per-file WeChat DB keys.

No process-memory APIs or queries live here. The vault is written only by an
explicit user-run operation, and loaded only by an explicit cached query.
Never log, print, commit, or export its plaintext contents.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from .dpapi import _transform
from .paths import STATE

KEY_FILE = STATE / "wechat-keys.dpapi"
MAX_KEYS = 256


class KeyVaultError(ValueError):
    """Messages may be presented to the user; no secret material in errors."""


def _fingerprint(account_dir: str) -> str:
    normalized = os.path.normcase(os.path.abspath(account_dir)).encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def _validated_keys(value: dict) -> dict[str, bytes]:
    if not isinstance(value, dict) or len(value) > MAX_KEYS:
        raise KeyVaultError("invalid_cached_key_collection")
    result = {}
    for rel, text in value.items():
        if (not isinstance(rel, str) or not rel or len(rel) > 300
                or not isinstance(text, str) or len(text) not in (64, 96)):
            raise KeyVaultError("invalid_cached_key_entry")
        try:
            result[rel] = bytes.fromhex(text)
        except ValueError:
            raise KeyVaultError("invalid_cached_key_format") from None
    return result


def seal_verified_keys(db, *, vault_path: Path = KEY_FILE) -> int:
    """Store verified per-file keys, not master keys or decrypted databases.

    Caller is responsible for explicit local user consent. No call into key
    extraction is made by this function.
    """
    selected = {}
    for rel, _, _ in db._db_files:
        if rel in db._keys and db._key_works(rel):
            selected[rel] = db._keys[rel].hex()
    if not selected:
        raise KeyVaultError("no_verified_keys_to_save")
    keys = _validated_keys(selected)
    if len(keys) != len(db._db_files):
        raise KeyVaultError("not_all_database_keys_verified")
    document = {
        "version": 1,
        "account": db.account,
        "accountPathFingerprint": _fingerprint(db.account_dir),
        "keys": {k: v.hex() for k, v in keys.items()},
    }
    plaintext = json.dumps(document, separators=(",", ":")).encode("utf-8")
    protected = _transform(plaintext, protect=True)
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = vault_path.with_suffix(".tmp")
    try:
        temporary.write_bytes(protected)
        temporary.replace(vault_path)
    finally:
        temporary.unlink(missing_ok=True)
    return len(keys)


def unseal_keys(*, vault_path: Path = KEY_FILE) -> tuple[str, str, dict[str, bytes]]:
    """Load keys strictly into the local process, never to stdout or logs."""
    if not vault_path.is_file():
        raise KeyVaultError("no_local_key_cache; run a separate authorized local setup")
    try:
        doc = json.loads(_transform(vault_path.read_bytes(), protect=False))
        if (not isinstance(doc, dict) or doc.get("version") != 1
                or not isinstance(doc.get("account"), str) or not doc["account"]
                or not isinstance(doc.get("accountPathFingerprint"), str)):
            raise KeyVaultError("invalid_key_cache_header")
        keys = _validated_keys(doc.get("keys"))
        if not keys:
            raise KeyVaultError("empty_key_cache")
        return doc["account"], doc["accountPathFingerprint"], keys
    except KeyVaultError:
        raise
    except (OSError, ValueError, TypeError, UnicodeError):
        raise KeyVaultError("unable_to_unlock_local_key_cache") from None


def key_cache_status() -> dict:
    """Metadata-only, never decrypt the cache during readiness checks."""
    return {"configured": KEY_FILE.is_file(), "protection": "Windows DPAPI current user"}
