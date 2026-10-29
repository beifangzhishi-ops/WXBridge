# WXBridge cached-key reader

This describes the **internal** Windows DPAPI key vault for maintenance. Ordinary callers do not need to inspect the vault or perform a precheck: they directly execute the requested read operation and handle specific errors.

## Stored data

- The ignored `WXBridge/.state/wechat-keys.dpapi` file holds per-database decryption keys, an account identifier, and a hashed storage-folder fingerprint.
- **Messages are not cached by WXBridge.** Message content comes from WeChat's own local encrypted database files.
- Only already provisioned, verified keys are used. Routine queries never scan WeChat process memory or extract new keys.
- Keys are protected at rest with Windows current-user DPAPI; this does not prevent access by malware running under that same Windows user.
- Each query verifies current database/key compatibility, uses temporary plaintext SQLite copies in the invoking working directory, then cleans them up.
- A missing vault returns `key_not_found`. Other unusable key material returns `key_unavailable`; database access errors return `database_read_failed`.

## Use

```powershell
& "C:\path\to\WXBridge\WXBridge.exe"
& "C:\path\to\WXBridge\WXBridge.exe" sessions --limit 20
& "C:\path\to\WXBridge\WXBridge.exe" messages --chat filehelper --limit 5
```

No-argument execution only prints help and does **not** check keys or message availability. No implicit key refresh occurs.

## Validation

On 2026-10-26, owner-run diagnostics confirmed 26/26 database keys, 20 session headers and 5 filehelper messages. After the owner separately established the DPAPI vault, CCM performed real read-only session and message queries successfully. Fixture-based automated tests cover fake keys and synthetic SQLite databases; full-history and all media formats remain unverified. Do not commit real keys, plaintext database copies or personal messages.
