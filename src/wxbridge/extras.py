"""Additional read-only original-upstream operations over an existing DB.

Never starts the original DB constructor or desktop UI. When invoking media
code, disable any fallback process-memory image-key scanner.
"""
from __future__ import annotations

from html import unescape
import hashlib
from types import MethodType
from xml.etree import ElementTree as ET

from .cached import CachedError
from .media_read import locate_file
from .upstream_extra import load_media, load_moment_db


def _message_storage(db, chat: str) -> dict:
    """Check exact per-conversation message tables without reading any rows.

    This is a structural diagnosis for ordinary and business message shards,
    not an alternative path for returning private message content.
    """
    table = "Msg_" + hashlib.md5(chat.encode("utf-8")).hexdigest()
    required = {"local_id", "local_type", "real_sender_id", "create_time",
                "message_content", "source", "packed_info_data",
                "compress_content", "server_id", "sort_seq"}
    hits = []
    ordinary = business = 0
    for rel in db._message_dbs():
        connection = db._open(rel)
        try:
            found = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not found:
                continue
            # The generated table name contains hex only.
            n = int(connection.execute(
                "SELECT COUNT(*) FROM " + table).fetchone()[0])
            cols = {str(r[1]).lower()
                    for r in connection.execute("PRAGMA table_info(" + table + ")")}
            biz = "biz_message_" in rel.lower()
            hits.append({
                "shard": rel.replace("\\", "/"),
                "rows": n,
                "business": biz,
                "hasMessageContent": "message_content" in cols,
                "hasCompressedContent": "compress_content" in cols,
                "readerSchemaCompatible": required.issubset(cols),
            })
            if biz:
                business += n
            else:
                ordinary += n
        finally:
            connection.close()
    return {"source": "wechat-local-storage-metadata", "chat": chat,
            "tables": len(hits), "ordinaryRows": ordinary,
            "businessRows": business, "totalRows": ordinary + business,
            "shards": hits, "includesMessageBody": False}


def _limited(rows, limit: int):
    return list(rows)[:limit]


def _no_memory(*args, **kwargs):
    return None


def _media(db):
    obj = load_media()(db)
    # Upstream detects missing image AES keys by scanning Weixin memory.
    # That behavior is incompatible with the cached-only safety contract.
    obj._scan_aes_key = MethodType(_no_memory, obj)
    obj._persist_key = MethodType(_no_memory, obj)
    obj._resolve_aes_key = MethodType(_no_memory, obj)
    obj.detect_image_key = MethodType(_no_memory, obj)
    return obj


def _decode_article(content):
    if not isinstance(content, str) or len(content) > 1_000_000:
        return None
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        return None
    try:
        root = ET.fromstring(content.strip())
    except ET.ParseError:
        return None
    app = root if root.tag == "appmsg" else root.find(".//appmsg")
    if app is None:
        return None
    app_type = (app.findtext("type") or "").strip()
    # WeChat appmsg type 6 is a file, and 57 a quoted message. Only a
    # web/article share (type 5), or an older untyped article XML, belongs
    # in the articles listing.
    if app_type not in ("", "5"):
        return None
    if app.find("appattach") is not None:
        return None
    def field(parent, path):
        node = parent.find(path)
        return unescape((node.text or "").strip()) if node is not None else ""
    # Article shares (including public accounts) are type 49 appmsg XML.
    # Do not fetch arbitrary external URLs here.
    item = app.find(".//item")
    if item is None:
        item = app
    title = field(item, "title") or field(app, "title")
    url = field(item, "url") or field(app, "url")
    if not title and not url:
        return None
    if app_type == "" and not url and app.find(".//mmreader") is None:
        return None
    return {
        "title": title,
        "url": url,
        "summary": field(item, "digest") or field(app, "des"),
        "author": field(app, "sourceusername"),
        "source": field(app, "sourcedisplayname"),
        "cover": field(item, "cover") or field(app, "thumburl"),
        "appType": field(app, "type"),
    }


def read_extra(reader, action: str, args) -> dict:
    db = reader.db
    limit = getattr(args, "limit", 20)
    if action == "message-storage":
        return _message_storage(db, args.chat)
    if action == "contacts":
        rows = db.search_contact(args.keyword)
        return {"source": "wechat-local-db", "count": min(limit, len(rows)),
                "contacts": _limited(rows, limit)}
    if action == "groups":
        groups = db.get_groups()
        # The upstream eagerly fetches group members. Only expose member
        # counts in listings; ask for one group's members separately.
        visible = [{k: v for k, v in g.items() if k != "members"}
                   for g in groups[:limit]]
        return {"source": "wechat-local-db", "count": len(visible), "groups": visible}
    if action == "group-members":
        members = db.get_group_members(args.chat)
        return {"source": "wechat-local-db", "chat": args.chat,
                "count": min(limit, len(members)),
                "members": _limited(members, limit)}
    if action == "labels":
        labels = db.list_labels()[:limit]
        return {"source": "wechat-local-db", "count": len(labels), "labels": labels}
    if action == "message-chats":
        chats = db.list_message_chats()[:limit]
        return {"source": "wechat-local-db", "count": len(chats), "chats": chats}
    if action == "new-messages":
        rows = db.get_new_messages(args.chat, since_seq=args.since_seq, limit=limit)
        return {"source": "wechat-local-db", "chat": args.chat,
                "count": len(rows), "messages": rows}
    if action == "self":
        return {"source": "wechat-local-db", "profile": db.get_self_info()}
    if action == "media-status":
        md = _media(db)
        if args.kind == "image":
            data = md.image_status(args.chat, args.local_id, shard=args.shard)
        elif args.kind == "voice":
            data = md.voice_status(args.chat, args.local_id)
        else:
            raise CachedError("status_only_supports_image_or_voice")
        return {"source": "wechat-local-media", "kind": args.kind, "data": data}
    if action == "media-read":
        return locate_file(db, args.chat, args.message_id)
    if action in ("moments", "moment", "moment-interactions"):
        moments = load_moment_db()(db)
        if action == "moment":
            found = moments.get_moment(args.tid)
            return {"source": "wechat-local-moments", "moment": found}
        if action == "moment-interactions":
            rows = moments.get_interactions(
                limit=limit, offset=args.offset, only_unread=args.unread)
            return {"source": "wechat-local-moments",
                    "count": len(rows), "interactions": rows}
        rows = moments.get_moments(
            limit=limit, offset=args.offset, username=args.chat,
            keyword=args.keyword)
        return {"source": "wechat-local-moments", "count": len(rows),
                "moments": rows}
    if action == "articles":
        data = reader.messages(chat=args.chat, limit=limit,
                               offset=args.offset)
        items = []
        for message in data["messages"]:
            article = _decode_article(message.get("content"))
            if article is not None:
                items.append({"messageId": message.get("id"),
                              "timestamp": message.get("timestamp"),
                              **article})
        return {"source": "wechat-local-article-metadata",
                "chat": args.chat, "count": len(items),
                "scanned": data["count"], "completeHistory": False,
                "articles": items}
    raise CachedError("unknown_read_operation")
