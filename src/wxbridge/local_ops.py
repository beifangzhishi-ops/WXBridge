"""Internal one-shot, read-only data worker used *only* by the local API.

This is not the public CLI, nor upstream's CLI. It never chooses an environment.
Each API request runs in a short-lived subprocess, isolating DB/decrypted
scratch lifetime and avoiding shared process stdout captures.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import sqlite3
import sys

from .cached import CachedError, open_cached_reader
from .extras import read_extra
from .keyvault import KeyVaultError


EXTRA_COMMANDS = (
    "self", "contacts", "groups", "group-members", "labels",
    "message-chats", "new-messages", "message-storage",
    "media-status", "media-read", "file-list",
    "moments", "moment", "moment-interactions", "articles",
)


def _text(value: str) -> str:
    if not value.strip() or len(value) > 300:
        raise argparse.ArgumentTypeError("value must be 1-300 characters")
    return value


def _limit(value: str) -> int:
    try:
        num = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid limit") from None
    if not 1 <= num <= 100:
        raise argparse.ArgumentTypeError("limit must be 1-100")
    return num


def _offset(value: str) -> int:
    try:
        num = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("invalid offset") from None
    if not 0 <= num <= 100000:
        raise argparse.ArgumentTypeError("offset must be 0-100000")
    return num


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Internal local database reader; not the public EXE")
    commands = p.add_subparsers(dest="command", required=True)
    sessions = commands.add_parser("sessions")
    sessions.add_argument("--limit", type=_limit, default=20)
    sessions.add_argument("--keyword", type=_text)
    for name in ("messages", "search"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--chat", type=_text, required=True)
        cmd.add_argument("--limit", type=_limit, default=30)
        cmd.add_argument("--offset", type=_offset, default=0)
        cmd.add_argument("--start", type=_text)
        cmd.add_argument("--end", type=_text)
        if name == "search":
            cmd.add_argument("--keyword", type=_text, required=True)
    for name in EXTRA_COMMANDS:
        cmd = commands.add_parser(name)
        if name == "contacts":
            cmd.add_argument("--keyword", type=_text, required=True)
        if name in ("group-members", "new-messages", "message-storage",
                    "media-status", "media-read", "articles", "file-list"):
            cmd.add_argument("--chat", type=_text, required=True)
        if name in ("moments",):
            cmd.add_argument("--chat", type=_text)
            cmd.add_argument("--keyword", type=_text)
        if name == "file-list":
            cmd.add_argument("--keyword", type=_text)
        if name == "new-messages":
            cmd.add_argument("--since-seq", type=int, required=True)
        if name == "media-status":
            cmd.add_argument("--local-id", type=int, required=True)
            cmd.add_argument("--shard", type=_text)
            cmd.add_argument("--kind", choices=("image", "voice"), required=True)
        if name == "media-read":
            cmd.add_argument("--message-id", type=_text, required=True)
        if name == "moment":
            cmd.add_argument("--tid", type=int, required=True)
        if name == "moment-interactions":
            cmd.add_argument("--unread", action="store_true")
        if name not in ("self", "media-status", "media-read", "moment"):
            cmd.add_argument("--limit", type=_limit, default=20)
        if name in ("moments", "moment-interactions", "articles", "file-list"):
            cmd.add_argument("--offset", type=_offset, default=0)
    return p


def execute(args) -> dict:
    with open_cached_reader() as reader:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            if args.command in EXTRA_COMMANDS:
                return read_extra(reader, args.command, args)
            if args.command == "sessions":
                return reader.sessions(limit=args.limit, keyword=args.keyword)
            return reader.messages(
                chat=args.chat, limit=args.limit, offset=args.offset,
                keyword=args.keyword if args.command == "search" else None,
                start=args.start, end=args.end,
            )


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0
    except KeyVaultError as error:
        code = "key_not_found" if str(error).startswith("no_local_key_cache") else "key_unavailable"
        print(json.dumps({"error": code}), file=sys.stderr)
    except CachedError as error:
        code = ("key_unavailable" if str(error) in (
            "cached_account_does_not_match_storage",
            "cache_missing_or_stale_for_current_databases") else "database_read_failed")
        print(json.dumps({"error": code}), file=sys.stderr)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(json.dumps({"error": "local_operation_failed", "message": type(error).__name__}),
              file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
