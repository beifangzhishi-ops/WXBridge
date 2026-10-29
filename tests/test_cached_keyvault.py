"""All key/cache tests use invented keys and fake DB readers only."""

import json
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import sys
import types
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wxbridge import cached, keyvault


class InventedDB:
    account = "fictional-account"
    account_dir = r"C:\Synthetic\WeChat\fictional-account"
    _db_files = [("session/session.db", "fictional-session", 8192),
                 ("message/message_0.db", "fictional-message", 8192)]
    _keys = {"session/session.db": b"s" * 32, "message/message_0.db": b"m" * 32}

    def _key_works(self, rel):
        return rel in self._keys


class VaultFixture(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / ".state" / "synthetic-sealed-keys-test.dpapi"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.assertFalse(self.path.exists(), "Refusing to overwrite an existing fixture")
        # Test substitution is NOT encryption and is never used in production.
        self.transform = patch.object(
            keyvault, "_transform",
            side_effect=lambda content, protect: bytes(v ^ 0xA5 for v in content))
        self.transform.start()
        self.addCleanup(self.transform.stop)
        self.addCleanup(lambda: self.path.unlink(missing_ok=True))

    def test_sealed_vault_roundtrip_fake_keys_only(self):
        self.assertEqual(keyvault.seal_verified_keys(InventedDB(), vault_path=self.path), 2)
        contents = self.path.read_bytes()
        self.assertNotIn(b"fictional-account", contents)
        self.assertNotIn(b"6d6d6d6d", contents)
        account, path_hash, keys = keyvault.unseal_keys(vault_path=self.path)
        self.assertEqual(account, "fictional-account")
        self.assertEqual(path_hash, keyvault._fingerprint(InventedDB.account_dir))
        self.assertEqual(keys, InventedDB._keys)

    def test_incomplete_valid_keys_cannot_replace_existing_cache(self):
        db = InventedDB()
        db._keys = {"session/session.db": b"s" * 32}
        with self.assertRaisesRegex(keyvault.KeyVaultError, "not_all"):
            keyvault.seal_verified_keys(db, vault_path=self.path)
        self.assertFalse(self.path.exists())

    def test_unset_cache_fails_closed(self):
        with self.assertRaisesRegex(keyvault.KeyVaultError, "no_local_key_cache"):
            keyvault.unseal_keys(vault_path=self.path)

    def test_corrupted_cache_fails_closed(self):
        self.path.write_bytes(b"synthetic not json")
        with self.assertRaisesRegex(keyvault.KeyVaultError, "unable_to_unlock"):
            keyvault.unseal_keys(vault_path=self.path)


class ForbiddenConstructor:
    def __init__(self, *args, **kwargs):
        raise AssertionError("cached backend must never invoke the live constructor")

    def _collect_db_files(self):
        return list(InventedDB._db_files)

    def _key_works(self, rel):
        return self._keys.get(rel) == InventedDB._keys.get(rel)

    def get_sessions(self, limit=20):
        return [{"username": "filehelper", "unread": 0, "last_time": 1760000000}]

    def get_nickname(self, username):
        return "Fictional Helper"

    def get_messages(self, user, limit=20, offset=0):
        return [{"local_id": 42, "shard": "message_0", "create_time": 1760000010,
                 "content": "fictional hello", "sender_username": "filehelper"}][offset:][:limit]


class CacheBackendTests(unittest.TestCase):
    def setUp(self):
        self.module = types.SimpleNamespace(
            WeChatDB=ForbiddenConstructor, auto_detect_db_dir=lambda: r"C:\Synthetic\WeChat")
        self.stubs = [
            patch.object(cached, "unseal_keys",
                         return_value=(InventedDB.account, keyvault._fingerprint(
                             InventedDB.account_dir), dict(InventedDB._keys))),
            patch.object(cached.os.path, "isdir", return_value=True),
        ]
        for stub in self.stubs:
            stub.start()
            self.addCleanup(stub.stop)

    def test_stub_reader_no_memory_calls(self):
        db = cached._prepare(self.module, "fictional-temp")
        self.assertEqual(db._keys, InventedDB._keys)
        with self.assertRaisesRegex(cached.CachedError, "disabled"):
            db.extract_keys()
        with self.assertRaisesRegex(cached.CachedError, "disabled"):
            db.extract_master_key()
        with self.assertRaisesRegex(cached.CachedError, "disabled"):
            db._all_key_candidates()
        db._refresh_db_files()
        from wxbridge.replica import ReplicaReader
        adapted = ReplicaReader(db)
        self.assertEqual(adapted.sessions(limit=10)["count"], 1)
        self.assertEqual(adapted.messages(chat="filehelper", limit=5)["messages"][0]["content"],
                         "fictional hello")

    def test_stale_key_disables_query(self):
        with patch.object(cached, "unseal_keys", return_value=(
                InventedDB.account, keyvault._fingerprint(InventedDB.account_dir),
                {"session/session.db": b"z" * 32})):
            with self.assertRaisesRegex(cached.CachedError, "stale"):
                cached._prepare(self.module, "fictional-temp")

    def test_wrong_account_location_refused(self):
        with patch.object(cached, "unseal_keys", return_value=(
                InventedDB.account, "0" * 64, dict(InventedDB._keys))):
            with self.assertRaisesRegex(cached.CachedError, "does_not_match"):
                cached._prepare(self.module, "fictional-temp")

    def test_ephemeral_db_cache_uses_callers_workdir_not_wxbridge_root(self):
        """No real Windows scratch directory/ACL mutation in this test."""
        expected_dir = Path.cwd()
        @contextmanager
        def simulated_temp(*args, **kwargs):
            self.assertEqual(Path(kwargs["dir"]), expected_dir)
            yield str(expected_dir / "fictional-temporary-database-directory")

        with patch.object(cached, "_load_upstream", return_value=object()):
            with patch.object(cached, "_prepare", side_effect=lambda _u, path: (
                    SimpleNamespace(get_sessions=lambda limit: [],
                                    workdir=path))):
                with patch.object(cached.tempfile, "TemporaryDirectory",
                                  side_effect=simulated_temp):
                    with cached.open_cached_reader() as reader:
                        self.assertEqual(Path(reader.db.workdir).parent, expected_dir)


if __name__ == "__main__":
    unittest.main()
