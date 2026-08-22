"""Stable Studio entry point for source development and future frozen builds.

This avoids requiring users to manually set ``PYTHONPATH`` while retaining the
existing ``python -m app.main`` development command for compatibility.
"""

from __future__ import annotations

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


def main() -> int:
    _prepare_source_imports()
    from app.main import main as run_studio

    return run_studio()


if __name__ == "__main__":
    raise SystemExit(main())
