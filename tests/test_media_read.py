"""Local file resolution regression tests using only invented attachments."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wxbridge.cached import CachedError
from wxbridge.media_read import locate_file


class InventedDatabase:
    def __init__(self, root, xml, *, shard="message__message_3.db",
                 local_type=(6 << 32) | 49):
        self.account_dir = root
        self.xml = xml
        self.shard = shard
        self.local_type = local_type

    def get_message_row(self, chat, local_id, shard):
        if (chat, local_id) != ("fictional", 602):
            return None
        if shard != self.shard:
            return None
        return {"shard": self.shard, "local_type": self.local_type, "content": self.xml}

    def _msg_type_name(self, local_type):
        return "File"

    def _friendly_content(self, content, message_type):
        return content.decode("utf-8")


class MediaReadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.media = self.root / "msg" / "file" / "2026-10"
        self.media.mkdir(parents=True)
        self.content = b"%PDF-1.4\nfictional example\n%%EOF\n"
        self.digest = hashlib.md5(self.content).hexdigest()
        self.name = "example.pdf"
        self.message_id = "message__message_3.db:602"

    def db(self, *, name=None, digest=None, size=None, app_type="6"):
        title = name if name is not None else self.name
        digest = self.digest if digest is None else digest
        size = len(self.content) if size is None else size
        xml = ("<msg><appmsg><type>%s</type><title>%s</title>"
               "<appattach><totallen>%s</totallen></appattach>"
               "<md5>%s</md5></appmsg></msg>" % (app_type, title, size, digest))
        return InventedDatabase(self.root, xml)

    def locate(self, db=None, message_id=None):
        return locate_file(db or self.db(), "fictional", message_id or self.message_id)

    def test_collision_renamed_pdf_resolves_by_size_and_md5_without_copy(self):
        source = self.media / "example(1).pdf"
        source.write_bytes(self.content)
        before = set(self.root.rglob("*"))
        result = self.locate()
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["path"], str(source.resolve()))
        self.assertEqual(result["verification"], "md5_and_size")
        self.assertEqual(result["md5"], self.digest)
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_raw_blob_message_is_decoded_before_xml_parsing(self):
        source = self.media / "example.pdf"
        source.write_bytes(self.content)
        db = self.db()
        db.xml = db.xml.encode("utf-8")
        self.assertEqual(self.locate(db)["path"], str(source.resolve()))

    def test_exact_name_wins_only_when_contents_match(self):
        (self.media / "example.pdf").write_bytes(b"X" * len(self.content))
        renamed = self.media / "example(2).pdf"
        renamed.write_bytes(self.content)
        self.assertEqual(self.locate()["path"], str(renamed.resolve()))

    def test_wrong_hash_fails_closed(self):
        (self.media / "example(1).pdf").write_bytes(b"X" * len(self.content))
        result = self.locate()
        self.assertEqual(result["status"], "checksum_mismatch")
        self.assertIsNone(result["path"])

    def test_missing_file_returns_status_not_path(self):
        result = self.locate()
        self.assertEqual(result["status"], "not_cached")
        self.assertIsNone(result["path"])

    def test_mismatched_size_is_not_a_match(self):
        (self.media / "example.pdf").write_bytes(self.content)
        result = self.locate(self.db(size=1234))
        self.assertEqual(result["status"], "not_cached")

    def test_no_digest_does_not_guess_renamed_file(self):
        (self.media / "example(1).pdf").write_bytes(self.content)
        self.assertIsNone(self.locate(self.db(digest="missing"))["path"])
        (self.media / "example.pdf").write_bytes(self.content)
        result = self.locate(self.db(digest="missing"))
        self.assertEqual(result["verification"], "exact_name_and_size")

    def test_rejects_invalid_or_mismatched_message(self):
        for message_id in ("602", "../../secret:602", "a:0:602"):
            with self.subTest(message_id=message_id), self.assertRaises(CachedError):
                self.locate(message_id=message_id)
        with self.assertRaises(CachedError):
            self.locate(message_id="message__message_7.db:602")

    def test_rejects_non_file_and_unsafe_names(self):
        with self.assertRaises(CachedError):
            self.locate(self.db(app_type="5"))
        with self.assertRaises(CachedError):
            self.locate(self.db(name="../secret.pdf"))
        incorrect_type = self.db()
        incorrect_type.local_type = 1
        with self.assertRaises(CachedError):
            self.locate(incorrect_type)

    def test_symlink_outside_account_is_not_followed(self):
        other = self.root / "external.pdf"
        other.write_bytes(self.content)
        link = self.media / "example.pdf"
        try:
            link.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not permitted")
        self.assertIsNone(self.locate()["path"])


if __name__ == "__main__":
    unittest.main()
