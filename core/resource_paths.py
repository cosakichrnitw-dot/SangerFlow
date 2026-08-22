"""Single resource-location boundary for development and frozen runtimes.

Scientific modules use this helper only to locate read-only application assets.
It deliberately does not resolve user data, Projects, or external tools.
"""

from __future__ import annotations

from pathlib import Path
import sys


def application_resource_path(*parts: str) -> Path:
    """Return a packaged or source-tree resource path.

    PyInstaller exposes bundled data through ``_MEIPASS``.  During normal
    repository development the SangerFlow repository root is the parent of
    ``core``.  Keeping this distinction here prevents working-directory
    dependent resource lookup throughout the application.
    """

    frozen_root = getattr(sys, "_MEIPASS", None) if getattr(sys, "frozen", False) else None
    root = Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[1]
    return root.joinpath(*parts)

