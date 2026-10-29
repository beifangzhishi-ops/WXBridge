# wechatauto-replica — read-only backend review

Review date: 2026-10-26

- Upstream: https://github.com/fanyuantaier/wechatauto-replica
- Reviewed tree: `6e603974bbac3bda93d88bd6995510ae2547f5c`
- License: Apache-2.0
- Source reviewed: `wechatauto/db.py` and `wechatauto/__init__.py`, plus upstream `pyproject.toml` and README.
- The audited source was subsequently cloned at the same exact commit under ignored `.vendor/replica-src` on 6v. It was not installed as a system package and its GUI/sending initializer was not loaded.

## Authorized one-time probe on 2026-10-26

- The owner explicitly approved local process-memory database-key access and a read-only test limited to the File Transfer Assistant conversation.
- A narrowly scoped probe used only the upstream DB module, isolated from its UI/sending package initializer. It disabled key-file persistence and redirected upstream output away from chat.
- Database reader initialization returned `RuntimeError`. No real message content was retrieved, reported, or saved by WXBridge.
- The first metadata diagnosis found seven generic `.db` files but no `db_storage` under that configuration folder; a subsequent configuration/registry candidate check found one actual account data-storage directory that upstream auto-detection missed.
- The probe temporary cache directory was removed and the probe execution script was not retained. Another attempt was blocked by the execution environment's security checks, and no bypass was attempted.
- **Outcome: inconclusive initialization failure; backend not connected.** No claim is made that all key-access mechanisms were verified, or that process-memory access never occurred during the failed initializer.

## Original upstream checkout and safe smoke test

The unmodified upstream project has been cloned at the pinned commit into
`.vendor/replica-src` (Git-ignored). The following command performs a
**synthetic cryptographic check against the original upstream `db.py`**,
without constructing `WeChatDB` or importing the upstream GUI modules:

```powershell
python tools/check_upstream_core.py
```

On the 6v host, the original database module loaded successfully under
Python 3.13, accepted a correctly authenticated synthetic page, and rejected
an incorrect synthetic key. This is an **offline core smoke test**, not proof
that any real WeChat database can be decrypted.

A separate Python 3.9 virtual environment was created at
`.vendor/replica-py39` to respect the upstream Python compatibility range.
Its packaging tools installed successfully. The original package's full
editable install stalled during the transitive PyAutoGUI/screenshot build
dependencies; it was not yet proven installed or functional. Do not claim
that the upstream CLI or real chat reading works until separately verified.

In addition, a clean **database-core-only** Python 3.9 environment was
successfully established at `.vendor/replica-db39`, independent of the
stalled full-install environment:

```powershell
# Local environment already provisioned on 6v
& .\.vendor\replica-db39\Scripts\python.exe tools\check_upstream_core.py
```

This environment has `cryptography==50.0.2` and
`zstandard==0.25.0` with their Python dependencies. The original, unchanged
upstream `db.py` imports and its synthetic page HMAC validation both pass
under Python 3.9; `auto_detect_db_dir()` reports a candidate root. Its
corresponding UI/sending dependencies are not installed there. This does
**not** indicate that a live account or message has been accessed.

If reproducing the environment, use a new isolated venv rather than the
stalled full-package venv; avoid concurrent installations into the same venv.

### Explicit manual live-key diagnostic (opt-in only)

`tools/manual_upstream_key_diagnostic.py` is a **separate user-run**
diagnostic. It must never be called with `--check-live` in CCM, unattended
automation, automated tests or CI. The operator can run it in a **local
interactive PowerShell** to evaluate the pinned original upstream key-loading
and database HMAC verification path. This is a sensitive operation: the
original code can inspect a running Weixin.exe process, even though this
wrapper does not display the extracted key bytes.

The script checks the exact upstream source revision and hash, suppresses
upstream raw stdout/stderr, prevents saving original key caches, and never
calls message or session queries. It records only fixed-field non-secret
booleans, numeric totals and Python exception class in ignored
`.state/manual-key-diagnostic-summary.json`. Do **not** redirect the
interactive command output to a general-purpose transcript or log.

```powershell
# Run manually on your own PC only, from any current directory:
& "C:\path\to\WXBridge\.vendor\replica-db39\Scripts\python.exe" "C:\path\to\WXBridge\tools\manual_upstream_key_diagnostic.py" --check-live
```

Without `--check-live`, the script is inert. No live run or real chat read
has been verified by automated tests. This diagnostic is not part of the
WXBridge runtime and never enables continuous monitoring.

