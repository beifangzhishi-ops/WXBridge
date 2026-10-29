"""Resolve already downloaded WeChat file attachments without copying them.

All filesystem operations are read-only. The pinned upstream's media
downloader is intentionally not used: its exact-filename lookup misses
WeChat's collision-renamed files (for example, ``paper(1).pdf``).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from .cached import CachedError


_MESSAGE_ID = re.compile(r"^([A-Za-z0-9_.-]{1,128}):([0-9]{1,18})$")
_MD5 = re.compile(r"[a-fA-F0-9]{32}\Z")


def _file_metadata(content: str) -> tuple[str, int | None, str | None]:
    if not isinstance(content, str) or len(content) > 1_000_000:
        raise CachedError("attachment_metadata_unavailable")
    if "<!DOCTYPE" in content.upper() or "<!ENTITY" in content.upper():
        raise CachedError("attachment_metadata_unavailable")
    try:
        xml = ET.fromstring(content.strip())
    except ET.ParseError:
        raise CachedError("attachment_metadata_unavailable") from None
    app = xml if xml.tag == "appmsg" else xml.find(".//appmsg")
    if app is None or app.findtext("type", "").strip() != "6":
        raise CachedError("message_is_not_file_attachment")
    name = (app.findtext("title") or "").strip()
    if (not name or name in (".", "..") or "/" in name or "\\" in name
            or "\x00" in name or ":" in name):
        raise CachedError("invalid_attachment_filename")
    length = (app.findtext("appattach/totallen") or "").strip()
    size = int(length) if length.isascii() and length.isdecimal() else None
    digest = (app.findtext("md5") or "").strip()
    digest = digest.lower() if _MD5.fullmatch(digest) else None
    return name, size, digest


def _renamed_variant(actual: str, original: str) -> bool:
    if actual == original:
        return True
    stem, ext = os.path.splitext(original)
    prefix = stem + "("
    return (actual.startswith(prefix) and actual.endswith(")" + ext)
            and actual[len(prefix):-len(ext) - 1].isascii()
            and actual[len(prefix):-len(ext) - 1].isdecimal())


def _hash_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locate_file(db, chat: str, message_id: str) -> dict:
    """Return a verified absolute path for one explicit, shard-unique file.

    Missing files and hash mismatches are never presented as readable paths.
    The existing account's msg/file tree is the only search root.
    """
    match = _MESSAGE_ID.fullmatch(message_id)
    if match is None:
        raise CachedError("invalid_message_id_use_shard_colon_local_id")
    shard, local_id = match.group(1), int(match.group(2))
    # WeChat 4.x encodes appmsg subtype in the high 32 bits of local_type.
    # For example, a type-6 file can be 0x600000031 rather than literal 49.
    # Query by the exact shard and local ID, then validate the base type and
    # the appmsg XML; upstream's local_type=49 SQL filter drops these rows.
    row = db.get_message_row(chat, local_id, shard=shard)
    if row is None:
        raise CachedError("file_message_not_found_in_shard")
    if row.get("shard") != shard:
        raise CachedError("file_message_shard_mismatch")
    local_type = row.get("local_type")
    if not isinstance(local_type, int) or (local_type & 0xFFFFFFFF) != 49:
        raise CachedError("message_is_not_file_attachment")
    # get_message_row exposes raw SQLite BLOBs, unlike get_messages which
    # decodes compressed / UTF-8 message contents via _friendly_content.
    content = row.get("content")
    message_type = db._msg_type_name(local_type) if isinstance(content, bytes) else None
    if isinstance(content, bytes):
        content = db._friendly_content(content, message_type)
    if not isinstance(content, str) or "<appmsg" not in content:
        compressed = row.get("compress_content")
        if isinstance(compressed, bytes):
            content = db._friendly_content(compressed, message_type)
    name, size, expected_md5 = _file_metadata(content)
    root = (Path(db.account_dir) / "msg" / "file").resolve()
    result = {
        "source": "wechat-local-file", "chat": chat,
        "messageId": message_id, "name": name,
        "expectedSize": size, "expectedMd5": expected_md5,
        "status": "not_cached", "path": None, "verification": None,
    }
    if not root.is_dir():
        return result

    # Filter by filename and size before opening any file. A renamed copy is
    # only trusted when a cryptographic digest identifies its contents.
    candidates = []
    for directory, _, files in os.walk(root, followlinks=False):
        for filename in files:
            if not _renamed_variant(filename, name):
                continue
            path = Path(directory) / filename
            try:
                if not path.resolve().is_relative_to(root) or not path.is_file():
                    continue
                if size is not None and path.stat().st_size != size:
                    continue
            except OSError:
                continue
            if filename != name and expected_md5 is None:
                continue
            candidates.append(path)

    if not candidates:
        return result
    verified = []
    for path in candidates:
        try:
            observed_md5 = _hash_file(path) if expected_md5 else None
            if expected_md5 is None or observed_md5 == expected_md5:
                verified.append((path, observed_md5))
        except OSError:
            continue

    if not verified:
        result["status"] = "checksum_mismatch" if expected_md5 else "not_cached"
        return result
    # An exact filename takes precedence; identical-content renamed copies
    # are equivalent when the MD5 matches. No unverified ambiguity is picked.
    if not expected_md5 and len(verified) != 1:
        result["status"] = "ambiguous_unverified_file"
        return result
    verified.sort(key=lambda entry: (entry[0].name != name, str(entry[0]).lower()))
    path, observed_md5 = verified[0]
    result.update({
        "status": "available", "path": str(path),
        "size": path.stat().st_size, "md5": observed_md5,
        "verification": "md5_and_size" if expected_md5 and size is not None
                        else "md5" if expected_md5 else "exact_name_and_size"
                        if size is not None else "exact_name_only",
    })
    return result
