# WXBridge — current implementation and maintenance plan

Updated: 2026-10-29. This document records the present implementation, not superseded development experiments; Git history retains previous research notes.

## Architecture and safety

- Standalone Windows, local-first, strictly read-only WeChat CLI for use by CCM/Codex in their current workspaces; no separate MCP service is required.
- Main executable: `WXBridge.exe` with adjacent `_wxbridge_runtime/` directory. The EXE uses the local Windows-user DPAPI key cache and pinned upstream `wechatauto-replica` read-only database/media/Moments implementations. These pinned upstream files are not edited.
- One-shot cached queries use temporary decrypted SQLite copies in the invoking working directory and clean them up afterwards. The normal query path does not scan WeChat process memory or discover new keys.
- No sending, forwarding, contact edits, Moments actions, GUI automation, network attachment fetching or WeChat state mutations. Local chat contents, keys and personal paths must not enter source control.

## Working features

- `status`, `providers`, `preflight`; `sessions`, `messages`, `search`; `contacts`, `groups`, `group-members`, `labels`, `message-chats`, `new-messages`, `message-storage`, `self`.
- `moments`, `moment`, `moment-interactions`; `media-status` for image and voice availability; `articles` for web/article share XML metadata (not files or quoted-message cards).
- Both `message_N.db` and `biz_message_N.db` message shards are covered for WeChat 4.x.
- `media-read --chat <id> --message-id <shard:local_id>`: locates one already-downloaded file attachment within that account's `msg/file` directory and returns the existing absolute path. Supports WeChat collision suffixes such as `(1)` only with an accompanying MD5, checks available file size and MD5, reports missing/mismatched files without a path, and does not copy or download content.
- For direct file analysis, CCM/Codex consumes the original path with its existing file/PDF tooling. WXBridge does not parse PDF body content.

## Verification

- 2026-10-26: owner verified a one-shot database/key read; subsequent CCM cached-key tests read real conversation and filehelper message records.
- 2026-10-27: synthetic EXE integration tests verified the business-message shard adapter; the pinned source is hash-verified during build.
- 2026-10-29: inspected a user-selected type-6 PDF message and the downloaded local file; their 806,014-byte sizes and MD5 digests match. The new Python CLI `media-read` returned the actual collision-renamed `(...1).pdf` path without copying it. This also confirmed that WeChat 4.x uses a compound integer `local_type` and that raw message BLOBs need the pinned reader's decoding step.
- All automated unit tests use synthetic inputs. See `tests/` and `docs/EXE_BUILD.md` for EXE tests and build procedures.

## Known limitations and next work

- Cached `status` currently checks only cache configuration and conservatively reports `readingAvailable=false`; a separately scoped actual-read verification mode remains future work.
- Cached one-shot queries can be slow because each invocation validates DB keys and prepares transient database copies. Profile before adding optimizations; do not persist plaintext indexes or database copies by default.
- `media-read` supports already-downloaded file attachments (WeChat `appmsg type=6`) only. Image/voice status is a separate command. Files absent from the account's local `msg/file` tree cannot be obtained without other means, which WXBridge does not provide.
- Reader results are bounded and must never imply complete history. Unofficial integrations may break when WeChat changes its schema or storage layout.

## Maintenance/release gates

Read `AGENTS.md` before changes. Keep `README.md`, the Chinese documentation, this plan, tests, and packaged EXE consistent with the real implementation. Use fabricated test fixtures for CI; real-chat smoke checks require explicit user-selected targets. Commit completed changes, and push only if a configured remote exists. Do not publish a public repository or a release without owner approval.
