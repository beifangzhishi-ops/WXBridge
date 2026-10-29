"""Extra upstream integration tests: entirely invented inputs and databases."""

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wxbridge.extras import _decode_article, _media, read_extra
from wxbridge.upstream_extra import load_media, load_moment_db


def opts(**kwargs):
    defaults = dict(limit=5, keyword=None, chat="synthetic@chatroom",
                    offset=0, kind="image", local_id=7, out=None,
                    shard=None, since_seq=0, tid=123, unread=False,
                    tier="best")
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FakeDB:
    def search_contact(self, keyword):
        return [{"username": "fictional", "nick_name": "Invented", "remark": ""}]

    def get_groups(self):
        return [{"username": "synthetic@chatroom", "name": "Synthetic Room",
                 "member_count": 2, "members": [{"username": "madeup"}]}]

    def get_group_members(self, chat):
        return [{"username": "fictional", "is_owner": False}]

    def list_labels(self):
        return [{"label_id": 1, "name": "Synthetic Label"}]

    def list_message_chats(self):
        return [{"username": "fictional", "message_count": 2}]

    def get_new_messages(self, chat, since_seq, limit):
        return [{"content": "invented!", "sort_seq": since_seq + 1}]

    def get_self_info(self):
        return {"username": "fictional"}

    def get_messages(self, *args, **kwargs):
        return []


class ExtrasTests(unittest.TestCase):
    def setUp(self):
        self.reader = SimpleNamespace(db=FakeDB())

    def test_original_sources_are_loadable_without_gui_imports(self):
        self.assertEqual(load_media().__name__, "MediaDownloader")
        self.assertEqual(load_moment_db().__name__, "MomentDB")

    def test_contacts_groups_labels_and_incremental_messages(self):
        self.assertEqual(read_extra(self.reader, "contacts", opts(keyword="Inv"))["count"], 1)
        self.assertEqual(read_extra(self.reader, "groups", opts())["groups"][0]["name"],
                         "Synthetic Room")
        self.assertNotIn("members", read_extra(self.reader, "groups", opts())["groups"][0])
        self.assertEqual(read_extra(self.reader, "group-members", opts())["count"], 1)
        self.assertEqual(read_extra(self.reader, "labels", opts())["count"], 1)
        self.assertEqual(read_extra(self.reader, "message-chats", opts())["count"], 1)
        self.assertEqual(read_extra(self.reader, "new-messages", opts(since_seq=9))
                         ["messages"][0]["sort_seq"], 10)
        self.assertEqual(read_extra(self.reader, "self", opts())["profile"]["username"],
                         "fictional")

    def test_commands_without_limit_option_do_not_fail(self):
        args = SimpleNamespace()
        self.assertEqual(read_extra(self.reader, "self", args)["profile"]["username"],
                         "fictional")

    def test_articles_parse_original_xml_without_following_links(self):
        xml = ("<msg><appmsg><title>Fictional article</title>"
               "<des>Example</des><url>https://example.invalid/post</url>"
               "<sourcedisplayname>Example Public Account</sourcedisplayname>"
               "</appmsg></msg>")
        self.assertEqual(_decode_article(xml)["title"], "Fictional article")
        self.assertEqual(
            _decode_article("<msg><appmsg><mmreader><category><item><title>"
                            "Nested Synthetic</title></item></category></mmreader></appmsg></msg>")["title"],
            "Nested Synthetic")
        self.assertIsNone(_decode_article('<!DOCTYPE a [<!ENTITY x "bad">]><msg/>'))
        self.assertIsNone(_decode_article("not xml"))
        self.assertIsNone(_decode_article("<msg><img/></msg>"))
        self.assertIsNone(_decode_article(
            "<msg><appmsg><type>6</type><title>paper.pdf</title>"
            "<appattach><totallen>123</totallen></appattach></appmsg></msg>"))
        self.assertIsNone(_decode_article(
            "<msg><appmsg><type>57</type><title>Quoted message</title>"
            "</appmsg></msg>"))
        self.assertEqual(_decode_article(
            "<msg><appmsg><type>5</type><title>Article</title>"
            "<url>https://example.invalid/article</url></appmsg></msg>")["title"],
            "Article")
        self.reader.messages = lambda **kw: {
            "count": 1, "messages": [{"id": "synthetic-id", "timestamp": 123,
                                        "content": xml}]}
        data = read_extra(self.reader, "articles", opts())
        self.assertEqual(data["count"], 1)
        self.assertFalse(data["completeHistory"])

    def test_media_key_memory_fallback_is_disabled(self):
        obj = _media(FakeDB())
        self.assertIsNone(obj.detect_image_key())
        self.assertIsNone(obj._resolve_aes_key())
        self.assertIsNone(obj._scan_aes_key())

    def test_moment_original_xml_parser(self):
        parser = load_moment_db()(FakeDB())
        result = parser.parse_feed(
            '<SnsDataItem><id>123</id><username>synthetic</username>'
            '<createTime>1760000000</createTime>'
            '<contentDesc>Fictional &#38; harmless</contentDesc></SnsDataItem>',
            fallback_user="synthetic")
        self.assertEqual(result["text"], "Fictional & harmless")
        self.assertEqual(result["create_time"], 1760000000)


if __name__ == "__main__":
    unittest.main()
