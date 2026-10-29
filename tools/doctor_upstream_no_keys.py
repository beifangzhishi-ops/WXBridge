"""Inspect upstream DB layout without constructing WeChatDB or extracting keys.

All output is aggregate metadata. Never prints paths, usernames, database
contents, account names, or key material.
Requires the pinned, independently cloned upstream checkout.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from check_upstream_core import load_upstream_db


def report():
    upstream = load_upstream_db()
    root = upstream.auto_detect_db_dir()
    result = {
        "upstreamCommitVerified": True,
        "databaseRootLocated": bool(root),
        "accountDirectories": 0,
        "databaseFiles": 0,
        "sessionDatabasePresent": False,
        "contactDatabasePresent": False,
        "messageShards": 0,
        "encryptedDatabaseOpened": False,
        "processMemoryAccessed": False,
        "realMessagesRead": False,
    }
    if not root:
        return result
    accounts = upstream._find_account_dirs(root)
    result["accountDirectories"] = len(accounts)
    for account in accounts[:20]:
        base = Path(account) / "db_storage"
        for where, _, files in os.walk(base):
            for name in files:
                if not name.lower().endswith(".db"):
                    continue
                result["databaseFiles"] += 1
                if name.lower() == "session.db":
                    result["sessionDatabasePresent"] = True
                elif name.lower() == "contact.db":
                    result["contactDatabasePresent"] = True
                elif name.lower().startswith("message_") and name.lower().endswith(".db"):
                    result["messageShards"] += 1
    return result


def main():
    try:
        data = report()
    except Exception as error:
        # Never print raw exception text, which might contain personal paths.
        data = {
            "diagnosis": "failed",
            "errorClass": type(error).__name__,
            "encryptedDatabaseOpened": False,
            "processMemoryAccessed": False,
            "realMessagesRead": False,
        }
        print(json.dumps(data))
        return 1
    print(json.dumps(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
