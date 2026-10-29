# WXBridge read-only upstream capability boundary

The pinned original `wechatauto-replica` source checkout remains unchanged.
WXBridge wraps only read-oriented methods from hash-verified source. The
underlying upstream package contains both read and write operations, but
**WXBridge deliberately does not expose those upstream write operations**.

| Original upstream | WXBridge `cached-key` CLI | Limits |
| --- | --- | --- |
| `WeChatDB.get_sessions/get_messages` | `sessions/messages/search` | Real message read via CCM verified |
| `search_contact` | `contacts --keyword` | Bounded search |
| `get_groups/get_group_members` | `groups/group-members` | Group listing excludes detailed members |
| `list_labels` | `labels` | Reads local labels, does not edit them |
| `list_message_chats` | `message-chats` | Message-bearing chat enumeration |
| `get_new_messages` | `new-messages --chat --since-seq` | One-shot query, no listener |
| `get_self_info` | `self` | Local account metadata |
| `MediaDownloader.image_status/voice_status` | `media-status` | Availability, no GUI |
| `WeChatDB.get_message_row` and local `msg/file` | `media-read --chat --message-id` | WXBridge-only file attachment locator; returns verified existing path without copying or downloading |
| `MomentDB.get_moments/get_moment` | `moments/moment` | Local SNS database |
| `MomentDB.get_interactions` | `moment-interactions` | Local interaction notifications; no like/comment actions |
| Local appmsg XML | `articles --chat` | Web/article share metadata only; excludes file attachments and quoted messages, no external page crawling |

File-attachment lookup requires an exact shard-qualified message ID. It checks
the original account-local file tree and validates WeChat-renamed filenames
against message XML's size/MD5 when present. A missing attachment or checksum
mismatch does not yield a path. The caller can directly read an available file;
WXBridge does not write a copy. Some images need a separate image key, so the
image/voice status command does not guarantee decoded media content.

## Disabled state-changing functions

Sending messages, forwarding, changing remarks, editing labels, adding
contacts, changing Moments likes/comments/replies, foreground UI listeners
and UI-driven downloads are **not available** through WXBridge.

- `src/wxbridge/operator.py` was removed.
- `WXBridgeUI.cmd` remains as a compatibility **hard-deny stub**: every
  argument combination, including `--allow-state-change`, returns
  `wxbridge_ui_disabled` (exit status 4) without launching Python or WeChat.
- The public CLI has no credential-changing or background service commands.
- The original upstream repository and any separately installed upstream
  Python environment are **not** a hardened sandbox or blocked at OS level.
  Calling `python -m wechatauto` directly bypasses WXBridge and is outside
  the project's read-only contract. CCM/Codex should never use it for GUI
  operations.

This restriction is intentional even when a CCM command is granted
`require_escalated` permissions. Testing showed that normal CCM execution
does **not** automatically trigger approval on a WeChat write command:
filesystem sandbox restrictions are not the same as application-level
authorization. Do not present approval as a sufficient substitute for
disabling the command.

## Cross-workspace use

Other registered CCM/Codex workspaces should call
`C:\path\to\WXBridge\WXBridge.exe` while retaining
their own workspace handle. A projectless CCM handle on 6v also works. The
DPAPI key vault is read-only for normal queries. Temporary decrypted SQLite
copies are prepared under the invoking working directory, then removed on
normal exit. Existing Windows ACL restrictions may still prevent a particular
workspace from reading databases or creating temporary directories. A
different-directory `sessions --limit 1` query succeeded with exit code 0.
CCM connection errors are not evidence of WXBridge read permission denial or
a requirement to enter the WXBridge development workspace.
