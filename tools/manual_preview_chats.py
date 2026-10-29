"""One-shot, explicitly user-run preview of two authorized WeChat data types.

NEVER run with --read-live in CCM, CI, automated tests, or an agent. A person
must launch the command locally. It can inspect Weixin.exe process memory to
recover keys. Results: up to 20 session headers and 5 recent filehelper
messages, in .state/manual-selected-preview.json (ignored by Git).

By default, no keys are saved. With separately requested --save-keys,
validated per-database keys are encrypted under the current Windows user via
DPAPI for reuse without another process memory scan. This must be launched by
the owner in the local terminal; never by CCM or tests. Upstream decrypted
SQLite cache is confined to a temporary directory removed at process exit.
The raw upstream diagnostic output is not persisted or printed.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / ".state" / "manual-selected-preview.json"


def _preview(*, save_keys: bool = False) -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from wxbridge.replica import ReplicaReader
    from wxbridge.keyvault import seal_verified_keys
    from wxbridge.snapshot import _load_upstream

    result = {
        "source": "original_wechatauto_replica",
        "realDataPreview": True,
        "sessions": None,
        "filehelper": None,
        "sessionsErrorClass": None,
        "filehelperErrorClass": None,
        "initializationErrorClass": None,
        "verifiedKeys": 0,
        "databaseFiles": 0,
        "keyCachesWritten": False,
        "dpapiKeyCacheSaved": False,
        "keyCacheEntryCount": 0,
        "keyCacheErrorClass": None,
        "decryptedDatabaseCachesKept": False,
    }
    module = _load_upstream()
    db_cls = module.WeChatDB
    original_save = db_cls._save_keys
    db_cls._save_keys = lambda self: None
    try:
        # Use a unique temporary location for decrypted databases. It is
        # explicitly deleted after the two narrowly scoped queries.
        with tempfile.TemporaryDirectory(prefix="manual-wxpreview-",
                                         dir=str(ROOT / ".state")) as temp:
            try:
                # Upstream could print account-specific or secret information;
                # keep that text out of terminal logs and the JSON output.
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    db = db_cls(
                        workdir=temp,
                        keys_file=str(Path(temp) / "keys.json"),
                    )
                result["databaseFiles"] = len(db._db_files)
                result["verifiedKeys"] = sum(
                    1 for rel, _, _ in db._db_files if db._key_works(rel))
                if save_keys:
                    try:
                        count = seal_verified_keys(db)
                        result["dpapiKeyCacheSaved"] = True
                        result["keyCacheEntryCount"] = count
                    except Exception as exc:
                        result["keyCacheErrorClass"] = type(exc).__name__
            except Exception as exc:
                result["initializationErrorClass"] = type(exc).__name__
                return result
            reader = ReplicaReader(db)
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result["sessions"] = reader.sessions(limit=20)
            except Exception as exc:
                result["sessionsErrorClass"] = type(exc).__name__
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    result["filehelper"] = reader.messages(
                        chat="filehelper", limit=5)
            except Exception as exc:
                result["filehelperErrorClass"] = type(exc).__name__
    finally:
        db_cls._save_keys = original_save
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--read-live", action="store_true",
                        help="Explicitly authorize live WeChat memory key read and two selected queries")
    parser.add_argument("--save-keys", action="store_true",
                        help="Separately opt into storing verified keys with local Windows-user DPAPI")
    args = parser.parse_args(argv)
    if not args.read_live:
        print("No action. Run --read-live manually in your local terminal.")
        return 2
    if args.save_keys and sys.platform != "win32":
        print("No action. Saving keys requires local Windows DPAPI.")
        return 2
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    # Remove stale output first: the assistant must never mistake an old read
    # for a new result if this run fails.
    RESULT.unlink(missing_ok=True)
    try:
        result = _preview(save_keys=args.save_keys)
    except Exception as exc:
        result = {
            "source": "original_wechatauto_replica",
            "realDataPreview": False,
            "errorClass": type(exc).__name__,
            "keyCachesWritten": False,
        }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    state = {
        "resultFile": str(RESULT),
        "verifiedKeys": result.get("verifiedKeys", 0),
        "databaseFiles": result.get("databaseFiles", 0),
        "sessionCount": (result.get("sessions") or {}).get("count"),
        "filehelperCount": (result.get("filehelper") or {}).get("count"),
        "initializationErrorClass": result.get("initializationErrorClass"),
        "sessionsErrorClass": result.get("sessionsErrorClass"),
        "filehelperErrorClass": result.get("filehelperErrorClass"),
        "dpapiKeyCacheSaved": result.get("dpapiKeyCacheSaved", False),
        "keyCacheEntryCount": result.get("keyCacheEntryCount", 0),
        "keyCacheErrorClass": result.get("keyCacheErrorClass"),
        "errorClass": result.get("errorClass"),
    }
    print(json.dumps(state, ensure_ascii=False))
    complete = result.get("sessions") is not None and result.get("filehelper") is not None
    if args.save_keys:
        complete = complete and bool(result.get("dpapiKeyCacheSaved"))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
