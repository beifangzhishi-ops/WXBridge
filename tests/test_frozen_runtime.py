"""EXE resource-path and pinned-source logic tested with synthetic files."""
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wxbridge import runtime
from wxbridge.paths import state_directory


class FrozenPathsTests(unittest.TestCase):
    def test_source_mode_uses_checkout(self):
        self.assertEqual(runtime.app_root(),
                         Path(__file__).resolve().parents[1])

    def test_frozen_exe_root_and_bundled_source(self):
        local = Path("C:/fictional-wxbridge-exe-test-root")
        source = local / "upstream" / "wechatauto" / "db.py"
        synthetic = b"# fictional source"
        digest = hashlib.sha256(synthetic).hexdigest()
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "_MEIPASS", str(local), create=True):
                with patch.object(sys, "executable", str(local / "WXBridge.exe")):
                    self.assertEqual(runtime.app_root(), local)
                    self.assertEqual(runtime.embedded_root(), local / "upstream")
                    with patch.dict(runtime.SOURCE_HASHES, {"db.py": digest}):
                        with patch.object(Path, "read_bytes", return_value=synthetic):
                            self.assertTrue(runtime.embedded_source_is_verified(source))
                        with patch.object(Path, "read_bytes", return_value=b"tampered"):
                            self.assertFalse(runtime.embedded_source_is_verified(source))
                    self.assertFalse(runtime.embedded_source_is_verified(
                        local / "other" / "db.py"))

    def test_frozen_exe_checkout_uses_existing_state_path(self):
        root = Path("C:/fictional-wxbridge-checkout-root")
        with patch.dict(os.environ, {"WXBRIDGE_STATE_DIR": ""}):
            with patch.object(sys, "frozen", True, create=True):
                with patch.object(sys, "executable", str(root / "WXBridge.exe")):
                    with patch.object(Path, "is_file", return_value=True):
                        self.assertEqual(state_directory(), root / ".state")


if __name__ == "__main__":
    unittest.main()
