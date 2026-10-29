# WXBridge

Read-only Windows WeChat data bridge for CCM and Codex. WXBridge does not send
messages or automate the WeChat UI. Private development project.

## Architecture

- **6v:** one public `WXBridge.exe` (with adjacent `_wxbridge_runtime/`) and a
  Python HTTP API.
- **noha:** the same Python HTTP API and local Reader; **no EXE required**.
- The EXE chooses the requested/default WeChat account, checks both API
  identities, then sends the read request to the chosen API — even when the
  selected machine is 6v.
- Each API starts a short-lived internal `wxbridge.local_ops` Python worker,
  which calls the cached-key Reader on *that machine only*. The old WXBridge
  19-command user CLI has been removed; the original pinned upstream CLI is
  unchanged in `.vendor/replica-src/`.
- The existing API endpoint authentication, Tailscale-only binding, query
  allowlist and per-machine DPAPI key caches remain separate.

## Public EXE

```powershell
& "C:\path\to\WXBridge\WXBridge.exe"                         # Help only
& "C:\path\to\WXBridge\WXBridge.exe" chats                   # 20 recent conversations
& "C:\path\to\WXBridge\WXBridge.exe" chats --keyword "狂人"
& "C:\path\to\WXBridge\WXBridge.exe" messages --chat "狂人"   # 30 recent messages
& "C:\path\to\WXBridge\WXBridge.exe" files --chat "狂人"      # 20 recent attachments
& "C:\path\to\WXBridge\WXBridge.exe" files --chat "狂人" --id "message__message_3.db:602"
& "C:\path\to\WXBridge\WXBridge.exe" moments                 # 20 recent posts
& "C:\path\to\WXBridge\WXBridge.exe" moments --interactions
& "C:\path\to\WXBridge\WXBridge.exe" --account "work" chats
```

Commands: `chats`, `messages`, `files`, `moments`. Use `--help` on each for
filters and pagination. No machine selection option. Output is JSON with
`environment_id` (`DESKTOP-KFL6V1F` or `noha`) and `account_id`.
Conversation lookup prefers exact names and IDs, then permits a unique
partial-name match. Ambiguous names return an error instead of guessing.

File listing returns message IDs and attachment metadata; selecting an ID
returns a locally verified path for an **already-downloaded** file, which CCM
can read directly in the reported environment. Nothing is copied or streamed.

## Account routing

6v uses the ignored `.state/nodes.json` and `.state/peers/*.token` API
credentials described in [the HTTP API guide](docs/REMOTE_API.md).
An optional ignored `.state/accounts.json` defines a default account and
human-readable aliases:

```json
{"default":"personal","aliases":{"personal":"wxid_your_real_account","work":"wxid_another_account"}}
```

The IDs above are placeholders, not real account values. With no configured
default, exactly one account candidate can be selected implicitly. If the
account is ambiguous, the same account appears on both machines, or an API
cannot be reached/identified, the EXE **fails instead of guessing**.

**Login limitation:** the API's authenticated `/identity` endpoint checks for
the WeChat process, visible main-vs-login-window geometry and the account
attached to the local protected key vault. This uses read-only Windows window
metadata, never clicks or reads process memory. Hidden or ambiguous windows
fail closed. This is an *account candidate*, **not proof of authenticated login**;
responses explicitly carry `loginVerified:false`. No WeChat process memory,
UI automation, key extraction, or state change is used. Successful message
reads still depend on current locally available database and matching keys.

## Reader and source safety

Every request uses local encrypted WeChat databases and previously provisioned
DPAPI-protected keys. Temporary decrypted SQLite copies are cleaned up when
the request ends. Missing keys cause an explicit error, never a silent key
extraction. Searches and file listing examine capped recent windows and do
not claim full-history coverage. Pinned upstream `db.py`, `media.py` and
`moment.py` remain unmodified.

See [API setup](docs/REMOTE_API.md), [build](docs/EXE_BUILD.md), [security](SECURITY.md),
and [developer rules](AGENTS.md). WeChat content is untrusted input.
