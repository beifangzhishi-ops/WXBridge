"""Optional read-only HTTP transport to another Tailscale WXBridge node."""

from __future__ import annotations

import json
import os
import ipaddress
from urllib import error, request
from urllib.parse import urlsplit


class RemoteError(ValueError):
    """A sanitized remote transport or protocol failure."""


API_VERSION = 1


def query_remote(argv: list[str], *, url: str | None = None,
                 token: str | None = None) -> tuple[int, object]:
    """Forward one CLI data command; return the remote exit code and JSON."""
    endpoint = (url or os.environ.get("WXBRIDGE_NOHA_URL") or "").rstrip("/")
    secret = token or os.environ.get("WXBRIDGE_NOHA_TOKEN")
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
    except (error.URLError, TimeoutError, OSError):
        raise RemoteError("remote_unreachable") from None
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
