"""Small OS-neutral path helpers for externally supplied source references."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


def source_filename(filepath: str | Path) -> str:
    """Return the terminal filename for POSIX *or* Windows path spelling.

    Project metadata can be opened on a host different from the one that
    created it, so ``Path(value).name`` alone is insufficient for a stored
    Windows path while running on macOS/Linux.
    """

    value = str(filepath)
    return PureWindowsPath(value).name if "\\" in value else Path(value).name
