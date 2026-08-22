"""Bounded Qt platform-plugin setup for source-tree development."""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


_COPY_TIMEOUT_SECONDS = 5
_PLUGIN_NAMES = ("libqcocoa.dylib", "libqminimal.dylib", "libqoffscreen.dylib")


def configure_qt_plugins() -> None:
    """Configure a bounded, reusable local platform-plugin cache on macOS.

    Qt's C++ plugin loader can fail to enumerate PySide6 plugins from a macOS
    File Provider volume.  The former workaround used ``cp -R`` into a fresh
    temporary directory on every launch; that recursive subprocess could wait
    indefinitely.  This version reuses a deterministic cache and copies only
    the three platform dylibs if the cache is absent.  The compatibility copy
    has a hard timeout, so startup never waits indefinitely.

    Frozen applications remain the responsibility of their packaging layout.
    """

    if getattr(sys, "frozen", False) or sys.platform != "darwin":
        return
    if os.environ.get("SANGERFLOW_STUDIO_DISABLE_QT_PLUGIN_COPY"):
        return
    if os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return

    source_platforms = _source_platforms_directory()
    if source_platforms is None:
        return
    cached_platforms = _cached_platforms_directory(source_platforms)
    if not _is_ready_platform_directory(cached_platforms):
        try:
            _prepare_platform_cache(source_platforms, cached_platforms)
        except (OSError, subprocess.SubprocessError):
            # Direct use may work on a normal local filesystem.  More
            # importantly, it is a non-blocking failure path.
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(source_platforms)
            return
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(cached_platforms)


def _source_platforms_directory() -> Path | None:
    spec = importlib.util.find_spec("PySide6")
    if spec is None or spec.origin is None:
        return None
    platforms = Path(spec.origin).parent / "Qt" / "plugins" / "platforms"
    return platforms if platforms.is_dir() else None


def _cached_platforms_directory(source_platforms: Path) -> Path:
    cocoa = source_platforms / "libqcocoa.dylib"
    try:
        # ``copy-v2`` deliberately invalidates an earlier hard-link cache:
        # Qt's C++ loader still followed that link onto the File Provider
        # volume rather than loading a local copy.
        signature = f"copy-v2:{source_platforms}:{cocoa.stat().st_size}:{cocoa.stat().st_mtime_ns}"
    except OSError:
        signature = str(source_platforms)
    key = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "sangerflow_studio_qt_plugins" / key / "platforms"


def _is_ready_platform_directory(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in _PLUGIN_NAMES)


def _prepare_platform_cache(source_platforms: Path, target_platforms: Path) -> None:
    """Copy only platform dylibs once, with a bounded subprocess fallback."""

    if _is_ready_platform_directory(target_platforms):
        return
    source_files = tuple(source_platforms / name for name in _PLUGIN_NAMES)
    if not all(path.is_file() for path in source_files):
        raise OSError("PySide6 platform plugins are incomplete")

    cache_root = target_platforms.parent
    staging = cache_root / f".platforms-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=False)
    try:
        # Do not use recursive cp: platform plugins are standalone dylibs and
        # their Qt framework dependencies remain resolved from PySide6 rpaths.
        subprocess.run(
            ["/bin/cp", *(str(path) for path in source_files), str(staging)],
            check=True,
            timeout=_COPY_TIMEOUT_SECONDS,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if not _is_ready_platform_directory(staging):
            raise OSError("Qt platform-plugin cache preparation was incomplete")
        if not _is_ready_platform_directory(target_platforms):
            os.replace(staging, target_platforms)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
