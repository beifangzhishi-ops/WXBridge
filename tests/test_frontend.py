"""Synthetic tests for the one-EXE routing boundary (no network/WeChat)."""

import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from wxbridge import frontend
from wxbridge.identity import local_identity
from wxbridge.api import valid_query_args


class FrontendTests(unittest.TestCase):
    def _identities(self, first, second):
        return {"6v": first, "noha": second}

    @staticmethod
    def _identity(state, account=None):
        return {"state": state, "accountId": account, "loginVerified": False}

    def test_no_arguments_are_help_only(self):
        out = io.StringIO()
        with patch.object(frontend, "query_identity") as probe, redirect_stdout(out):
            self.assertEqual(frontend.main([]), 0)
        probe.assert_not_called()
        self.assertIn("chats,messages,files,moments", out.getvalue())

    def test_single_account_autoroutes_to_same_api_even_for_6v(self):
        identities = self._identities(self._identity("candidate", "wxid_one"),
                                     self._identity("offline"))
        with patch.object(frontend, "_config", return_value={}):
            with patch.object(frontend, "query_identity", side_effect=lambda node: identities[node]):
                with patch.object(frontend, "query_remote", return_value=(0, {"sessions": []})) as query:
                    out = io.StringIO()
                    with redirect_stdout(out):
                        self.assertEqual(frontend.main(["chats"]), 0)
        query.assert_called_once_with(["sessions", "--limit", "20"], node="6v")
        self.assertEqual(json.loads(out.getvalue())["environment_id"], "DESKTOP-KFL6V1F")

    def test_named_account_routes_to_noha(self):
        identities = self._identities(self._identity("offline"),
                                     self._identity("candidate", "wxid_two"))
        cfg = {"default": "primary", "aliases": {"primary": "wxid_two"}}
        with patch.object(frontend, "_config", return_value=cfg):
            with patch.object(frontend, "query_identity", side_effect=lambda node: identities[node]):
                self.assertEqual(frontend.select_node(None), ("noha", "wxid_two"))

    def test_fails_closed_on_same_account_both_machines(self):
        identity = self._identity("candidate", "wxid_same")
        with patch.object(frontend, "_config", return_value={}):
            with patch.object(frontend, "query_identity", return_value=identity):
                with self.assertRaisesRegex(frontend.FrontendError, "multiple_environments"):
                    frontend.select_node(None)

    def test_fails_closed_on_unknown_or_unreachable(self):
        with patch.object(frontend, "_config", return_value={}):
            for second in (self._identity("unknown"), None):
                with self.subTest(second=second):
                    def identity(node):
                        if node == "6v":
                            return self._identity("candidate", "wxid_one")
                        if second is None:
                            raise frontend.RemoteError("remote_unreachable")
                        return second
                    with patch.object(frontend, "query_identity", side_effect=identity):
                        with self.assertRaises(frontend.FrontendError):
                            frontend.select_node(None)

    def test_public_operations_forward_existing_api_commands(self):
        ns = frontend.parser().parse_args(["files", "--chat", "wxid_person", "--id", "message__message_3.db:602"])
        with patch.object(frontend, "_query", return_value={"status": "available"}) as query:
            self.assertEqual(frontend._dispatch("noha", ns)["status"], "available")
        query.assert_called_once_with("noha", "media-read", "--chat", "wxid_person",
                                      "--message-id", "message__message_3.db:602")

    def test_api_only_exposes_bounded_read_operations(self):
        self.assertTrue(valid_query_args(["file-list", "--chat", "wxid_person"]))
        self.assertFalse(valid_query_args(["send", "hello"]))

    def test_local_identity_never_claims_verified_login(self):
        with patch("wxbridge.identity.wechat_process_state", return_value="present"):
            with patch("wxbridge.identity.unseal_keys", return_value=("wxid_demo_abcd", "hash", {})):
                result = local_identity()
        self.assertEqual(result["state"], "candidate")
        self.assertEqual(result["accountId"], "wxid_demo")
        self.assertFalse(result["loginVerified"])


if __name__ == "__main__":
    unittest.main()
