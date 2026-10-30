"""Synthetic tests for the one-EXE routing boundary (no network/WeChat)."""

import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch

from wxbridge import frontend
from wxbridge.identity import _window_evidence, local_identity
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
        identities = self._identities(self._identity("online", "wxid_one"),
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
                                     self._identity("online", "wxid_two"))
        cfg = {"default": "primary", "aliases": {"primary": "wxid_two"}}
        with patch.object(frontend, "_config", return_value=cfg):
            with patch.object(frontend, "query_identity", side_effect=lambda node: identities[node]):
                self.assertEqual(frontend.select_node(None), ("noha", "wxid_two"))

    def test_fails_closed_on_same_account_both_machines(self):
        identity = self._identity("online", "wxid_same")
        with patch.object(frontend, "_config", return_value={}):
            with patch.object(frontend, "query_identity", return_value=identity):
                with self.assertRaisesRegex(frontend.FrontendError, "multiple_environments"):
                    frontend.select_node(None)

    def test_offline_or_unreachable_peer_does_not_block_online_account(self):
        with patch.object(frontend, "_config", return_value={}):
            for second in (self._identity("offline", "wxid_one"), None):
                with self.subTest(second=second):
                    def identity(node):
                        if node == "6v":
                            return self._identity("online", "wxid_one")
                        if second is None:
                            raise frontend.RemoteError("remote_unreachable")
                        return second
                    with patch.object(frontend, "query_identity", side_effect=identity):
                        self.assertEqual(frontend.select_node(None), ("6v", "wxid_one"))

    def test_unreachable_node_does_not_count_as_confirmed_online(self):
        with patch.object(frontend, "_config", return_value={}):
            with patch.object(frontend, "query_identity",
                              side_effect=frontend.RemoteError("remote_unreachable")):
                with self.assertRaisesRegex(frontend.FrontendError, "environment_status_unavailable"):
                    frontend.select_node(None)

    def test_two_offline_nodes_have_no_selected_account(self):
        with patch.object(frontend, "_config", return_value={}):
            with patch.object(frontend, "query_identity", return_value=self._identity("offline", "wxid_same")):
                with self.assertRaisesRegex(frontend.FrontendError, "account_not_found"):
                    frontend.select_node(None)

    def test_public_operations_forward_existing_api_commands(self):
        ns = frontend.parser().parse_args(["files", "--chat", "wxid_person", "--id", "message__message_3.db:602"])
        with patch.object(frontend, "_query", return_value={"status": "available"}) as query:
            self.assertEqual(frontend._dispatch("noha", ns)["status"], "available")
        query.assert_called_once_with("noha", "media-read", "--chat", "wxid_person",
                                      "--message-id", "message__message_3.db:602")

    def test_unique_partial_nickname_resolves_for_messages(self):
        def api(_node, command, *_args):
            if command == "sessions":
                return {"sessions": []}
            if command == "contacts":
                return {"contacts": [{"username": "wxid_fictional", "nick_name": "狂人朋友"}]}
            raise AssertionError(command)
        with patch.object(frontend, "_query", side_effect=api):
            self.assertEqual(frontend._resolve_chat("noha", "狂人"), "wxid_fictional")

    def test_ambiguous_partial_nicknames_are_not_guessed(self):
        def api(_node, command, *_args):
            return ({"sessions": []} if command == "sessions" else
                    {"contacts": [{"username": "wxid_a", "nick_name": "狂人一"},
                                  {"username": "wxid_b", "nick_name": "狂人二"}]})
        with patch.object(frontend, "_query", side_effect=api):
            with self.assertRaisesRegex(frontend.FrontendError, "ambiguous_chat"):
                frontend._resolve_chat("noha", "狂人")

    def test_group_name_resolves_when_no_contact_matches(self):
        def api(_node, command, *_args):
            return {"sessions": []} if command == "sessions" else (
                {"contacts": []} if command == "contacts" else
                {"groups": [{"username": "fictional@chatroom", "name": "测试交流群"}]})
        with patch.object(frontend, "_query", side_effect=api):
            self.assertEqual(frontend._resolve_chat("noha", "交流群"), "fictional@chatroom")

    def test_api_only_exposes_bounded_read_operations(self):
        self.assertTrue(valid_query_args(["file-list", "--chat", "wxid_person"]))
        self.assertFalse(valid_query_args(["send", "hello"]))

    def test_local_identity_never_claims_verified_login(self):
        with patch("wxbridge.identity.wechat_process_state", return_value="present"):
            with patch("wxbridge.identity.wechat_window_state", return_value="main_window"):
                with patch("wxbridge.identity.unseal_keys", return_value=("wxid_demo_abcd", "hash", {})):
                    result = local_identity()
        self.assertEqual(result["state"], "online")
        self.assertEqual(result["accountId"], "wxid_demo")
        self.assertFalse(result["loginVerified"])

    def test_login_window_is_not_an_online_account(self):
        with patch("wxbridge.identity.wechat_process_state", return_value="present"):
            with patch("wxbridge.identity.wechat_window_state", return_value="login_window"):
                with patch("wxbridge.identity.unseal_keys", return_value=("wxid_demo_abcd", "hash", {})):
                    result = local_identity()
        self.assertEqual(result["state"], "offline")
        self.assertEqual(result["windowState"], "login_window")

    def test_read_only_window_evidence_is_conservative(self):
        self.assertEqual(_window_evidence(1, [(296, 388)]), "login_window")
        self.assertEqual(_window_evidence(5, [(1339, 942)]), "main_window")
        self.assertEqual(_window_evidence(1, [(330, 257), (296, 388)]), "login_window")
        self.assertEqual(_window_evidence(1, []), "unknown")
        self.assertEqual(_window_evidence(5, [(296, 388)]), "login_window")

    def test_ambiguous_window_is_offline(self):
        with patch("wxbridge.identity.wechat_process_state", return_value="present"):
            with patch("wxbridge.identity.wechat_window_state", return_value="unknown"):
                with patch("wxbridge.identity.unseal_keys", return_value=("wxid_demo_abcd", "hash", {})):
                    result = local_identity()
        self.assertEqual(result["state"], "offline")
        self.assertTrue(result["accountId"])


if __name__ == "__main__":
    unittest.main()
