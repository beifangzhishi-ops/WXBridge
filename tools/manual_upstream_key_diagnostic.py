"""Explicit, user-run, privacy-sanitized diagnosis of the pinned upstream core.

Never run --check-live automatically (or from tests/CI/CCM). The user runs
this in an ordinary local PowerShell window after reviewing the command.

The upstream source is never modified. Its key-extraction methods MAY read
memory of locally running Weixin.exe. The diagnostic suppresses upstream
console output, never exports a key or message, never invokes a chat query,
and inhibits writing of key caches. Only a minimal aggregate JSON status is
written, for reading back through CCM without a raw log or transcript.
"""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / ".state" / "manual-key-diagnostic-summary.json"


def diagnose() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    # Use the pinned original db.py; the loader verifies both commit and
    # exact source hash before importing. Avoid package UI imports.
    from wxbridge.snapshot import _load_upstream

    result = {
        "originalUpstreamVerified": False,
        "liveKeyCheckRequested": True,
        "memoryScanInvoked": False,
        "masterKeyCheckInvoked": False,
        "initializationSucceeded": False,
        "databaseFileCount": 0,
        "verifiedKeyCount": 0,
        "remainingEncryptedCount": None,
        "errorClass": None,
        "realMessagesRead": False,
        "rawKeysSaved": False,
    }
    try:
        module = _load_upstream()
        result["originalUpstreamVerified"] = True
    except Exception as exc:
        result["errorClass"] = type(exc).__name__
        return result

    db_type = module.WeChatDB
    original_save = db_type._save_keys
    original_extract = db_type.extract_keys
    original_master = db_type.extract_master_key

    def discard_keys(self):
        # No raw key caches stored during this one-shot diagnostic.
        return None

    def count_extract(self, *args, **kwargs):
        result["memoryScanInvoked"] = True
        return original_extract(self, *args, **kwargs)

    def count_master(self, *args, **kwargs):
        result["masterKeyCheckInvoked"] = True
        return original_master(self, *args, **kwargs)

    db_type._save_keys = discard_keys
    db_type.extract_keys = count_extract
    db_type.extract_master_key = count_master
    try:
        # Original upstream sometimes prints account paths, key-cache names
        # or other sensitive diagnostics. Do not put them on stdout or disk.
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            obj = db_type(
                workdir=str(ROOT / ".state" / "manual-key-check-workdir"),
                keys_file=str(ROOT / ".state" / "manual-key-check-workdir" / "keys.json"),
            )
        result["initializationSucceeded"] = True
        result["databaseFileCount"] = len(obj._db_files)
        result["verifiedKeyCount"] = sum(1 for rel, _, _ in obj._db_files
                                         if obj._key_works(rel))
        result["remainingEncryptedCount"] = len(obj._db_files) - result["verifiedKeyCount"]
    except BaseException as exc:
        result["errorClass"] = type(exc).__name__
    finally:
        db_type._save_keys = original_save
        db_type.extract_keys = original_extract
        db_type.extract_master_key = original_master
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-live", action="store_true",
                        help="Explicitly run upstream key extraction against locally running WeChat")
    args = parser.parse_args(argv)
    if not args.check_live:
        print("No action. User must explicitly pass --check-live in local PowerShell.")
        return 2
    result = diagnose()
    # The only persisted data is this fixed-schema, aggregate status.
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["initializationSucceeded"] and result["verifiedKeyCount"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
