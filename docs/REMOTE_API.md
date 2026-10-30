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
- Authenticated `GET /identity`: `state=online|offline` only,
  `accountId`, `process`, `windowState` and `loginVerified:false`. Uses
  read-only WeChat window geometry to distinguish visible large main windows
  from compact QR login dialogs in addition to the local account vault.
  Missing/ambiguous main windows report `offline`, never a third status.
  Unreachable APIs remain separate communication errors, not login statuses.
  A single confirmed `online` account can route when the peer is unreachable;
  two reachable nodes both reporting that account `online` cause a conflict.
  This remains a local heuristic, **not proof** of server-side login state.
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
### Headless self-healing API

The internal `wxbridge.supervisor` process keeps one API child alive per
machine. Every five seconds it checks authenticated local `GET /status`
against its Tailscale address without a proxy. A dead process or sustained
health-check failure is restarted after a startup grace period. The
supervisor never terminates a server process it did not start.

Run the one-time per-machine task installer with Windows task registration
permissions:

```powershell
# On 6v
& "C:\Users\Songjx\Documents\ChatGPT\WXBridge\tools\install_api_task.ps1" -Node 6v -Bind 100.76.74.124
# On noha
& "C:\Users\noha\Documents\AAAVitalFile\WXBridge\tools\install_api_task.ps1" -Node noha -Bind 100.96.30.32
```

This updates only the current user's `WXBridge-API` scheduled task. It
launches `pythonw.exe` with `tools/api_supervisor.py` at interactive logon,
and starts it immediately. The task has no execution-time limit or battery
restrictions; Task Scheduler can retry a failed supervisor (ten attempts,
one minute apart). The supervisor itself retries unhealthy API children
indefinitely. No user-facing EXE is installed on noha.

Only local `.state/api-token.txt` is read; no credentials are passed on
the command line or written to the log. Bounded rotating diagnostics go to
ignored `.state/api-supervisor.log`, and a process lock is held at
`.state/api-supervisor.lock`.

Windows API startup requests exclusive port ownership. Switching task
actions requires stopping the old task first; if another process holds
the port, the supervisor waits instead of killing that process.

**Power boundary:** A supervisor cannot wake a sleeping computer. Screen
blanking while the PC stays awake is supported; deep sleep/Modern Standby
can suspend ordinary processes and network access.
