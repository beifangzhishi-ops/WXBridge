"""The headless API and Reader must never spawn a visible console."""

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from wxbridge import api, snapshot, upstream_extra
from wxbridge.process import NO_CONSOLE_FLAGS


class NoConsoleTests(unittest.TestCase):
    def assert_hidden_calls(self, run, count):
        self.assertEqual(run.call_count, count)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs["creationflags"], NO_CONSOLE_FLAGS)
            self.assertTrue(call.kwargs["capture_output"])
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            self.assertNotEqual(NO_CONSOLE_FLAGS, 0)

    def test_api_worker_preserves_json_and_suppresses_console(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"count":1}', stderr="")
        with patch.object(api.subprocess, "run", return_value=completed) as run:
            self.assertEqual(api.run_query(["sessions"]), (0, {"count": 1}))
        self.assert_hidden_calls(run, 1)

    def test_snapshot_git_verification_suppresses_console(self):
        def synthetic_git(args, **kwargs):
            output = snapshot.PIN if "HEAD" in args else "fictional-hash"
            return subprocess.CompletedProcess(args, 0, output, "")

        with patch.object(snapshot, "_upstream_dir", return_value=Path("synthetic")):
            with patch.object(Path, "is_file", return_value=True):
                with patch.object(snapshot, "frozen", return_value=False):
                    with patch.object(snapshot.subprocess, "run",
                                      side_effect=synthetic_git) as run:
                        with patch.object(snapshot.importlib.util,
                                          "spec_from_file_location",
                                          return_value=None):
                            with self.assertRaisesRegex(
                                snapshot.SnapshotError, "upstream_db_module_missing"
                            ):
                                snapshot._load_upstream()
        self.assert_hidden_calls(run, 3)

    def test_extra_git_verification_suppresses_console(self):
        def synthetic_git(args, **kwargs):
            output = snapshot.PIN if "HEAD" in args else "fictional-hash"
            return subprocess.CompletedProcess(args, 0, output, "")

        with patch.object(upstream_extra, "_upstream_dir",
                          return_value=Path("synthetic")):
            with patch.object(Path, "is_file", return_value=True):
                with patch.object(upstream_extra, "frozen", return_value=False):
                    with patch.object(upstream_extra.subprocess, "run",
                                      side_effect=synthetic_git) as run:
                        self.assertEqual(upstream_extra._source("media.py"),
                                         Path("synthetic/wechatauto/media.py"))
        self.assert_hidden_calls(run, 3)


if __name__ == "__main__":
    unittest.main()
