"""Pure read-only adapter for the upstream wechatauto-replica WeChatDB API.

Do NOT import or instantiate the real upstream package here. Its WeChatDB
constructor scans WeChat process memory and caches DB keys when necessary.
Live factory wiring is intentionally deferred pending user authorization.

This module can be unit tested against a synthetic WeChatDB-compatible object.
"""

from __future__ import annotations

from datetime import datetime
from importlib import metadata
from typing import Any

MAX_SCAN = 1000


def installation_status() -> dict:
    """Inspect package metadata only; never import or run upstream code."""
    try:
        installed = metadata.version("wechatauto-replica")
    except metadata.PackageNotFoundError:
        installed = None
    return {
        "source": "wechatauto-replica",
        "installedVersion": installed,
        "apiAdapted": True,
        "liveReadingEnabled": False,
        "realMessageReadVerified": False,
        "requiresProcessMemoryKeyAccess": True,
        "snapshotModeRequiresProcessMemoryKeyAccess": False,
        "windowAutomation": False,
        "reason": (
            "Adapter is ready for offline tests. Live WeChatDB initialization "
            "may scan process memory and create plaintext DB/key caches. "
            "This project does not enable it without separate approval."
        ),
    }


def _time_bound(value: str | None, *, is_end: bool) -> int | None:
    if value is None:
        return None
    if len(value) == 8 and value.isdecimal():
        parsed = datetime.strptime(value, "%Y%m%d")
        # Search through the entire ending date.
        return int(parsed.timestamp()) + (86399 if is_end else 0)
    timestamp = int(value)
    if timestamp >= 10**12:
        timestamp //= 1000
    return timestamp


def _normalize_row(row: dict) -> dict:
    # Upstream local_id values are only unique *within a shard*.
    local_id = row.get("local_id")
    shard = row.get("shard") or ""
    message_id = None
    if local_id is not None and shard:
        message_id = f"{shard}:{local_id}"
    return {
        "id": message_id,
        "timestamp": row.get("create_time"),
        "sender": row.get("sender_username") or None,
        "senderId": row.get("sender_id"),
        "content": row.get("content"),
        "type": row.get("type"),
        "sortSequence": row.get("sort_seq"),
    }


class ReplicaReader:
    """Adapts a *provided* WeChatDB-compatible instance; never creates one."""

    def __init__(self, db: Any):
        if db is None:
            raise ValueError("Provide an already authorized WeChatDB object")
        self.db = db

    def sessions(self, *, limit: int, keyword: str | None = None) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("limit outside supported range")
        # Account for local filtering without unbounded contact scans.
        raw = self.db.get_sessions(limit=MAX_SCAN if keyword else limit)
        if not isinstance(raw, list):
            raise ValueError("Unexpected upstream sessions response")
        output = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            username = item.get("username")
            if not isinstance(username, str) or not username:
                continue
            # get_nickname only queries upstream contact data; it does not
            # operate the desktop. Do not make extra calls for empty names.
            name = self.db.get_nickname(username)
            name = name if isinstance(name, str) else username
            if keyword and keyword.casefold() not in (name + " " + username).casefold():
                continue
            output.append({
                "id": username,
                "name": name,
                "type": "group" if username.endswith("@chatroom") else "private",
                "lastTimestamp": item.get("last_time"),
                "unreadCount": item.get("unread"),
            })
            if len(output) >= limit:
                break
        return {
            "source": "wechatauto-replica",
            "coverage": "upstream_available_sessions",
            "count": len(output),
            "sessions": output,
        }

    def messages(self, *, chat: str, limit: int, offset: int = 0,
                 keyword: str | None = None,
                 start: str | None = None, end: str | None = None) -> dict:
        if not chat or not isinstance(chat, str):
            raise ValueError("Explicit chat ID required")
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise ValueError("Invalid pagination")
        lower = _time_bound(start, is_end=False)
        upper = _time_bound(end, is_end=True)
        if lower is not None and upper is not None and lower > upper:
            raise ValueError("Start date must not follow end date")
        filtering = keyword is not None or start is not None or end is not None
        # For unfiltered pagination the upstream merges per-shard rows.
        # For filters, only inspect a capped recent window and label it as
        # incomplete: don't silently pretend to search full history.
        fetch_limit = MAX_SCAN if filtering else min(MAX_SCAN, limit + 1)
        fetch_offset = 0 if filtering else offset
        rows = self.db.get_messages(chat, limit=fetch_limit, offset=fetch_offset)
        if not isinstance(rows, list):
            raise ValueError("Unexpected upstream messages response")
        selected = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            timestamp = row.get("create_time")
            if lower is not None or upper is not None:
                if not isinstance(timestamp, (int, float)):
                    continue
                if lower is not None and timestamp < lower:
                    continue
                if upper is not None and timestamp > upper:
                    continue
            if keyword is not None and keyword.casefold() not in str(row.get("content") or "").casefold():
                continue
            selected.append(row)
        window = selected[offset:offset + limit] if filtering else selected[:limit]
        return {
            "source": "wechatauto-replica",
            "chat": chat,
            "coverage": "recent_window_only" if filtering else "upstream_available_messages_only",
            "completeHistory": False,
            "count": len(window),
            "hasMore": None if filtering else len(rows) > limit,
            "searchWindowLimit": MAX_SCAN if filtering else None,
            "scanned": len(rows),
            "offset": offset,
            "messages": [_normalize_row(row) for row in window],
        }
