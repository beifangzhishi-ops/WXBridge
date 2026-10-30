"""No external services, keys, or WeChat content required."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from wxbridge import supervisor


class TestApiSupervisor(unittest.TestCase):
    def test_health_probe_uses_authentication_and_disables_proxy(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({
            "apiReady": True, "node": "noha",
        }).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch.object(supervisor.request, "build_opener",
                          return_value=opener) as build:
            self.assertTrue(supervisor.api_healthy(
                "100.96.30.32", "noha", "fictional-secret"))
        self.assertEqual(len(build.call_args.args), 1)
        self.assertIsInstance(build.call_args.args[0],
                              supervisor.request.ProxyHandler)
        self.assertEqual(build.call_args.args[0].proxies, {})
        sent = opener.open.call_args.args[0]
        self.assertEqual(sent.get_header("X-wxbridge-token"),
                         "fictional-secret")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 2)

    def test_health_probe_rejects_wrong_node(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"apiReady":true,"node":"6v"}'
        with patch.object(supervisor.request, "build_opener") as build:
            build.return_value.open.return_value = response
            self.assertFalse(supervisor.api_healthy(
                "100.96.30.32", "noha", "fictional-secret"))

    def test_health_probe_rejects_network_failure(self):
        with patch.object(supervisor.request, "build_opener") as build:
            build.return_value.open.side_effect = TimeoutError()
            self.assertFalse(supervisor.api_healthy(
                "100.96.30.32", "noha", "fictional-secret"))

    @unittest.skipUnless(__import__("os").name == "nt", "Windows file lock")
    def test_only_one_supervisor_holds_local_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            first = supervisor.acquire_singleton(state)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(supervisor.acquire_singleton(state))
            finally:
                first.close()
            third = supervisor.acquire_singleton(state)
            self.assertIsNotNone(third)
            third.close()

    def test_stop_child_only_terminates_own_live_process(self):
        child = Mock()
        child.poll.return_value = None
        supervisor.stop_child(child)
        child.terminate.assert_called_once_with()
        child.wait.assert_called_once_with(timeout=5)
        already_stopped = Mock()
        already_stopped.poll.return_value = 1
        supervisor.stop_child(already_stopped)
        already_stopped.terminate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
