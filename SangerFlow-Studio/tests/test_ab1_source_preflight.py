"""Copy-mode AB1 source availability checks."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from services.ab1_source_preflight import (
    Ab1SourcePreflightError,
    MACOS_DATALLESS_FILE_FLAG,
    preflight_ab1_copy_sources,
)


def _regular_stat(*, flags: int = 0) -> SimpleNamespace:
    return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_flags=flags)


class Ab1SourcePreflightTests(unittest.TestCase):
    def test_local_regular_file_is_allowed(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "local.ab1"
            source.write_bytes(b"AB1")
            preflight_ab1_copy_sources((source,), platform="darwin")

    def test_missing_source_is_rejected_before_copy(self) -> None:
        source = Path("/missing/source.ab1")
        with self.assertRaisesRegex(Ab1SourcePreflightError, "unavailable for copying") as raised:
            preflight_ab1_copy_sources((source,), platform="darwin")
        self.assertIn("source.ab1", str(raised.exception))
        self.assertNotIn("Errno", str(raised.exception))

    def test_macos_dataless_file_is_rejected_with_finder_guidance(self) -> None:
        source = Path("/iCloud/C17_FishF1.ab1")
        with self.assertRaisesRegex(Ab1SourcePreflightError, "stored in iCloud") as raised:
            preflight_ab1_copy_sources(
                (source,),
                platform="darwin",
                stat_fn=lambda _: _regular_stat(flags=MACOS_DATALLESS_FILE_FLAG),
            )
        self.assertIn("Download them in Finder", str(raised.exception))
        self.assertIn(str(source), str(raised.exception))

    def test_one_placeholder_rejects_the_whole_source_set(self) -> None:
        first = Path("/iCloud/local.ab1")
        placeholder = Path("/iCloud/placeholder.ab1")

        def stat_fn(path: Path) -> SimpleNamespace:
            return _regular_stat(
                flags=MACOS_DATALLESS_FILE_FLAG if path == placeholder else 0
            )

        with self.assertRaises(Ab1SourcePreflightError) as raised:
            preflight_ab1_copy_sources((first, placeholder), platform="darwin", stat_fn=stat_fn)
        self.assertEqual(tuple(issue.path for issue in raised.exception.issues), (placeholder,))

    def test_dataless_flag_is_ignored_off_macos(self) -> None:
        source = Path("/local/source.ab1")
        for platform in ("win32", "linux"):
            preflight_ab1_copy_sources(
                (source,),
                platform=platform,
                stat_fn=lambda _: _regular_stat(flags=MACOS_DATALLESS_FILE_FLAG),
            )

    def test_directory_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory)
            with self.assertRaisesRegex(Ab1SourcePreflightError, "unavailable for copying"):
                preflight_ab1_copy_sources((source,))
