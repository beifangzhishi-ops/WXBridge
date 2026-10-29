"""Synthetic protocol tests; no sockets, chat data, or real key cache."""

import io
import json
import unittest
from unittest.mock import patch

from wxbridge.api import API_VERSION, valid_query_args
from wxbridge.frontend import main
from wxbridge.remote import RemoteError, query_remote


class TestRemoteApi(unittest.TestCase):
    def test_only_read_commands(self):
        self.assertTrue(valid_query_args(["sessions", "--limit", "2"]))
        self.assertTrue(valid_query_args(["media-read", "--chat", "fiction"]))
        for args in ([], ["send", "hello"], ["forward"],
                     ["preflight"], ["sessions", ""], "sessions",
                     ["sessions", "a" * 301], ["sessions"] * 33):
            with self.subTest(args=args):
                self.assertFalse(valid_query_args(args))

    def test_client_rejects_unconfigured_and_public_endpoint(self):
        with self.assertRaisesRegex(RemoteError, "remote_api_not_configured"):
            query_remote(["sessions"], url="http://100.96.30.32:18763",
                         token="")
        with self.assertRaisesRegex(RemoteError, "remote_endpoint_not_tailscale"):
            query_remote(["sessions"], url="http://example.com:18763",
                         token="synthetic-test-token")
        with self.assertRaisesRegex(RemoteError, "unknown_remote_node"):
            query_remote(["sessions"], node="untrusted", url="http://100.96.30.32:18763",
                         token="synthetic-test-token")

    def test_uses_wire_protocol_without_proxy(self):
        payload = json.dumps({
            "protocol": API_VERSION, "exitCode": 0,
            "data": {"sessions": [{"id": "invented"}]},
        }).encode()

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, _limit):
                return payload

        class Opener:
            def open(self, req, timeout):
                self.request = req
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch("wxbridge.remote.request.build_opener", return_value=opener) as mock:
            code, result = query_remote(
                ["sessions", "--limit", "1"],
                url="http://100.96.30.32:18763",
                token="synthetic-test-token",
            )
        self.assertEqual(code, 0)
        self.assertEqual(result["sessions"][0]["id"], "invented")
        self.assertEqual(opener.timeout, 30)
        self.assertEqual(json.loads(opener.request.data)["args"],
                         ["sessions", "--limit", "1"])
        self.assertTrue(mock.called)

    def test_second_node_uses_identical_transport(self):
        with patch("wxbridge.remote.request.build_opener") as opener:
            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    pass

                def read(self, _):
                    return b'{"protocol":1,"exitCode":0,"data":{"node":"6v"}}'
            opener.return_value.open.return_value = FakeResponse()
            code, result = query_remote(
                ["self"], node="6v",
                url="http://100.76.74.124:18763", token="synthetic-test-token")
        self.assertEqual((code, result["node"]), (0, "6v"))

    def test_new_public_cli_never_opens_local_db(self):
        with patch("wxbridge.frontend.query_identity", side_effect=RemoteError("remote_unreachable")):
            with patch("wxbridge.cached.open_cached_reader") as reader:
                with patch("sys.stderr", new_callable=io.StringIO):
                    code = main(["chats"])
        self.assertEqual(code, 4)
        reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
