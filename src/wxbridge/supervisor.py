"""Keep the local read-only API alive without a console or remote dependencies.

This is an internal Windows deployment worker, not a public WXBridge CLI.
The scheduled task starts one supervisor; the supervisor owns only its child
API process. It never terminates a listener owned by another process.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib import request


PORT = 18763
HEALTH_INTERVAL = 5
HEALTH_TIMEOUT = 2
STARTUP_GRACE = 20
MAX_HEALTH_FAILURES = 3


def api_healthy(bind: str, node: str, token: str) -> bool:
    """Probe the authenticated local API directly, without system proxies."""
    opener = request.build_opener(request.ProxyHandler({}))
    req = request.Request(
        f"http://{bind}:{PORT}/status",
        headers={"X-WXBridge-Token": token},
    )
    try:
        with opener.open(req, timeout=HEALTH_TIMEOUT) as response:
            payload = json.loads(response.read(2048))
        return (payload.get("apiReady") is True
                and payload.get("node") == node)
    except (OSError, ValueError, TypeError, KeyError):
        return False


def port_occupied(bind: str) -> bool:
    try:
        with socket.create_connection((bind, PORT), timeout=1):
            return True
    except OSError:
        return False


def acquire_singleton(state: Path):
    """Windows byte-range lock held for the lifetime of the supervisor."""
    import msvcrt

    lock = (state / "api-supervisor.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        return None
    return lock


def configure_log(state: Path) -> logging.Logger:
    logger = logging.getLogger("wxbridge.supervisor")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = RotatingFileHandler(
        state / "api-supervisor.log", maxBytes=128 * 1024,
        backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    return logger


def stop_child(child: subprocess.Popen) -> None:
    if child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)


def supervise(node: str, bind: str, root: Path) -> int:
    state = root / ".state"
    state.mkdir(exist_ok=True)
    log = configure_log(state)
    singleton = acquire_singleton(state)
    if singleton is None:
        log.info("supervisor_duplicate_ignored")
        return 0

    child = None
    try:
        token = (state / "api-token.txt").read_text(encoding="ascii").strip()
        if len(token) < 24:
            log.error("invalid_local_token")
            return 2

        env = os.environ.copy()
        env["WXBRIDGE_API_TOKEN"] = token
        env["WXBRIDGE_NODE_ID"] = node
        env["PYTHONPATH"] = str(root / "src")
        log.info("supervisor_started node=%s", node)

        while True:
            # An already-running API must not be killed or replaced.
            if port_occupied(bind):
                log.warning("port_owned_by_external_process")
                while port_occupied(bind):
                    time.sleep(HEALTH_INTERVAL)
                continue

            try:
                child = subprocess.Popen(
                    [sys.executable, "-m", "wxbridge.api",
                     "--bind", bind, "--port", str(PORT)],
                    cwd=str(root), env=env, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except OSError as exc:
                log.error("api_spawn_failed class=%s", type(exc).__name__)
                time.sleep(HEALTH_INTERVAL)
                continue

            log.info("api_started pid=%d", child.pid)
            started = time.monotonic()
            failures = 0
            while child.poll() is None:
                if api_healthy(bind, node, token):
                    failures = 0
                elif time.monotonic() - started >= STARTUP_GRACE:
                    failures += 1
                    if failures >= MAX_HEALTH_FAILURES:
                        log.warning("api_unhealthy_restarting pid=%d",
                                    child.pid)
                        break
                time.sleep(HEALTH_INTERVAL)

            stop_child(child)
            log.warning("api_stopped code=%s", child.returncode)
            child = None
            time.sleep(HEALTH_INTERVAL)
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception as exc:
        # Do not record credentials, paths, tracebacks, or message data.
        log.error("supervisor_failed class=%s", type(exc).__name__)
        return 1
    finally:
        if child is not None:
            stop_child(child)
        singleton.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Internal WXBridge API supervisor")
    parser.add_argument("--node", choices=("6v", "noha"), required=True)
    parser.add_argument("--bind", required=True)
    args = parser.parse_args(argv)
    address = ipaddress.ip_address(args.bind)
    if address not in ipaddress.ip_network("100.64.0.0/10"):
        parser.error("bind must be a Tailscale IPv4")
    return supervise(args.node, str(address),
                     Path(__file__).resolve().parents[2])


if __name__ == "__main__":
    raise SystemExit(main())
