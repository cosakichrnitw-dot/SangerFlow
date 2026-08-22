"""Pure path/resource regressions shared by macOS and Windows CI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.ab1_reader import read_ab1
from core.config import CONFIG_PATH, load_qc_config
from core.path_utils import source_filename


class CrossPlatformPathTests(unittest.TestCase):
    def test_source_filename_accepts_windows_and_posix_spellings(self) -> None:
        self.assertEqual(source_filename(r"C:\data\C2_FishF1.ab1"), "C2_FishF1.ab1")
        self.assertEqual(
            source_filename("/Users/example/C2_FishF1.ab1"),
            "C2_FishF1.ab1",
        )

    def test_ab1_reader_uses_platform_neutral_filename_labels(self) -> None:
        record = SimpleNamespace(
            annotations={
                "abif_raw": {
                    "DATA9": [1], "DATA10": [1], "DATA11": [1], "DATA12": [1],
                    "PLOC2": [0, 1, 2, 3],
                }
            },
            seq="ATGC",
            letter_annotations={"phred_quality": [40, 40, 40, 40]},
        )
        with patch("core.ab1_reader.SeqIO.read", return_value=record):
            windows = read_ab1(r"C:\data\C2_FishF1.ab1")
            posix = read_ab1("/Users/example/C2_FishF1.ab1")
        self.assertEqual(windows.filename, "C2_FishF1.ab1")
        self.assertEqual(posix.filename, "C2_FishF1.ab1")

    def test_source_filename_preserves_unicode_spaces_and_japanese(self) -> None:
        self.assertEqual(
            source_filename(r"C:\研究 データ\サンプル 1.ab1"),
            "サンプル 1.ab1",
        )

    def test_qc_resource_is_resolved_independently_of_current_directory(self) -> None:
        self.assertTrue(CONFIG_PATH.is_file())
        self.assertIn("terminal_quality", load_qc_config())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
