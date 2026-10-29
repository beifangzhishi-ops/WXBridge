"""Synthetic-only regression coverage for WeChat 4.x service account DBs."""

import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wxbridge.message_shards import message_shards
from wxbridge.extras import read_extra


class FakeReadOnlyDB:
    def _message_dbs(self):
        return ["message\\biz_message_1.db", "message\\message_0.db"]

    def _open(self, rel):
        db = sqlite3.connect(":memory:")
        target = "Msg_" + hashlib.md5(b"gh_synthetic_official").hexdigest()
        if "biz_message" in rel:
            db.execute("CREATE TABLE " + target + " "
                       "(local_id INTEGER, message_content TEXT, compress_content BLOB)")
            db.execute("INSERT INTO " + target + " VALUES "
                       "(9, 'synthetic-only', NULL)")
        return db


class MessageShardTests(unittest.TestCase):
    def test_exact_supported_db_types_only(self):
        paths = [
            ("message\\message_0.db", "", 1),
            ("message/biz_message_12.db", "", 1),
            ("message/media_0.db", "", 1),
            ("message/message_fts.db", "", 1),
            ("message/message_resource.db", "", 1),
            ("contact/contact.db", "", 1),
            ("message/biz_message_1.db-shm", "", 1),
            ("message/biz_message_1.db/other", "", 1),
        ]
        self.assertEqual(
            message_shards(paths),
            ["message/biz_message_12.db", "message\\message_0.db"],
        )

    def test_business_table_count_metadata_does_not_return_body(self):
        args = SimpleNamespace(chat="gh_synthetic_official")
        result = read_extra(SimpleNamespace(db=FakeReadOnlyDB()),
                            "message-storage", args)
        self.assertEqual(result["totalRows"], 1)
        self.assertEqual(result["businessRows"], 1)
        self.assertEqual(result["ordinaryRows"], 0)
        self.assertTrue(result["shards"][0]["hasMessageContent"])
        self.assertFalse(result["shards"][0]["readerSchemaCompatible"])
        self.assertFalse(result["includesMessageBody"])
        self.assertNotIn("synthetic-only", str(result))


if __name__ == "__main__":
    unittest.main()
