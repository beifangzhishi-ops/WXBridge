"""Read-only WeChat 4.x message-shard inventory.

Ordinary chats live under message_N.db; service/official-account messages
may live under biz_message_N.db.  The pinned upstream enumerates only
ordinary shards, so expose both without modifying its original source.
"""

from __future__ import annotations

import re


_SHARD = re.compile(r"^message/(?:biz_)?message_\d+\.db$", re.IGNORECASE)
_FILE = re.compile(r"^(?:biz_)?message_\d+\.db$", re.IGNORECASE)


def is_message_shard_name(filename: str) -> bool:
    return bool(_FILE.fullmatch(filename))


def message_shards(db_files) -> list[str]:
    """Return only supported message shards, excluding media/FTS/resources."""
    return sorted(
        rel for rel, _, _ in db_files
        if isinstance(rel, str) and _SHARD.fullmatch(rel.replace("\\", "/"))
    )
