"""Stable Studio entry point for source development and future frozen builds.

This avoids requiring users to manually set ``PYTHONPATH`` while retaining the
existing ``python -m app.main`` development command for compatibility.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _prepare_source_imports() -> None:
    if getattr(sys, "frozen", False):
        return
    studio_root = Path(__file__).resolve().parent
    repository_root = studio_root.parent
    for location in (studio_root, repository_root):
        text = str(location)
        if text not in sys.path:
            sys.path.insert(0, text)


def _prepare_frozen_macos_path() -> None:
    """Expose standard user-installed MAFFT locations to Finder launches.

    Finder's launch environment commonly omits ``/opt/homebrew/bin`` and
    ``/usr/local/bin``.  The existing MAFFT adapter still performs all
    discovery; this frozen-app-only adjustment merely gives it the same
    standard installation locations a Terminal launch would have.
    """

    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return
    current_paths = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    additions = ["/opt/homebrew/bin", "/usr/local/bin"]
    os.environ["PATH"] = os.pathsep.join(
        [*additions, *(part for part in current_paths if part not in additions)]
    )


def main() -> int:
    _prepare_source_imports()
    _prepare_frozen_macos_path()
    from app.main import main as run_studio

    return run_studio()


if __name__ == "__main__":
    raise SystemExit(main())
