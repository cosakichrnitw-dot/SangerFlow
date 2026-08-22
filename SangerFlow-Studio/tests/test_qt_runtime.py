"""Regression checks for bounded Studio Qt plugin setup."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app import qt_runtime


def test_configure_qt_plugins_uses_ready_cache_without_copying() -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "source" / "platforms"
        cache = Path(directory) / "cache" / "platforms"
        source.mkdir(parents=True)
        cache.mkdir(parents=True)
        (source / "libqcocoa.dylib").write_bytes(b"source")
        for name in qt_runtime._PLUGIN_NAMES:
            (cache / name).write_bytes(b"cache")
        with (
            patch.object(qt_runtime.sys, "platform", "darwin"),
            patch.object(qt_runtime, "_source_platforms_directory", return_value=source),
            patch.object(qt_runtime, "_cached_platforms_directory", return_value=cache),
            patch.dict(os.environ, {}, clear=True),
        ):
            qt_runtime.configure_qt_plugins()
            assert os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(cache)


def test_configure_qt_plugins_returns_promptly_when_cache_copy_times_out() -> None:
    with TemporaryDirectory() as directory:
        source = Path(directory) / "source" / "platforms"
        cache = Path(directory) / "cache" / "platforms"
        source.mkdir(parents=True)
        (source / "libqcocoa.dylib").write_bytes(b"source")
        with (
            patch.object(qt_runtime.sys, "platform", "darwin"),
            patch.object(qt_runtime, "_source_platforms_directory", return_value=source),
            patch.object(qt_runtime, "_cached_platforms_directory", return_value=cache),
            patch.object(qt_runtime, "_prepare_platform_cache", side_effect=qt_runtime.subprocess.TimeoutExpired("cp", 5)),
            patch.dict(os.environ, {}, clear=True),
        ):
            started = time.monotonic()
            qt_runtime.configure_qt_plugins()
            assert time.monotonic() - started < 1.0
            assert os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] == str(source)
