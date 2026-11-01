"""Optional read-only HTTP transport to another Tailscale WXBridge node."""

from __future__ import annotations

import json
import os
import ipaddress
import socket
from urllib import error, request
from urllib.parse import urlsplit

from .paths import STATE

class RemoteError(ValueError):
    """A sanitized remote transport or protocol failure."""


API_VERSION = 1


def _transport_error(exc: OSError) -> RemoteError:
    """Separate deadline expiry from connection failures without leaking details."""
    cause = exc.reason if isinstance(exc, error.URLError) else exc
    if isinstance(cause, (TimeoutError, socket.timeout)):
        return RemoteError("remote_timeout")
    return RemoteError("remote_unreachable")


def _private_config(node: str) -> tuple[str, str]:
    """Read only explicitly provisioned Git-ignored node settings."""
    endpoint = ""
    secret = ""
    config = STATE / "nodes.json"
    peer_token = STATE / "peers" / (node + ".token")
    try:
        if config.is_file() and config.stat().st_size <= 4096:
            data = json.loads(config.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                value = data.get(node)
                if isinstance(value, str):
                    endpoint = value
    except (OSError, ValueError, TypeError):
        pass
    try:
        if peer_token.is_file() and peer_token.stat().st_size <= 1024:
            secret = peer_token.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        pass
    return endpoint, secret


def query_remote(argv: list[str], *, node: str = "noha",
                 url: str | None = None,
                 token: str | None = None) -> tuple[int, object]:
    """Forward one CLI data command to either authenticated node."""
    if node not in ("6v", "noha"):
        raise RemoteError("unknown_remote_node")
    prefix = "WXBRIDGE_" + node.upper()
    saved_endpoint, saved_secret = _private_config(node)
    endpoint = (url if url is not None else
                os.environ.get(prefix + "_URL", saved_endpoint)).rstrip("/")
    secret = (token if token is not None else
              os.environ.get(prefix + "_TOKEN", saved_secret))
    if not endpoint.startswith("http://") or not secret:
        raise RemoteError("remote_api_not_configured")
    parsed = urlsplit(endpoint)
    try:
        host = ipaddress.ip_address(parsed.hostname or "")
        if (host not in ipaddress.ip_network("100.64.0.0/10")
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment):
            raise ValueError("wrong endpoint")
    except ValueError:
        raise RemoteError("remote_endpoint_not_tailscale") from None
    body = json.dumps({"args": argv}, separators=(",", ":")).encode("utf-8")
    req = request.Request(
        endpoint + "/query", data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "X-WXBridge-Token": secret,
                 "X-WXBridge-Protocol": str(API_VERSION)},
    )
    try:
        # Bypass unrelated HTTP_PROXY settings for the private Tailscale IP.
        with request.build_opener(request.ProxyHandler({})).open(req, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except error.HTTPError as exc:
        raise RemoteError("remote_http_" + str(exc.code)) from None
    except (error.URLError, TimeoutError, OSError) as exc:
        raise _transport_error(exc) from None
    if len(raw) > 4 * 1024 * 1024:
        raise RemoteError("remote_response_too_large")
    try:
        result = json.loads(raw.decode("utf-8"))
        if result.get("protocol") != API_VERSION:
            raise RemoteError("remote_protocol_mismatch")
        code = result["exitCode"]
        if not isinstance(code, int) or isinstance(code, bool):
            raise ValueError("bad exit code")
        if code == 0:
            return 0, result["data"]
        return code, {"error": result.get("error", "remote_query_failed")}
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, RemoteError):
            raise
        raise RemoteError("remote_invalid_response") from None


def query_identity(node: str) -> dict:
    """Read the authenticated, non-secret local account routing signal."""
    if node not in ("6v", "noha"):
        raise RemoteError("unknown_remote_node")
    endpoint, secret = _private_config(node)
    prefix = "WXBRIDGE_" + node.upper()
    endpoint = os.environ.get(prefix + "_URL", endpoint).rstrip("/")
    secret = os.environ.get(prefix + "_TOKEN", secret)
    if not endpoint.startswith("http://") or not secret:
        raise RemoteError("remote_api_not_configured")
    parsed = urlsplit(endpoint)
    try:
        host = ipaddress.ip_address(parsed.hostname or "")
        if (host not in ipaddress.ip_network("100.64.0.0/10")
                or parsed.username or parsed.password or parsed.path
                or parsed.query or parsed.fragment):
            raise ValueError("wrong endpoint")
    except ValueError:
        raise RemoteError("remote_endpoint_not_tailscale") from None
    req = request.Request(
        endpoint + "/identity", method="GET",
        headers={"X-WXBridge-Token": secret,
                 "X-WXBridge-Protocol": str(API_VERSION)},
    )
    try:
        with request.build_opener(request.ProxyHandler({})).open(req, timeout=8) as response:
            raw = response.read(4097)
    except error.HTTPError as exc:
        raise RemoteError("remote_http_" + str(exc.code)) from None
    except (error.URLError, TimeoutError, OSError) as exc:
        raise _transport_error(exc) from None
    if len(raw) > 4096:
        raise RemoteError("remote_invalid_response")
    try:
        result = json.loads(raw.decode("utf-8"))
        if (result.get("protocol") != API_VERSION
                or result.get("state") not in ("online", "offline")
                or result.get("loginVerified") is not False
                or not isinstance(result.get("accountId"), (str, type(None)))
                or (result.get("state") == "online" and not result.get("accountId"))):
            raise ValueError("bad identity")
        return result
    except (ValueError, TypeError, UnicodeError):
        raise RemoteError("remote_invalid_response") from None
