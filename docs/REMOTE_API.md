# WXBridge two-machine read-only API

Both 6v (`DESKTOP-KFL6V1F`) and noha run the same Python HTTP API. Each API
reads its own local WeChat databases only. There is **no EXE on noha**.

The API requires a distinct private token per machine at `.state/api-token.txt`
and binds to its Tailscale IP, not public interfaces. On each host:

```powershell
# 6v
& ".\tools\run_api.ps1" -Node 6v -Bind 100.76.74.124
# noha
& ".\tools\run_api.ps1" -Node noha -Bind 100.96.30.32
```

Only 6v needs client routing settings (Git-ignored):

`.state/nodes.json`:

```json
{"6v":"http://100.76.74.124:18763","noha":"http://100.96.30.32:18763"}
```

`.state/peers/6v.token` and `.state/peers/noha.token` contain each API's
corresponding token. Keep them private; never transfer DPAPI key vaults,
plaintext databases or private chat data across machines.

## Endpoints

- Authenticated `GET /status`: compatibility status; no claim about login.
- Authenticated `GET /identity`: `state=offline|candidate|unknown`,
  `accountId`, `process`, and `loginVerified:false`. This is a best-effort
  process-plus-local-vault signal, not proof of current login.
- Authenticated `POST /query`: JSON `{"args":["sessions","--limit","20"]}`;
  only allowlisted, bounded read commands are accepted and locally executed.

Clients must supply `X-WXBridge-Token`; `POST /query` also requires
`X-WXBridge-Protocol: 1`. The public EXE uses the private peer credentials
to call `/identity` on both nodes and `/query` on the single chosen node.
Even for 6v, the EXE uses HTTP, never direct database access.

The API spawns `python -m wxbridge.local_ops` for each authorized query.
`local_ops` is an internal API worker, **not a second public CLI**. The
original pinned upstream's CLI is unchanged and not executed by this API.

The EXE always adds its own `environment_id` based on which configured API
it called. A local path returned from `files --id` refers to that environment;
CCM can read it there without sending file bytes over the WXBridge API.

## Deployment

Version-sync both source checkouts, rebuild 6v EXE, and restart **both**
APIs after code updates. Git synchronization alone does not restart an API.
Both nodes need local Python dependencies and their own authorized DPAPI vault.
No persistent Windows service/scheduled-task installation is bundled.
