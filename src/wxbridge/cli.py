"""WXBridge command interface. All data operations are read-only."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sqlite3
import sys
import re

from .preflight import preflight
from .snapshot import SnapshotError, SnapshotReader
from .cached import CachedError, open_cached_reader
from .keyvault import KeyVaultError
from .extras import read_extra
from .runtime import app_root, frozen
from .remote import RemoteError, query_remote

EXTRA_COMMANDS = (
    "self", "contacts", "groups", "group-members", "labels",
    "message-chats", "new-messages", "message-storage",
    "media-status", "media-read",
    "moments", "moment", "moment-interactions", "articles",
)


def get_version():
    try:
        return version("wxbridge")
    except PackageNotFoundError:
        pass
    # Avoid adding tomllib/tomli to the separate Python 3.9 upstream DB
    # environment. The project source has one anchored version declaration.
    root = Path(sys._MEIPASS) if frozen() else app_root()
    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([0-9][^"\r\n]*)"\s*$', content, re.MULTILINE)
    return match.group(1) if match else "unknown"


def _bounded(value: str) -> str:
    if len(value) > 300 or not value.strip():
        raise argparse.ArgumentTypeError("Must be nonempty and no longer than 300 characters")
    return value


def _limit(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("Limit must be from 1 to 100")
    return number


def _offset(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 100000:
        raise argparse.ArgumentTypeError("Offset must be from 0 to 100000")
    return number


def _date(value: str) -> str:
    if value.isdecimal() and (len(value) == 8 or 10 <= len(value) <= 13):
        return value
    raise argparse.ArgumentTypeError("Use YYYYMMDD or a 10–13 digit Unix timestamp")


def build_parser() -> argparse.ArgumentParser:
    backend_default = ("cached-key" if frozen()
                       else os.environ.get("WXBRIDGE_BACKEND", "cached-key"))
    parser = argparse.ArgumentParser(
        prog="WXBridge.exe" if frozen() else "WXBridge.cmd",
        description="Read-only local WeChat queries. Commands report actual query results; no connection precheck is required.",
    )
    parser.add_argument("--version", action="version", version=get_version())
    parser.add_argument(
        "--backend", choices=("cached-key", "snapshot"),
        default=backend_default,
        help="Select reader (default: " + backend_default + ")",
    )
    parser.add_argument(
        "--allow-local-db", action="store_true",
        help="Local DB permission for source CLI; WXBridge.exe supplies it automatically",
    )
    parser.add_argument(
        "--node", choices=("local", "noha"), default="local",
        help="Read locally (default), or forward to the noha Tailscale API",
    )
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("providers", help="Inspect read-only backends without accessing chat data")
    commands.add_parser("preflight", help="Inspect local WeChat file metadata only (no keys/messages)")
    sessions = commands.add_parser("sessions", help="List conversations in selected backend (JSON)")
    sessions.add_argument("--limit", type=_limit, default=20)
    sessions.add_argument("--keyword", type=_bounded)
    for name in ("messages", "search"):
        cmd = commands.add_parser(name, help="Read only messages in one conversation (JSON)")
        cmd.add_argument("--chat", type=_bounded, required=True)
        cmd.add_argument("--limit", type=_limit, default=50)
        cmd.add_argument("--offset", type=_offset, default=0)
        cmd.add_argument("--start", type=_date)
        cmd.add_argument("--end", type=_date)
        if name == "search":
            cmd.add_argument("--keyword", type=_bounded, required=True)
    for name in EXTRA_COMMANDS:
        cmd = commands.add_parser(name, help="Read-only local WeChat data operation")
        if name in ("contacts",):
            cmd.add_argument("--keyword", type=_bounded, required=True)
        if name in ("group-members", "new-messages", "message-storage", "media-status",
                    "media-read", "articles"):
            cmd.add_argument("--chat", type=_bounded, required=True)
        if name in ("moments",):
            cmd.add_argument("--chat", type=_bounded, help="Optional author wxid")
            cmd.add_argument("--keyword", type=_bounded)
        if name in ("new-messages",):
            cmd.add_argument("--since-seq", type=int, required=True)
        if name == "media-status":
            cmd.add_argument("--local-id", type=int, required=True)
            cmd.add_argument("--shard", type=_bounded)
            cmd.add_argument("--kind", choices=("image", "voice"), required=True)
        if name == "media-read":
            cmd.add_argument("--message-id", type=_bounded, required=True,
                             help="Exact ID from messages, e.g. message__message_3.db:602")
        if name == "moment":
            cmd.add_argument("--tid", type=int, required=True)
        if name == "moment-interactions":
            cmd.add_argument("--unread", action="store_true")
        if name not in ("self", "media-status", "media-read", "moment"):
            cmd.add_argument("--limit", type=_limit, default=20)
        if name in ("moments", "moment-interactions", "articles"):
            cmd.add_argument("--offset", type=_offset, default=0)
    return parser


def _json(value: object) -> None:
    # Windows PowerShell can launch Python with the legacy GBK console
    # encoding. A session title containing emoji or rare characters then
    # causes UnicodeEncodeError even when the underlying DB query succeeded.
    # ASCII-escaped JSON remains valid Unicode once decoded by clients.
    print(json.dumps(value, ensure_ascii=True, separators=(",", ":")))


def main(argv=None) -> int:
    parser = build_parser()
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(raw_argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.node == "noha":
        # Do not forward local diagnostic commands or allow remote shell/GUI.
        if args.command in ("providers", "preflight") or args.backend != "cached-key":
            _json({"error": "unsupported_remote_command"})
            return 4
        try:
            code, result = query_remote(raw_argv[raw_argv.index(args.command):])
        except RemoteError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            return 4
        if code == 0:
            _json(result)
        else:
            print(json.dumps(result), file=sys.stderr)
        return code
    try:
        if args.backend not in ("snapshot", "cached-key"):
            raise ValueError("Invalid backend selection")
        if args.backend == "cached-key" and args.command in (
                "sessions", "messages", "search", *EXTRA_COMMANDS):
            if not args.allow_local_db:
                _json({"error": "local_db_consent_required",
                       "message": "Use --allow-local-db before the command; no process memory is accessed."})
                return 4
            # Requires an existing DPAPI vault, and NEVER scans process memory.
            with open_cached_reader() as cached:
                # Suppress potentially sensitive upstream diagnostics, but do
                # not suppress the normalized JSON response to this CLI user.
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    if args.command in EXTRA_COMMANDS:
                        result = read_extra(cached, args.command, args)
                    elif args.command == "sessions":
                        result = cached.sessions(limit=args.limit, keyword=args.keyword)
                    else:
                        result = cached.messages(
                            chat=args.chat, limit=args.limit, offset=args.offset,
                            keyword=args.keyword if args.command == "search" else None,
                            start=args.start, end=args.end,
                        )
            _json(result)
            return 0
        if args.command in EXTRA_COMMANDS:
            _json({"error": "requires_cached_key_backend",
                   "message": "Select --backend cached-key for this operation"})
            return 4
        reader = None
        if args.backend == "snapshot" and args.command in ("sessions", "messages", "search"):
            reader = SnapshotReader(os.environ.get("WXBRIDGE_SNAPSHOT_DIR", ""))
        if args.command == "providers":
            _json({
                "selected": args.backend,
                "supported": ["cached-key", "snapshot"],
                "note": "Backend selection only; query readiness is determined by actual read commands.",
            })
        elif args.command == "preflight":
            _json(preflight())
        elif args.command == "sessions":
            _json(reader.sessions(limit=args.limit, keyword=args.keyword))
        elif args.command in ("messages", "search"):
            kwargs = dict(
                chat=args.chat, limit=args.limit, offset=args.offset,
                keyword=args.keyword if args.command == "search" else None,
                start=args.start, end=args.end,
            )
            _json(reader.messages(**kwargs))
        return 0
    except SnapshotError as error:
        print(json.dumps({"error": "offline_snapshot_unavailable",
                          "message": str(error)}), file=sys.stderr)
        return 4
    except KeyVaultError as error:
        code = ("key_not_found" if str(error).startswith("no_local_key_cache")
                else "key_unavailable")
        print(json.dumps({"error": code, "message": str(error)}), file=sys.stderr)
        return 4
    except CachedError as error:
        code = ("key_unavailable" if str(error) in (
            "cached_account_does_not_match_storage",
            "cache_missing_or_stale_for_current_databases",
        ) else "database_read_failed")
        print(json.dumps({"error": code, "message": str(error)}),
              file=sys.stderr)
        return 4
    except (OSError, ValueError, sqlite3.Error) as error:
        # Do not echo any personal message content, raw response, or tokens.
        print(json.dumps({"error": "local_operation_failed",
                          "message": type(error).__name__}), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
