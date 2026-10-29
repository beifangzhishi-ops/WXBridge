"""The WXBridge product entrypoints must be read-only, not just omit help."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class ReadOnlyGateTests(unittest.TestCase):
    def _run(self, module, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run(
            [sys.executable, "-m", module, *args],
            capture_output=True, encoding="utf-8", env=env, timeout=10,
        )

    def test_mutation_subcommands_are_not_exposed_or_executable(self):
        helptext = self._run("wxbridge", "--help")
        self.assertEqual(helptext.returncode, 0)
        for action in (
            "send", "forward", "remark", "addfriend", "moment-like",
            "moment-comment", "moment-reply", "listen", "images",
            "token", "service",
        ):
            with self.subTest(action=action):
                self.assertNotIn("    " + action + " ", helptext.stdout)
                denied = self._run("wxbridge", action, "synthetic-nonrecipient")
                self.assertNotEqual(denied.returncode, 0)
                self.assertIn("invalid choice", denied.stderr)

    def test_old_python_gateway_is_uninstalled(self):
        self.assertIsNone(
            importlib.util.find_spec("wxbridge.operator"),
            "State-changing Python gateway must not be importable",
        )

    @unittest.skipUnless(sys.platform == "win32", "Windows CMD launcher only")
    def test_old_cmd_launcher_always_fails_closed(self):
        old = ROOT / "WXBridgeUI.cmd"
        self.assertTrue(old.is_file())
        for args in [
            ("--help",), ("send", "SYNTHETIC-NO-RECIPIENT"),
            ("--allow-state-change", "send", "SYNTHETIC-NO-RECIPIENT"),
            ("--allow-state-change", "remark", "SYNTHETIC-NO-RECIPIENT",
             "--to", "SYNTHETIC"),
        ]:
            with self.subTest(args=args):
                done = subprocess.run([str(old), *args],
                                      capture_output=True, encoding="utf-8",
                                      timeout=10)
                self.assertEqual(done.returncode, 4)
                self.assertEqual(json.loads(done.stderr)["error"],
                                 "wxbridge_ui_disabled")

    def test_readonly_commands_still_visible(self):
        result = self._run("wxbridge", "--help")
        self.assertEqual(result.returncode, 0)
        for name in ("chats", "messages", "files", "moments"):
            self.assertIn("    " + name + " ", result.stdout)
        self.assertNotIn("--node", result.stdout)


if __name__ == "__main__":
    unittest.main()
