# Windows installation and deployment

WXBridge is an alpha-stage, third-party Windows WeChat reader. The GitHub
repository is private at present, but the source is maintained as if public.

## 6v: CLI entrypoint

The Windows executable consists of **both** `WXBridge.exe` and its adjacent
`_wxbridge_runtime/` directory. These generated artifacts are intentionally
not tracked in Git. To build, use `tools/build_exe.ps1` after provisioning
the pinned upstream source and isolated build environment; see EXE_BUILD.md.

```powershell
& "C:\path\to\WXBridge\WXBridge.exe" --help
```

For actual reads, the CLI additionally requires locally available
WeChat database files and a separately provisioned Windows-user DPAPI key
cache. Keys are never distributed through GitHub.

## noha: Python source and API host (not a second EXE)

Clone the private repository with an authenticated GitHub account:

```powershell
gh repo clone OWNER/WXBridge "C:\path\to\WXBridge"
cd "C:\path\to\WXBridge"
uv venv .venv --python 3.12
$env:UV_CACHE_DIR = Join-Path (Get-Location) ".venv\uv-cache"
uv pip install --python .\.venv\Scripts\python.exe cryptography zstandard
$env:PYTHONPATH = Join-Path (Get-Location) "src"
.\.venv\Scripts\python.exe -m wxbridge --help
```

Replace OWNER with the GitHub username. The `uv` CLI must be installed.
This install intentionally avoids the optional UI/sending dependencies.
That is a **source CLI** smoke test,
not yet a test of chat reading or network API access. The upstream repository
at the exact PIN described in REPLICA_SOURCE.md must also be provisioned for
real DB reads. The Python HTTP API is implemented in `wxbridge.api`; see
`REMOTE_API.md` for token setup and Tailscale-only startup. It cannot read
noha's chats until the local upstream core and noha-specific key vault work.
The 6v EXE must be rebuilt to support `--node noha`.

## Privacy and publication

Do not commit local database files, decrypted SQL copies, DPAPI vault,
user-specific runtime state, API tokens, environment secrets or chat records.
Do not expose the HTTP API to the public internet.
