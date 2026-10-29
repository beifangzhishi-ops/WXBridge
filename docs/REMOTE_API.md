# Tailscale HTTP API: noha Python worker and 6v CLI client

The HTTP endpoint is a lightweight, read-only adapter. It is **not** supplied
by upstream `wechatauto-replica` and does not enable account login, extract
database keys, or inspect WeChat windows. It cannot prove login status yet.
The API's `wechatLogin: "unknown"` field is deliberate.

The service does not have an EXE. On **noha**, install Python 3.12,
`cryptography`, and `zstandard`; provision the exact audited upstream
source tree under the ignored `.vendor/replica-src` as described in
`REPLICA_SOURCE.md`. Local reads additionally require a **noha-specific**
DPAPI key vault, separately provisioned on noha. Never copy 6v's vault.

Example noha PowerShell session (use a unique secret and keep it outside Git):

```powershell
$env:PYTHONPATH = "C:\path\to\WXBridge\src"
$env:WXBRIDGE_NOHA_TOKEN = "<unique, random 32+ character secret>"
& "C:\path\to\WXBridge\.venv\Scripts\python.exe" -m wxbridge.api --bind 100.96.30.32 --port 18763
```

The server binds **only** to the specified Tailscale IPv4 address. The
`X-WXBridge-Token` header is required even for `GET /status`. HTTP
content is carried over the encrypted Tailscale tunnel, not public internet.
No Windows firewall or scheduled-service startup configuration is bundled.

On **6v** with the matching API protocol and built EXE:

```powershell
$env:WXBRIDGE_NOHA_URL = "http://100.96.30.32:18763"
$env:WXBRIDGE_NOHA_TOKEN = "<the same private secret>"
& "C:\path\to\WXBridge\WXBridge.exe" --node noha sessions --limit 2
```

`--node noha` forwards one read-only command to the remote server. It
does not silently use the 6v local cached database. Default remains
`--node local`. **Automatic login-based routing is not yet implemented**;
neither process existence nor cached DB readability proves an account is
logged in. Remote `media-read` currently identifies files on noha; its
returned Windows path is not a 6v-local path and must not be misrepresented
as directly openable on 6v. Binary attachment streaming still needs a
separate implementation and verification.

Endpoints:

- `GET /status`: API protocol and intentionally unknown login/readiness.
- `POST /query`: JSON `{"args":["sessions","--limit","2"]}`,
  authenticated with headers `X-WXBridge-Token` and
  `X-WXBridge-Protocol: 1`. Only the allowlisted read commands are accepted.

After changes, synchronize 6v and noha Git HEADs (see `AGENTS.md`),
rebuild the 6v EXE and separately restart the noha Python API. A matching
Git SHA alone is not proof of updated runtime components.
