"""Offline smoke test against the untouched upstream DB implementation.

Requires a separately cloned upstream at .vendor/replica-src.
Never constructs WeChatDB, reads user files, or accesses WeChat memory.
"""

import hashlib
import hmac
import importlib.util
import json
import logging
from pathlib import Path
import struct
import subprocess
import sys
import types


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / ".vendor" / "replica-src"
PIN = "6e603974bbac3bda93d88bbd6995510ae2547f5c"


def load_upstream_db():
    # CCM checkouts may be owned by Windows Administrators. Scope Git trust
    # to this exact pinned upstream path without changing global settings.
    p = subprocess.run(["git", "-c", "safe.directory=" + str(UPSTREAM),
                        "-C", str(UPSTREAM), "rev-parse", "HEAD"],
                       check=True, text=True, capture_output=True)
    if p.stdout.strip() != PIN:
        raise RuntimeError("Unsupported upstream commit")

    # Upstream wechatauto/__init__.py imports the complete sending/UI stack.
    # Loading db.py in isolation prevents unrelated GUI imports. The db.py
    # source is the original unchanged file.
    root = UPSTREAM / "wechatauto"
    package = types.ModuleType("wechatauto")
    package.__path__ = [str(root)]
    sys.modules["wechatauto"] = package
    logger = types.ModuleType("wechatauto.logger")
    logger.wxlog = logging.getLogger("wxbridge.upstream.readonly")
    sys.modules["wechatauto.logger"] = logger
    spec = importlib.util.spec_from_file_location("wechatauto.db", root / "db.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load upstream database module")
    db = importlib.util.module_from_spec(spec)
    sys.modules["wechatauto.db"] = db
    spec.loader.exec_module(db)
    return db


def main():
    db = load_upstream_db()
    key = bytes(range(32))
    salt = bytes(range(16, 32))
    page = bytearray(db.PAGE_SZ)
    page[:16] = salt
    for i in range(16, db.PAGE_SZ - db.RESERVE_SZ + 16):
        page[i] = (i * 7 + 3) % 256
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", key, mac_salt, 2, dklen=32)
    data = bytes(page[16: db.PAGE_SZ - db.RESERVE_SZ + 16])
    auth = hmac.new(mac_key, data, hashlib.sha512)
    auth.update(struct.pack("<I", 1))
    page[-64:] = auth.digest()
    valid = db._verify_enc_key(key, bytes(page))
    invalid = not db._verify_enc_key(bytes(range(1, 33)), bytes(page))
    print(json.dumps({
        "upstreamCommit": PIN[:12],
        "upstreamDbModuleImported": True,
        "syntheticCorrectKeyVerified": valid,
        "syntheticWrongKeyRejected": invalid,
        "realChatsAccessed": False,
        "wechatMemoryAccessed": False,
    }))
    return 0 if valid and invalid else 1


if __name__ == "__main__":
    raise SystemExit(main())
