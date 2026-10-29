"""Only test the inert behavior of the opt-in diagnostic, never live access."""

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "tools" / "manual_upstream_key_diagnostic.py"


class ManualDiagnosticGuardTests(unittest.TestCase):
    def test_without_explicit_flag_does_not_scan_memory(self):
        result = subprocess.run([sys.executable, str(DIAG)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertIn("No action", result.stdout)

    def test_help_does_not_scan_memory(self):
        result = subprocess.run([sys.executable, str(DIAG), "--help"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertIn("--check-live", result.stdout)


if __name__ == "__main__":
    unittest.main()
