"""macOS Qt runtime setup for the Studio prototype."""

from __future__ import annotations

import atexit
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_TEMP_PLUGIN_ROOT: Path | None = None


def configure_qt_plugins() -> None:
    """Use a /tmp copy of PySide6 platform plugins on macOS.

    Some macOS File Provider backed project directories let Python list the
    bundled PySide6 plugins while Qt's C++ factory loader sees an empty plugin
    directory. Copying with the system cp command into /tmp avoids that state.
    """

    if sys.platform != "darwin":
        return
    if os.environ.get("SANGERFLOW_STUDIO_DISABLE_QT_PLUGIN_COPY"):
        return
    if os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"):
        return

    spec = importlib.util.find_spec("PySide6")
    if spec is None or spec.origin is None:
        return

    package_dir = Path(spec.origin).resolve().parent
    source_platforms = package_dir / "Qt" / "plugins" / "platforms"
    if not source_platforms.exists():
        return

    global _TEMP_PLUGIN_ROOT
    _TEMP_PLUGIN_ROOT = Path(tempfile.mkdtemp(prefix="sangerflow_studio_qt_", dir="/tmp"))
    target_platforms = _TEMP_PLUGIN_ROOT / "platforms"
    subprocess.run(
        ["/bin/cp", "-R", str(source_platforms), str(target_platforms)],
        check=True,
    )
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(target_platforms)
    atexit.register(_cleanup_temp_plugins)


def _cleanup_temp_plugins() -> None:
    if _TEMP_PLUGIN_ROOT is not None:
        shutil.rmtree(_TEMP_PLUGIN_ROOT, ignore_errors=True)
