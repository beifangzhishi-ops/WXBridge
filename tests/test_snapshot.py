"""End-to-end tests of the unmodified upstream DB query methods.

All SQLite data is fabricated. No WeChat process, account or encrypted DB is
accessed. The optional upstream checkout stays in ignored .vendor/.
"""

import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from wxbridge.snapshot import SnapshotError, SnapshotReader, _snapshot_files


class SnapshotMetadataTests(unittest.TestCase):
    def test_missing_snapshot_is_explicit(self):
        with self.assertRaisesRegex(SnapshotError, "not_configured"):
            SnapshotReader("")

    def test_unknown_snapshot_directory_is_explicit(self):
        with self.assertRaisesRegex(SnapshotError, "directory_missing"):
            _snapshot_files(ROOT / ".state" / "missing-replica-snapshot-TEST")


@unittest.skipUnless((ROOT / ".vendor" / "replica-src" / "wechatauto" / "db.py").is_file(),
                     "requires optional pinned unmodified upstream checkout")
class UpstreamSnapshotTests(unittest.TestCase):
    def setUp(self):
        safe = ROOT / ".state"
        safe.mkdir(exist_ok=True)
        # Use a fixed ignored fixture directory. CCM's restricted Windows
        # worker cannot write to Python's randomly generated temp directories.
        self.path = safe / "replica-fixture-synthetic"
        if self.path.exists():
            raise RuntimeError("Synthetic fixture already exists; refusing to overwrite")
        self.path.mkdir()
        self.addCleanup(lambda: shutil.rmtree(self.path) if self.path.is_dir() else None)
        con = sqlite3.connect(self.path / "session.db")
        try:
            con.execute("CREATE TABLE SessionTable (username TEXT, unread_count INTEGER,"
                        "summary TEXT, last_timestamp INTEGER, last_msg_sender TEXT,"
                        "last_sender_display_name TEXT, is_hidden INTEGER, sort_timestamp INTEGER)")
            con.execute("INSERT INTO SessionTable VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        ("filehelper", 2, "synthetic", 1760000000, "filehelper", "Me", 0, 1760000000))
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(self.path / "contact.db")
        try:
            con.execute("CREATE TABLE contact (username TEXT, nick_name TEXT, remark TEXT)")
            con.execute("INSERT INTO contact VALUES (?, ?, ?)",
                        ("filehelper", "File Transfer Assistant", ""))
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(self.path / "message__message_0.db")
        try:
            con.execute("CREATE TABLE Name2Id (user_name TEXT)")
            con.execute("INSERT INTO Name2Id VALUES ('filehelper')")
            tab = "Msg_" + hashlib.md5(b"filehelper").hexdigest()
            con.execute(f"CREATE TABLE {tab} (local_id INTEGER, local_type INTEGER,"
                        "real_sender_id INTEGER, create_time INTEGER, message_content TEXT,"
                        "source TEXT, packed_info_data BLOB, compress_content BLOB,"
                        "server_id INTEGER, sort_seq INTEGER)")
            con.execute(f"INSERT INTO {tab} VALUES (11, 1, 1, 1760000000,"
                        "'synthetic hello', '', NULL, NULL, 1001, 999)")
            con.execute(f"INSERT INTO {tab} VALUES (12, 1, 1, 1760000010,"
                        "'synthetic second', '', NULL, NULL, 1002, 1000)")
            con.commit()
        finally:
            con.close()
        con = sqlite3.connect(self.path / "message__biz_message_0.db")
        try:
            con.execute("CREATE TABLE Name2Id (user_name TEXT)")
            con.execute("INSERT INTO Name2Id VALUES ('gh_synthetic_official')")
            table = "Msg_" + hashlib.md5(b"gh_synthetic_official").hexdigest()
            con.execute(f"CREATE TABLE {table} (local_id INTEGER, local_type INTEGER,"
                        "real_sender_id INTEGER, create_time INTEGER, message_content TEXT,"
                        "source TEXT, packed_info_data BLOB, compress_content BLOB,"
                        "server_id INTEGER, sort_seq INTEGER)")
            con.execute(f"INSERT INTO {table} VALUES (1, 1, 1, 1760000020,"
                        "'synthetic business notification', '', NULL, NULL, 2001, 1001)")
            con.commit()
        finally:
            con.close()

    def tearDown(self):
        pass

    def test_real_upstream_methods_read_only_synthetic_sqlite(self):
        reader = SnapshotReader(str(self.path))
        ss = reader.sessions(limit=2)
        self.assertEqual(ss["count"], 1)
        self.assertEqual(ss["sessions"][0]["name"], "File Transfer Assistant")
        result = reader.messages(chat="filehelper", limit=2)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["messages"][0]["content"], "synthetic second")
        self.assertEqual(result["messages"][1]["sender"], "filehelper")
        self.assertEqual(result["coverage"], "explicit_offline_snapshot_only")
        self.assertEqual(result["source"], "offline_snapshot")
        self.assertEqual(result["readerImplementation"], "wechatauto-replica")
        self.assertFalse(result["completeHistory"])
        self.assertEqual(sorted(p.name for p in self.path.iterdir()),
                         ["contact.db", "message__biz_message_0.db",
                          "message__message_0.db", "session.db"])

    def test_synthetic_official_message_from_biz_shard(self):
        reader = SnapshotReader(str(self.path))
        result = reader.messages(chat="gh_synthetic_official", limit=2)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["messages"][0]["content"],
                         "synthetic business notification")
        self.assertEqual(result["messages"][0]["id"],
                         "message__biz_message_0.db:1")

    def test_keyword_filter_and_no_content_logging(self):
        result = SnapshotReader(str(self.path)).messages(
            chat="filehelper", keyword="second", limit=3)
        self.assertEqual([m["content"] for m in result["messages"]],
                         ["synthetic second"])

    def test_cli_in_separate_python_process(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        env["WXBRIDGE_SNAPSHOT_DIR"] = str(self.path)
        env["WXBRIDGE_BACKEND"] = "snapshot"
        proc = subprocess.run(
            [sys.executable, "-m", "wxbridge", "messages", "--chat", "filehelper", "--limit", "2"],
            env=env, capture_output=True, timeout=20)
        # The Windows worker may emit localized CP936 diagnostics on stderr.
        # Preserve UTF-8 JSON stdout while decoding unexpected errors safely.
        output = proc.stdout.decode("utf-8", errors="replace")
        diagnostics = proc.stderr.decode("utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, diagnostics)
        self.assertIn("synthetic second", output)
        self.assertNotIn("Traceback", diagnostics)

    @unittest.skipUnless((ROOT / "WXBridge.exe").is_file()
                         and (ROOT / "_wxbridge_runtime").is_dir(),
                         "requires optional locally built Windows EXE")
    def test_frozen_exe_reads_only_fabricated_snapshot(self):
        """Verify embedded upstream code, DLLs and adapter via synthetic SQL."""
        env = os.environ.copy()
        env["WXBRIDGE_SNAPSHOT_DIR"] = str(self.path)
        proc = subprocess.run(
            [str(ROOT / "WXBridge.exe"), "--backend", "snapshot", "messages",
             "--chat", "filehelper", "--limit", "2"],
            env=env, capture_output=True, timeout=20,
        )
        out = proc.stdout.decode("utf-8", errors="replace")
        err = proc.stderr.decode("utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, err)
        self.assertIn("synthetic second", out)
        self.assertIn('"source":"offline_snapshot"', out)
        self.assertNotIn("Traceback", err)

    @unittest.skipUnless((ROOT / "WXBridge.exe").is_file()
                         and (ROOT / "_wxbridge_runtime").is_dir(),
                         "requires optional locally built Windows EXE")
    def test_frozen_exe_reads_synthetic_official_biz_message(self):
        env = os.environ.copy()
        env["WXBRIDGE_SNAPSHOT_DIR"] = str(self.path)
        proc = subprocess.run(
            [str(ROOT / "WXBridge.exe"), "--backend", "snapshot",
             "messages", "--chat", "gh_synthetic_official", "--limit", "2"],
            env=env, capture_output=True, timeout=20)
        output = proc.stdout.decode("utf-8", errors="replace")
        errors = proc.stderr.decode("utf-8", errors="replace")
        self.assertEqual(proc.returncode, 0, errors)
        self.assertIn("synthetic business notification", output)


if __name__ == "__main__":
    unittest.main()
