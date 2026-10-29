"""PyInstaller entrypoint. WXBridge command exposure is read-only."""
from wxbridge.frontend import main

if __name__ == "__main__":
    # Only the public EXE routes between APIs. Each API keeps its own
    # local Python CLI and never calls this routing frontend.
    raise SystemExit(main())
