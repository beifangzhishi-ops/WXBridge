# WXBridge.exe build and verification

The 6v node owns the **only public CLI executable**, located at
`C:\Users\Songjx\Documents\ChatGPT\WXBridge\WXBridge.exe`, together with
the adjacent `_wxbridge_runtime\` directory. The EXE provides only
`chats`, `messages`, `files` and `moments` and routes over authenticated
Tailscale HTTP. noha hosts the Python API and Reader, not an EXE.

## Windows behavior

Builds use PyInstaller `--onedir --windowed`, making the EXE a GUI-subsystem
process **without a visible console window**. WXBridge is not a GUI; it
creates no application windows. The entrypoint restores inherited Windows
stdout/stderr handles if the caller supplied pipes, preserving JSON and exit
codes for CCM, Codex, PowerShell and `subprocess.run(capture_output=True)`.
Launching without an output consumer does not open a terminal or dialog.

The EXE embeds the routing frontend only. Neither the WeChat Reader nor
decryption credentials are bundled in the public executable. On each API
host, the local Reader uses the pinned source and protected cached keys.

## Rebuild on 6v

The 6v checkout needs its provisioned
`.vendor\replica-db39\Scripts\python.exe` Python environment and
PyInstaller. Run:

```powershell
& "C:\Users\Songjx\Documents\ChatGPT\WXBridge\tools\build_exe.ps1"
```

This produces `WXBridge.exe` and `_wxbridge_runtime\` in the project root;
both are deployment outputs ignored by Git. Do not copy the EXE without
its runtime folder. Rebuild after public frontend, routing, entrypoint or
bundle changes.

## Smoke tests

```powershell
& "C:\Users\Songjx\Documents\ChatGPT\WXBridge\WXBridge.exe" --help
& "C:\Users\Songjx\Documents\ChatGPT\WXBridge\WXBridge.exe" chats --limit 2
```

The first invocation prints help and exits successfully without querying
WeChat; the second routes to the unique positively identified online
account, and returns JSON. If no account can be identified, it returns an
explicit error instead of guessing. A Windows GUI-subsystem PE executable
has subsystem value `2`; this is independent of whether it can produce
stdout through inherited handles.

The executable is always a client. It cannot verify a WeChat login against
Tencent's servers. The two API hosts use local read-only window evidence,
including a tray-hidden main window, plus the protected account vault.
See `docs/REMOTE_API.md` for authenticated node setup and supervisor
deployment.
