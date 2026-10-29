"""PyInstaller entrypoint. WXBridge command exposure is read-only."""
import sys
from wxbridge.cli import main

if __name__ == "__main__":
    # One direct, read-only entrypoint for other CCM/Codex workspaces.
    raise SystemExit(main(["--backend", "cached-key", "--allow-local-db",
                           *sys.argv[1:]]))
