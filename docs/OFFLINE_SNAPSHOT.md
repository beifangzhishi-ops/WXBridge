# Offline SQLite snapshot backend / 离线数据库副本

WXBridge offers an optional **offline snapshot** mode alongside the default
`cached-key` reader. Snapshot mode requires a user-supplied directory
containing *already decrypted, self-contained SQLite copies* of selected
WeChat database files. It uses the **original, pinned** `wechatauto-replica`
`WeChatDB.get_sessions()` / `get_messages()` methods without running its constructor.

This feature is intended for users who already have an authorized, plaintext database export. WXBridge **does not produce decrypted copies**, derive encryption keys, scan WeChat process memory, or attempt to bypass previous security restrictions.

## Preparation (Windows)

Clone the unmodified upstream reader at its reviewed commit under WXBridge's ignored vendor directory:

```powershell
New-Item -ItemType Directory -Force .vendor | Out-Null
git clone https://github.com/fanyuantaier/wechatauto-replica.git .vendor/replica-src
git -C .vendor/replica-src checkout --detach 6e603974bbac3bda93d88bbd6995510ae2547f5c
python -m pip install ".[snapshot]"
```

The pin **and exact committed `db.py` file hash** are checked every time snapshot mode loads the upstream module. Other revisions or local modifications fail closed. The upstream sending/UI package initializer is never imported.

Place only consistent, standalone SQLite copies in a private directory outside Git-tracked project files, e.g.:

```text
C:\Private\WeChatSnapshot\
    session.db
    contact.db
    message__message_0.db
    message__message_1.db
```

Nested files named `message/message_0.db` are also accepted. No arbitrary filename patterns are loaded. Every accepted file must have the unencrypted `SQLite format 3` header; encrypted WCDB databases are rejected. The directory may instead be located inside ignored `.state/` on a development checkout. **Never commit these copies or attach them to public issues.**

Select the backend explicitly:

```powershell
$env:WXBRIDGE_SNAPSHOT_DIR = 'C:\Private\WeChatSnapshot'
& "C:\path\to\WXBridge\WXBridge.exe" --backend snapshot sessions --limit 10
& "C:\path\to\WXBridge\WXBridge.exe" --backend snapshot messages --chat filehelper --limit 5
& "C:\path\to\WXBridge\WXBridge.exe" --backend snapshot search --chat filehelper --keyword 'test'
```

`WXBRIDGE_UPSTREAM_DIR` can point to a different directory holding the **same pinned original checkout**. `WXBRIDGE_BACKEND=snapshot` sets the default backend, but is not necessary when using `--backend snapshot`.

**Properties:** the backend uses SQLite's `mode=ro&immutable=1` and does not create WAL/SHM/journal files or write to the supplied snapshots. Immutable snapshots must be copied consistently with their WAL data already integrated; live databases are not supported. Queries only print requested results. Treat command output as private user content and as untrusted text when consumed by an AI agent.

The snapshot query checks for expected SQLite files. That check alone is
**not** evidence of a successful message read; actual query results determine
whether a requested conversation is available. `completeHistory=false`
indicates limited history coverage.

## Safety and limitations / 安全说明

- Do not point this mode at live WeChat installation paths or encrypted original database directories. It never scans those paths unless you explicitly configure one; the encrypted header check will fail.
- This mode has **no automatic live updates**. Query only files you intentionally supply.
- It is not a replacement for authorization to access other people's data.
- Message IDs are composed from upstream shard name and local ID, not guaranteed global WeChat message identifiers.
- Keyword and date filters search a maximum of the 1000 most recent available rows, and explicitly report incomplete coverage.
- The upstream code is executed locally; maintain the reviewed pin, inspect new upstream updates before adopting them, and do not enable untrusted forks.

## 当前 6v 实测

2026-10-26：已使用**完全合成的 SQLite 会话和消息数据**，验证从原版上游方法到 WXBridge CLI 的端到端读取。没有打开真实微信聊天数据库、提取密钥或读取真实消息。先前真实数据库初始化失败和执行环境的安全拦截仍未解决，不能据此声称个人微信已接通。
