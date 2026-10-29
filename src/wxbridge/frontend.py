"""One public EXE: account-aware routing over the symmetric read-only APIs.

This is intentionally NOT imported by the API's local Python CLI. It never
opens a WeChat database or searches the desktop itself.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .paths import STATE
from .remote import RemoteError, query_identity, query_remote

ENVIRONMENTS = {"6v": "DESKTOP-KFL6V1F", "noha": "noha"}


class FrontendError(ValueError):
    pass


def _bounded(value: str) -> str:
    if not value.strip() or len(value) > 300:
        raise argparse.ArgumentTypeError("Provide 1-300 nonblank characters")
    return value


def _limit(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Limit must be an integer") from None
    if not 1 <= number <= 100:
        raise argparse.ArgumentTypeError("Limit must be 1-100")
    return number


def _offset(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Offset must be an integer") from None
    if not 0 <= number <= 100000:
        raise argparse.ArgumentTypeError("Offset must be 0-100000")
    return number


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="WXBridge.exe", description="Read-only WeChat queries via the online account's API."
    )
    p.add_argument("--account", type=_bounded,
                   help="Account ID or alias from .state/accounts.json; default: configured account")
    commands = p.add_subparsers(dest="command")
    chats = commands.add_parser("chats", help="Recent conversations or find a contact/group")
    chats.add_argument("--keyword", type=_bounded)
    chats.add_argument("--limit", type=_limit, default=20)
    chats.add_argument("--stored", action="store_true", help="Historical message DB index, not recent order")
    messages = commands.add_parser("messages", help="Read recent messages; search or paginate")
    messages.add_argument("--chat", required=True, type=_bounded)
    messages.add_argument("--keyword", type=_bounded)
    messages.add_argument("--limit", type=_limit, default=30)
    messages.add_argument("--offset", type=_offset, default=0)
    messages.add_argument("--before", type=_bounded,
                          help="Inclusive YYYYMMDD or Unix timestamp, capped search window")
    files = commands.add_parser("files", help="List file attachments or locate an already cached file")
    files.add_argument("--chat", required=True, type=_bounded)
    files.add_argument("--id", type=_bounded, help="Exact message ID for a downloaded file")
    files.add_argument("--keyword", type=_bounded)
    files.add_argument("--limit", type=_limit, default=20)
    files.add_argument("--offset", type=_offset, default=0,
                       help="Message offset for scanning the next historical window")
    moments = commands.add_parser("moments", help="Recent Moments, detail or interactions")
    moments.add_argument("--user", type=_bounded, help="Friend nickname or account ID")
    moments.add_argument("--id", type=int, help="Moment ID for details")
    moments.add_argument("--interactions", action="store_true")
    moments.add_argument("--unread", action="store_true")
    moments.add_argument("--keyword", type=_bounded)
    moments.add_argument("--limit", type=_limit, default=20)
    moments.add_argument("--offset", type=_offset, default=0)
    return p


def _config() -> dict:
    path = STATE / "accounts.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise FrontendError("invalid_accounts_config") from None
    if not isinstance(value, dict):
        raise FrontendError("invalid_accounts_config")
    return value


def select_node(requested: str | None) -> tuple[str, str]:
    cfg = _config()
    aliases = cfg.get("aliases", {})
    if not isinstance(aliases, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) or not k or not v
        for k, v in aliases.items()
    ):
        raise FrontendError("invalid_accounts_config")
    chosen = requested if requested is not None else cfg.get("default")
    if chosen is not None and not isinstance(chosen, str):
        raise FrontendError("invalid_accounts_config")
    account_id = aliases.get(chosen, chosen) if chosen else None
    results = {}
    failures = {}
    for node in ENVIRONMENTS:
        try:
            results[node] = query_identity(node)
        except RemoteError as exc:
            failures[node] = str(exc)
    # An unresponsive node may also host the same account. Don't silently
    # choose the other one when uniqueness cannot be established.
    if failures:
        raise FrontendError("environment_status_unavailable:" + ",".join(sorted(failures)))
    candidates = [(node, data["accountId"]) for node, data in results.items()
                  if data["state"] == "candidate" and data.get("accountId")]
    unknown = [node for node, data in results.items() if data["state"] == "unknown"]
    if unknown:
        raise FrontendError("wechat_status_unknown:" + ",".join(unknown))
    if account_id:
        candidates = [(node, ident) for node, ident in candidates if ident == account_id]
    elif len({ident for _, ident in candidates}) > 1:
        raise FrontendError("multiple_accounts_select_with_--account")
    if len(candidates) > 1:
        raise FrontendError("account_present_on_multiple_environments")
    if not candidates:
        raise FrontendError("account_not_found_on_running_wechat")
    return candidates[0]


def _query(node: str, command: str, *args: str) -> dict:
    code, result = query_remote([command, *args], node=node)
    if code != 0:
        raise FrontendError(str(result.get("error", "remote_query_failed")))
    if not isinstance(result, dict):
        raise FrontendError("invalid_query_response")
    return result


def _resolve_chat(node: str, chat: str) -> str:
    # Use internal identifiers unchanged, including official accounts and
    # filehelper. Otherwise distinguish exact matches from fuzzy candidates.
    if chat.startswith(("wxid_", "gh_")) or chat.endswith("@chatroom") or chat == "filehelper":
        return chat
    sessions = _query(node, "sessions", "--keyword", chat, "--limit", "100").get("sessions", [])
    contacts = _query(node, "contacts", "--keyword", chat, "--limit", "100").get("contacts", [])
    found = {}
    for item in [*sessions, *contacts]:
        if not isinstance(item, dict):
            continue
        ident = item.get("id") or item.get("username")
        if not isinstance(ident, str) or not ident:
            continue
        names = [str(item.get(key) or "") for key in ("name", "nick_name", "remark", "nickname")]
        if chat == ident or chat in names:
            found[ident] = item
    if len(found) == 1:
        return next(iter(found))
    if len(found) > 1:
        raise FrontendError("ambiguous_chat:" + ",".join(sorted(found)[:10]))
    raise FrontendError("chat_not_found_use_chats_--keyword")


def _chats(node: str, args) -> dict:
    if args.stored:
        result = _query(node, "message-chats", "--limit", str(args.limit))
        result["ordering"] = "message_count_not_recency"
        return result
    if not args.keyword:
        return _query(node, "sessions", "--limit", str(args.limit))
    sessions = _query(node, "sessions", "--keyword", args.keyword, "--limit", "100")
    contacts = _query(node, "contacts", "--keyword", args.keyword, "--limit", "100")
    groups = _query(node, "groups", "--limit", "100")
    combined = []
    seen = set()
    for data, key in ((sessions, "sessions"), (contacts, "contacts"), (groups, "groups")):
        for item in data.get(key, []):
            if not isinstance(item, dict):
                continue
            ident = item.get("id") or item.get("username")
            if not ident or ident in seen:
                continue
            if key == "groups" and args.keyword.casefold() not in json.dumps(item, ensure_ascii=False).casefold():
                continue
            seen.add(ident)
            combined.append(item)
            if len(combined) >= args.limit:
                break
        if len(combined) >= args.limit:
            break
    return {"source": "wechat-local-db", "count": len(combined),
            "chats": combined, "coverage": "recent_sessions_and_contact_lookup"}


def _dispatch(node: str, args) -> dict:
    if args.command == "chats":
        return _chats(node, args)
    if args.command == "messages":
        chat = _resolve_chat(node, args.chat)
        argv = ["--chat", chat, "--limit", str(args.limit),
                "--offset", str(args.offset)]
        if args.keyword:
            argv += ["--keyword", args.keyword]
        if args.before:
            argv += ["--end", args.before]
        return _query(node, "search" if args.keyword else "messages", *argv)
    if args.command == "files":
        chat = _resolve_chat(node, args.chat)
        if args.id:
            return _query(node, "media-read", "--chat", chat, "--message-id", args.id)
        argv = ["--chat", chat, "--limit", str(args.limit),
                "--offset", str(args.offset)]
        if args.keyword:
            argv += ["--keyword", args.keyword]
        return _query(node, "file-list", *argv)
    if args.command == "moments":
        if args.id is not None:
            if args.interactions or args.user or args.keyword or args.unread:
                raise FrontendError("incompatible_moments_options")
            return _query(node, "moment", "--tid", str(args.id))
        if args.interactions:
            if args.user or args.keyword:
                raise FrontendError("incompatible_moments_options")
            argv = ["--limit", str(args.limit), "--offset", str(args.offset)]
            if args.unread:
                argv.append("--unread")
            return _query(node, "moment-interactions", *argv)
        if args.unread:
            raise FrontendError("--unread_requires_--interactions")
        argv = ["--limit", str(args.limit), "--offset", str(args.offset)]
        if args.user:
            argv += ["--chat", _resolve_chat(node, args.user)]
        if args.keyword:
            argv += ["--keyword", args.keyword]
        return _query(node, "moments", *argv)
    raise FrontendError("unsupported_command")


def main(argv=None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if args.command is None:
        p.print_help()
        return 0
    try:
        node, account_id = select_node(args.account)
        data = _dispatch(node, args)
        # Routing metadata is set only at the EXE boundary, never accepted
        # as a caller-provided field or read from the remote response.
        data["environment_id"] = ENVIRONMENTS[node]
        data["account_id"] = account_id
        data["loginVerified"] = False
        print(json.dumps(data, ensure_ascii=True, separators=(",", ":")))
        return 0
    except (FrontendError, RemoteError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
