"""The sensitive preview runner is only tested for safe inactive behavior."""

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "manual_preview_chats.py"


class ManualPreviewGuardTests(unittest.TestCase):
    def test_no_flag_does_not_access_real_data(self):
        proc = subprocess.run([sys.executable, str(RUNNER)],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("No action", proc.stdout)

    def test_help_is_safe(self):
        proc = subprocess.run([sys.executable, str(RUNNER), "--help"],
                              capture_output=True, text=True, timeout=5)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("--read-live", proc.stdout)


if __name__ == "__main__":
    unittest.main()