### Explicit test: selected conversations only

`tools/manual_preview_chats.py` is a second opt-in, user-run command for
validating the read-only **data query** path, beyond key verification. It
queries only the most recent **20 session headers** and **5 messages in
`filehelper`** through the pinned original upstream and the WXBridge
`ReplicaReader` adapter. The user has expressly authorized showing these
two categories of data to CCM.

```powershell
& "C:\path\to\WXBridge\.vendor\replica-db39\Scripts\python.exe" "C:\path\to\WXBridge\tools\manual_preview_chats.py" --read-live
```

The terminal prints only counts and exception type names. The limited data
preview is saved at ignored `.state/manual-selected-preview.json` for
CCM to inspect. Upstream key saving is disabled, and temporary decrypted
database caches are deleted on process exit. Unlike the key-only
diagnostic, **this command does save selected plaintext chat content**;
it is intentionally restricted to the user's requested preview and should
not be copied into Git or shared publicly. The opt-in `--read-live`
command is not invoked through CCM or automated tests because a prior
tool-level safety check rejected process-memory extraction. Without
`--read-live`, the program performs no live reads.

**Later update:** The operator's actual local preview succeeded (26/26
verified keys, 20 sessions and 5 filehelper messages). The original preview
saved no keys. There is now a *separately opt-in* key-persistence mode for
owner-run local setup; only verified keys are sealed under Windows-user
DPAPI, and the normal `cached-key` CLI has no process-memory discovery
fallback. This `cached-key` path has been tested with fabricated
keys/databases and, later, with the owner's separately provisioned local key
vault using real read-only CCM session and message queries. See
`docs/CACHED_KEYS.md` for the current state and privacy boundary.

One diagnostic call to the unmodified upstream `auto_detect_db_dir()`
returned a candidate root in this environment, while a separate
metadata-only inspection also found one directory containing `db_storage`.
This means the live initializer failure must **not** be attributed solely to
path detection without a precise error trace.

If a long-running pip install is still active, cancel that specific process
before launching another installation in the same environment. Avoid using
any credentials, real messages, or process-memory key scans as a smoke test.

## Why it is not automatically enabled

In the reviewed version, `WeChatDB.__init__` invokes `_load_or_extract_keys` immediately. When the cache is incomplete, that method calls `extract_keys`, and may attempt additional process-memory key discovery. The upstream writes key material into `keys.json` and can produce local decrypted database caches in its work directory.

Thus even running `WeChatDB()` solely to test readiness is **not** a safe read-only diagnostic. WXBridge's `providers` command checks only installed distribution metadata; `preflight` checks only candidate file names. Neither imports the upstream package or reads actual chat content.

For a future live adapter, require explicit user consent for process-memory key access, an account-specific work directory with a documented secure storage/cleanup policy, an audited pinned upstream version, and a rollback/stop procedure. Check the platform terms and risk of account restrictions. Do not enable this through a background health monitor or by merely importing WXBridge.

## Adapted API contract

`src/wxbridge/replica.py` accepts an already-authorized `WeChatDB`-compatible instance and **does not create it**. It uses only:

- `get_sessions(limit)`, `get_nickname(username)` → normalized session JSON
- `get_messages(user, limit, offset)` → normalized message JSON

Important upstream field differences:

| Concept | wechatauto-replica field | WXBridge normalized field |
|---|---|---|
| Session ID | `username` | `id` |
| Last session time | `last_time` | `lastTimestamp` |
| Message time | `create_time` | `timestamp` |
| Sender | `sender_username`, `sender_id` | `sender`, `senderId` |
| Message type | `type` (may be text name) | `type` (unchanged) |
| Local ID | `shard` + `local_id` | `id` (compound; not global WeChat server ID) |

The upstream message query merges sharded databases. WXBridge does not synthesize missing sender names from another shard. Date/keyword filtering operates only on a capped window of 1000 recent messages; `completeHistory` remains false, and `hasMore` is null when a complete filtered result cannot be guaranteed.

## Future verification gate

1. Inspect a pinned dependency wheel and its transitive dependencies; verify that installing it doesn't enable GUI or sending behavior.
2. Explicitly agree to any process-memory key access and the local key/data cache policy.
3. Confirm compatibility with the exact WeChat version (6v had 4.1.15.56 at review time; upstream reports testing 4.1.15.53).
4. Query only an explicitly named test conversation; confirm sender, timestamps, ordering, and incomplete-history labeling against locally observed messages.
5. Publish nothing externally until a reliable, auditable read-only path is established.
