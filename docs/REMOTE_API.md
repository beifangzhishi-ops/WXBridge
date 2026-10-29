# Tailscale HTTP API: symmetric 6v and noha nodes

The HTTP endpoint is a lightweight, read-only adapter. It is **not** supplied
by upstream `wechatauto-replica` and does not enable account login, extract
database keys, or inspect WeChat windows. It cannot prove login status yet.
The API's `wechatLogin: "unknown"` field is deliberate.

**Both PCs run the same Python HTTP service**, each serving only its own local
WeChat database. 6v additionally has the sole user-facing EXE; noha needs
no EXE. On noha, install Python 3.12, `cryptography` and `zstandard`; on
6v the existing isolated Python 3.9 database-only runtime is reused.
Each requires the exact pinned upstream checkout and a separately provisioned
local Windows-user DPAPI vault. **Never transfer one PC's WeChat keys to the
other.**

Provision a distinct randomly generated API token on **each** computer, as
`.state/api-token.txt` (Git-ignored). Keep files readable only by their owner
and administrators; never print, log, or commit their contents. Run from the
matching WXBridge checkout; both use port 18763 on their distinct Tailscale IPs:

For zero-argument client configuration, create a Git-ignored `.state/nodes.json`
on the PC running the CLI:

```json
{"6v":"http://100.76.74.124:18763","noha":"http://100.96.30.32:18763"}
```

Then place the two API credentials in local `.state/peers/6v.token` and
`.state/peers/noha.token`, respectively; they contain the matching node's
`.state/api-token.txt` value. These are **API access credentials only**,
not database keys. They are never stored in Git and must only be transferred
using a trusted, authenticated private channel. Environment variables
`WXBRIDGE_6V_URL`, `WXBRIDGE_6V_TOKEN`,
`WXBRIDGE_NOHA_URL`, `WXBRIDGE_NOHA_TOKEN` override private files.

```powershell
# 6v (Windows home PC)
& ".\tools\run_api.ps1" -Node 6v -Bind 100.76.74.124
# noha (Windows work PC; run on noha, not in the same terminal as 6v)
& ".\tools\run_api.ps1" -Node noha -Bind 100.96.30.32
```

The server binds **only** to the specified Tailscale IPv4 address. The
`X-WXBridge-Token` header is required even for `GET /status`. HTTP
content is carried over the encrypted Tailscale tunnel, not public internet.
No Windows firewall or scheduled-service startup configuration is bundled.

On **6v** with the matching API protocol and built EXE, point at the desired
node. Client tokens must match the corresponding server's private API token;
do not confuse API access tokens with WeChat DPAPI database encryption keys.

```powershell
$env:WXBRIDGE_NOHA_URL = "http://100.96.30.32:18763"
$env:WXBRIDGE_NOHA_TOKEN = "<noha's separate API secret>"
$env:WXBRIDGE_6V_URL = "http://100.76.74.124:18763"
$env:WXBRIDGE_6V_TOKEN = "<6v's separate API secret>"
& "C:\path\to\WXBridge\WXBridge.exe" --node noha sessions --limit 2
& "C:\path\to\WXBridge\WXBridge.exe" --node 6v sessions --limit 2
```

`--node noha` or `--node 6v` forwards one read-only command to that
named node, with the same API protocol and permission boundaries. It
does not silently fall back to the other database. Default remains
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
rebuild the 6v EXE and restart/retest **both** Python API services. A matching
Git SHA alone is not proof of updated runtime components. The launch script
is an interactive foreground server; a persistent Windows scheduled task
is a separate deployment step, not silently installed by this repository.
