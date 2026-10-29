# Windows WXBridge.exe build

**The verified deployment on 6v consists of two adjacent items:**
`WXBridge.exe` and `_wxbridge_runtime/`. The EXE is the sole program
entrypoint; the runtime folder contains its Python DLLs and pinned source
resources. Both are ignored by Git, with no keys or actual chat data included.

The EXE is built using the isolated database-only Python 3.9 environment,
not the separate UI-automation Python runtime. It embeds the original pinned
`db.py`, `media.py` and `moment.py` as source resources. At runtime,
each resource is verified against a reviewed SHA-256 digest before being
loaded; the original GUI `wechatauto` package is never imported.
The main CLI does not register send, forward, remarks, or other state-changing
WeChat commands.

## Rebuild on 6v

From the WXBridge checkout with the pinned `.vendor/replica-src` and
`.vendor/replica-db39` environments already provisioned:

```powershell
& ".\.vendor\replica-db39\Scripts\python.exe" -m pip install "pyinstaller==6.16.0"
& ".\tools\build_exe.ps1"
```

The build script verifies the pinned Git commit and all three source hashes
before packaging, writes staging files under ignored `build/`, and copies
the completed EXE plus runtime folder into the checkout root.

The PyInstaller **one-file** configuration was tested and rejected for CCM:
its bootloader could not write the extracted DLLs in the restricted sandbox
(`Failed to extract VCRUNTIME140.dll`). The working **one-directory**
configuration loads its bundled native DLLs in-place. A lone EXE copied
without `_wxbridge_runtime` will fail to launch.

On 6v, the EXE was validated as a console program (zero-argument help,
`--version`, read-only command allowlist, and
startup from a different working directory). A missing synthetic vault
produced a controlled error rather than accessing real private keys.
An end-to-end test also read two fabricated messages from synthetic
offline SQLite files via the bundled upstream code. The latest automated
suite passes 65 tests (one conditional skip). Real account content was not
read during packaging; a separate read-only `sessions --limit 1` check
confirmed that the deployed EXE can read the current local database.

## Usage

### Read a local file attachment directly

`media-read` looks up an already-downloaded type-6 file using the exact
shard-qualified ID returned by `messages`. It returns the original Windows
path, with available size and MD5 checks; it does not copy or download media.
WeChat may append `(1)` to a saved filename, so matching uses the message's
file metadata rather than requiring an identical basename.
On 2026-10-29 the installed EXE successfully returned the original path of
one user-selected, renamed PDF with matching 806,014-byte size and MD5.

```powershell
& "C:\path\to\WXBridge\WXBridge.exe" media-read --chat "example_wxid" --message-id "message__message_3.db:602"
```

The caller can read the returned original PDF path directly. `articles`
returns web/article share metadata only, not file attachments or PDF content.

### Official/service-account message shards

WeChat 4.x stores some official-account/service-account notifications in
`message/biz_message_N.db` instead of the ordinary `message_N.db`
shards. The original pinned upstream's `_message_dbs()` skipped those
shards. WXBridge now overrides the one-shot cached-only shard inventory
to include both families, keeping the pinned upstream checkout untouched
and never attempting new key extraction. Offline snapshot mode supports
the same extra shard family.

```powershell
& "C:\path\to\WXBridge\WXBridge.exe" message-storage --chat "gh_example"
& "C:\path\to\WXBridge\WXBridge.exe" messages --chat "gh_example" --limit 5
```

The first command reports **only** hashed conversation-table counts and
schema compatibility (no body access). The second explicitly requests
private message content and should only be used with the owner's consent
and in compliance with the execution environment's safety checks. All
automated end-to-end content tests use invented SQLite records.

The subsequent service-account shard update passed 60 automated tests,
including a real EXE reading an entirely fictional `biz_message_0.db`
SQLite fixture. Structural live DB checks confirmed business-message
tables and compatible columns for two user-specified service accounts,
without retrieving any of their message-body values.

```powershell
& "C:\path\to\WXBridge\WXBridge.exe"
& "C:\path\to\WXBridge\WXBridge.exe" sessions --limit 20
```

With no arguments the program prints help and exits 0. All EXE commands
default to `--backend cached-key --allow-local-db`; the DPAPI key vault is
looked up under the checkout's ignored `.state/` when the EXE lives in the
checkout. Running with no arguments only displays help. Read queries
may create temporary decrypted SQLite copies in the invoking workspace's
current directory and remove them afterward. Full live database compatibility
must be separately verified for each operation.
