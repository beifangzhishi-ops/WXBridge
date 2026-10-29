import json
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wxbridge import cli

SRC = Path(__file__).resolve().parents[1] / "src"


class CLITests(unittest.TestCase):
    def run_tool(self, *args):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
        return subprocess.run([sys.executable, "-m", "wxbridge", *args],
                              text=True, encoding="utf-8", capture_output=True, env=env)

    def test_help(self):
        result = self.run_tool("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("cached-key", result.stdout)
        self.assertIn("default: cached-key", result.stdout)

    def test_no_arguments_print_help_and_exit_success(self):
        result = self.run_tool()
        self.assertEqual(result.returncode, 0)
        self.assertIn("sessions", result.stdout)

    def test_unknown_command_fails(self):
        self.assertNotEqual(self.run_tool("read").returncode, 0)

    def test_cached_session_requires_opt_in_without_touching_databases(self):
        output = self.run_tool("--backend", "cached-key", "sessions")
        self.assertEqual(output.returncode, 4)
        self.assertEqual(json.loads(output.stdout)["error"], "local_db_consent_required")

    def test_backend_default_and_snapshot_selection(self):
        parser = cli.build_parser()
        self.assertEqual(parser.parse_args(["sessions"]).backend, "cached-key")
        self.assertEqual(parser.parse_args(["--backend", "snapshot", "sessions"]).backend, "snapshot")
        with patch.dict(os.environ, {"WXBRIDGE_BACKEND": "snapshot"}):
            self.assertIn("default: snapshot", cli.build_parser().format_help())

    def test_provider_selection_does_not_claim_readiness(self):
        output = self.run_tool("providers")
        self.assertEqual(output.returncode, 0)
        doc = json.loads(output.stdout)
        self.assertEqual(doc["selected"], "cached-key")
        self.assertNotIn("connected", doc)
        self.assertNotIn("keyCache", doc)

    def test_read_errors_explain_missing_keys_only_after_a_query(self):
        failures = (
            (cli.KeyVaultError("no_local_key_cache"), "key_not_found"),
            (cli.KeyVaultError("unable_to_unlock_local_key_cache"), "key_unavailable"),
            (cli.CachedError("cache_missing_or_stale_for_current_databases"), "key_unavailable"),
            (cli.CachedError("database_root_unavailable"), "database_read_failed"),
        )
        for failure, expected in failures:
            with self.subTest(expected=expected, failure=str(failure)):
                stderr = StringIO()
                with patch.object(cli, "open_cached_reader", side_effect=failure):
                    with redirect_stderr(stderr):
                        rc = cli.main(["--backend", "cached-key", "--allow-local-db", "sessions"])
                self.assertEqual(rc, 4)
                self.assertEqual(json.loads(stderr.getvalue())["error"], expected)

    def test_cached_cli_emits_normalized_json_with_invented_reader(self):
        class InventedReader:
            def sessions(self, *, limit, keyword):
                return {"count": 1, "sessions": [
                    {"id": "fake-filehelper", "name": "Synthetic Conversation"}]}

        @contextmanager
        def stub_context():
            yield InventedReader()

        output = StringIO()
        with patch.object(cli, "open_cached_reader", stub_context), redirect_stdout(output):
            rc = cli.main(["--backend", "cached-key", "--allow-local-db",
                           "sessions", "--limit", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(output.getvalue())["sessions"][0]["name"],
                         "Synthetic Conversation")

    def test_json_response_is_safe_for_legacy_windows_gbk(self):
        output = StringIO()
        with redirect_stdout(output):
            cli._json({"title": "synthetic \U0001f680 \u4f1a\u8bdd"})
        raw = output.getvalue()
        self.assertEqual(raw.encode("gbk").decode("gbk"), raw)
        self.assertEqual(json.loads(raw)["title"], "synthetic \U0001f680 \u4f1a\u8bdd")

    def test_extended_read_only_commands_require_explicit_cached_consent(self):
        for action, params in (
            ("contacts", ("--keyword", "synthetic")),
            ("groups", ()),
            ("moments", ()),
            ("articles", ("--chat", "synthetic")),
            ("media-status", ("--chat", "synthetic", "--local-id", "7",
                              "--kind", "image")),
            ("media-read", ("--chat", "synthetic",
                            "--message-id", "message__message_3.db:602")),
        ):
            with self.subTest(action=action):
                output = self.run_tool("--backend", "cached-key", action, *params)
                self.assertEqual(output.returncode, 4)
                self.assertEqual(json.loads(output.stdout)["error"], "local_db_consent_required")

    def test_media_read_requires_exact_message_id(self):
        parser = cli.build_parser()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["media-read", "--chat", "synthetic"])


if __name__ == "__main__":
    unittest.main()
