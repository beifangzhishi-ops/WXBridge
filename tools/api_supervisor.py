"""Console-free scheduled-task entry for the WXBridge internal API supervisor."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wxbridge.supervisor import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
