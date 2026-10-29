"""Diagnose WeChat database *paths* without opening message files or process memory.

This is for local troubleshooting only; stdout contains no account/path names.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import winreg
import json


def main(*, return_db_root=False):
    candidates = set()
    config_names = set()
    for env in ("APPDATA", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if not base:
            continue
        for rel in ("Tencent/xwechat", "Tencent/xwechat/config", "Tencent/WeChat"):
            parent = Path(base) / rel
            if parent.is_dir():
                config_names.add(str(parent))
                for file in parent.iterdir():
                    if file.is_file() and file.stat().st_size <= 100_000:
                        raw = file.read_bytes()
                        for enc in ("utf-8", "utf-16-le", "gbk"):
                            content = raw.decode(enc, "ignore")
                            for path in re.findall(r'[A-Za-z]:[\\/][^\r\n\x00"<>|]{4,230}', content):
                                candidates.add(path.strip().strip("\x00").strip())
    registry_path_fields = 0
    for sub in ("Software\\Tencent\\xwechat", "Software\\Tencent\\xwechat\\config",
                "Software\\Tencent\\WeChat"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub)
        except OSError:
            continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                name, value, _ = winreg.EnumValue(key, i)
                if isinstance(value, str) and any(s in name.lower() for s in ("path", "dir", "save")):
                    registry_path_fields += 1
                    candidates.add(value.strip())
    document = Path.home() / "Documents"
    roots = [document, Path.home(), Path.home() / "AppData" / "Roaming" / "Tencent"]
    roots.extend(Path(path) for path in candidates)
    valid = 0
    accounts = 0
    seen = set()
    db_roots = []
    for root in roots:
        for possible in (root, root / "xwechat_files", root / "WeChat Files",
                         root / "xwechat_files_data"):
            if possible in seen:
                continue
            seen.add(possible)
            if not possible.is_dir():
                continue
            valid += 1
            try:
                count = sum(
                    (d / "db_storage").is_dir()
                    for d in possible.iterdir() if d.is_dir())
                accounts += count
                if count:
                    db_roots.append(possible)
            except OSError:
                continue
    if return_db_root:
        return db_roots[0] if len(db_roots) == 1 else None
    print(json.dumps({
        "configurationDirectoriesInspected": len(config_names),
        "candidatePathStrings": len(candidates),
        "registryPathFields": registry_path_fields,
        "existingCandidateRoots": valid,
        "accountDbStorageDirectoriesFound": accounts,
    }))


if __name__ == "__main__":
    main()
