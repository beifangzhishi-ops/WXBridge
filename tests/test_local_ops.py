"""Internal API subprocess dispatch; no public legacy CLI."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from wxbridge import local_ops


class LocalOpsTests(unittest.TestCase):
    def test_reader_is_bounded_and_internal(self):
        p = local_ops.parser()
        args = p.parse_args(["messages", "--chat", "wxid_fictional"])
        self.assertEqual(args.limit, 30)
        with self.assertRaises(SystemExit):
            p.parse_args(["send"])
        with self.assertRaises(SystemExit):
            p.parse_args(["messages", "--chat", "fictional", "--limit", "999"])

    def test_local_operation_emits_json(self):
        out = io.StringIO()
        with patch.object(local_ops, "execute", return_value={"sessions": []}):
            with redirect_stdout(out):
                self.assertEqual(local_ops.main(["sessions"]), 0)
        self.assertEqual(json.loads(out.getvalue()), {"sessions": []})

    def test_no_recursive_api_route(self):
        # Internal module has no network routing imports or node/environment flags.
        self.assertNotIn("--node", local_ops.parser().format_help())
        self.assertNotIn("--account", local_ops.parser().format_help())


if __name__ == "__main__":
    unittest.main()
