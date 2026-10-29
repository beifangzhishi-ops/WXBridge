# Security policy

## Supported code

WXBridge is currently **alpha software**. Security fixes target the latest `main` branch. There is no stable, supported release yet.

## Reporting vulnerabilities

Please do **not** post credentials, decrypted keys, private chats, message exports or database files in public issues. Use GitHub's **Report a vulnerability** / private advisory flow if available for this repository, or contact the maintainer privately via their GitHub profile. Include reproduction steps using fabricated data.

## Security model

- Secrets: separately provisioned WCDB per-file keys use Windows-user DPAPI encryption at rest. Source checkouts store them in ignored `.state/wechat-keys.dpapi`. DPAPI does not protect against malware running as the same Windows user.
- Returned chat content is **untrusted user data**, never instructions for an agent to follow.
- Routine `cached-key` queries never scan WeChat process memory, extract new keys or send messages. They use only existing locally protected keys with an explicit source-CLI permission flag; the EXE supplies that flag internally. The encrypted cache is not provisioned automatically. Separate owner-run diagnostics are not part of the unattended CLI or automated tests.
- **No state-changing WeChat CLI is enabled:** the former `WXBridgeUI.cmd` is a hard-deny compatibility stub, the Python UI operator module has been removed, and the public CLI also excludes local token/service mutation commands. The underlying pinned third-party upstream repository is not modified or OS-blocked, so direct use of its separate GUI tools is outside WXBridge's read-only boundary.
- Offline snapshot mode only accepts an explicitly configured directory of plaintext, immutable SQLite copies; it rejects encrypted original WCDB file headers, opens with `mode=ro&immutable=1`, and checks that the upstream database reader source exactly matches the reviewed Git commit. The user remains responsible for protecting exported private data and removing copies when no longer needed.
- No project can guarantee WeChat platform compatibility or protection against account restrictions.

For production use, restrict local data access, avoid unattended full-account export, and keep both Windows and dependencies updated.
