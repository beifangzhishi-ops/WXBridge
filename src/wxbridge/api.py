"""Read-only Tailscale HTTP API for a Windows WXBridge Python installation.

The API starts a one-shot local Reader worker. Only the public EXE routes
between machines, and upstream's CLI is never invoked.
"""

from __future__ import annotations

import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
import socket
import subprocess
import sys

from .remote import API_VERSION
from .runtime import app_root
from .identity import local_identity
from .process import NO_CONSOLE_FLAGS


ALLOWED_COMMANDS = frozenset((
    "sessions", "messages", "search", "self", "contacts", "groups",
    "group-members", "labels", "message-chats", "new-messages",
    "message-storage", "media-status", "media-read",
    "moments", "moment", "moment-interactions", "articles", "file-list",
))
MAX_BODY = 8 * 1024
READER_TIMEOUT_SECONDS = 90


def valid_query_args(value: object) -> bool:
    """Only data commands with bounded arguments; never expose UI commands."""
    return (isinstance(value, list) and 1 <= len(value) <= 32
            and all(isinstance(v, str) and 0 < len(v) <= 300 for v in value)
            and value[0] in ALLOWED_COMMANDS)


def run_query(argv: list[str]) -> tuple[int, object]:
    """Run the local-only cached-key Reader on the machine holding the DB."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_root() / "src")
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "wxbridge.local_ops", *argv],
            cwd=str(app_root()), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=READER_TIMEOUT_SECONDS,
            creationflags=NO_CONSOLE_FLAGS,
        )
    except subprocess.TimeoutExpired:
        return 4, {"error": "local_reader_timeout"}
    except OSError:
        return 4, {"error": "local_reader_unavailable"}
    try:
        if completed.returncode == 0:
            return 0, json.loads(completed.stdout)
        error_data = json.loads(completed.stderr.strip().splitlines()[-1])
        return 4, {"error": error_data.get("error", "local_reader_failed")}
    except (IndexError, AttributeError, ValueError, TypeError):
        return 4, {"error": "local_reader_failed"}


def make_handler(secret: str):
    """Create a handler with no mutable global secret and no access logs."""
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def reply(self, status: int, data: dict):
            blob = json.dumps(data, ensure_ascii=True,
                              separators=(",", ":")).encode("ascii")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(blob)

        def authorized(self):
            supplied = self.headers.get("X-WXBridge-Token", "")
            return bool(supplied) and hmac.compare_digest(supplied, secret)

        def do_GET(self):
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            if self.path == "/identity":
                return self.reply(200, {"service": "WXBridge", "protocol": API_VERSION,
                                        **local_identity()})
            if self.path != "/status":
                return self.reply(404, {"error": "not_found"})
            return self.reply(200, {
                "service": "WXBridge", "protocol": API_VERSION,
                "node": os.environ.get("WXBRIDGE_NODE_ID", "unknown"),
                "apiReady": True, "wechatLogin": "unknown",
                "readerReady": "not_checked",
            })

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "unauthorized"})
            if self.path != "/query":
                return self.reply(404, {"error": "not_found"})
            if self.headers.get("X-WXBridge-Protocol") != str(API_VERSION):
                return self.reply(409, {"error": "protocol_mismatch"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    return self.reply(413, {"error": "invalid_request_size"})
                payload = json.loads(self.rfile.read(size))
                args = payload["args"]
                if not valid_query_args(args):
                    return self.reply(400, {"error": "invalid_query_args"})
            except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                return self.reply(400, {"error": "invalid_request"})
            code, result = run_query(args)
            if code == 0:
                return self.reply(200, {
                    "protocol": API_VERSION, "exitCode": 0, "data": result,
                })
            return self.reply(200, {
                "protocol": API_VERSION, "exitCode": code,
                "error": result.get("error", "remote_query_failed"),
            })
    return Handler


class ExclusiveHTTPServer(ThreadingHTTPServer):
    """Prevent a new API from sharing a port with a stale Windows process.

    Windows SO_REUSEADDR permits competing listeners, unlike Linux semantics.
    Fail startup instead of letting queries silently hit an older API.
    """

    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WXBridge Tailscale-only API")
    parser.add_argument("--bind", required=True, help="Tailscale IPv4 address")
    parser.add_argument("--port", type=int, default=18763)
    args = parser.parse_args(argv)
    address = ipaddress.ip_address(args.bind)
    if (address not in ipaddress.ip_network("100.64.0.0/10")
            or not 1 <= args.port <= 65535):
        parser.error("bind a valid Tailscale IPv4 address and TCP port")
    secret = os.environ.get("WXBRIDGE_API_TOKEN", "")
    if len(secret) < 24:
        parser.error("WXBRIDGE_API_TOKEN must contain at least 24 characters")
    server = ExclusiveHTTPServer((args.bind, args.port), make_handler(secret))
    try:
        print("WXBridge API listening on Tailscale port %d" % args.port,
              flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
