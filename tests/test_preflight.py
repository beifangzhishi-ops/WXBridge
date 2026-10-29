import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wxbridge.preflight import preflight


class PreflightTests(unittest.TestCase):
    def test_counts_only_filenames_without_opening_database_content(self):
        # CCM's restricted Windows worker cannot create arbitrary temp dirs.
        # Mock metadata enumeration rather than opening or creating DB files.
        with patch.object(Path, "is_dir", return_value=True), patch(
            "wxbridge.preflight.os.walk",
            return_value=[("fake", [], ["message_0.db", "other.db", "ignored.ini"])],
        ):
            result = preflight(appdata="C:/synthetic")
        self.assertTrue(result["configPresent"])
        self.assertEqual(result["candidateDbFileCount"], 2)
        self.assertFalse(result["processMemoryReadAttempted"])
        self.assertFalse(result["messageContentReadAttempted"])
        self.assertIsNone(result["databaseReadable"])
        self.assertFalse(result["realMessageReadVerified"])

    def test_missing_files_report_unknown_not_unreadable(self):
        with patch.object(Path, "is_dir", return_value=False):
            result = preflight(appdata="C:/not-present")
        self.assertFalse(result["configPresent"])
        self.assertEqual(result["candidateDbFileCount"], 0)
        self.assertIsNone(result["databaseReadable"])
