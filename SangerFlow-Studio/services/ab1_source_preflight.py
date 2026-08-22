"""Preflight checks for copying AB1 source files into a Project Workspace.

The checks intentionally live in Studio rather than the AB1 reader: they
protect a file-management operation and do not alter AB1 parsing or any
scientific data model.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import os
from pathlib import Path
import stat as stat_module
import sys
from typing import Callable, Iterable


# Darwin's ``UF_DATALLESS`` flag.  It is meaningful only on macOS and marks a
# File Provider/iCloud placeholder whose content is not currently local.
MACOS_DATALLESS_FILE_FLAG = 0x40000000


@dataclass(frozen=True)
class Ab1SourcePreflightIssue:
    """One source file that must not be copied yet."""

    path: Path
    reason: str


class Ab1SourcePreflightError(ValueError):
    """A user-facing, aggregate error raised before any workspace copy."""

    def __init__(self, issues: Iterable[Ab1SourcePreflightIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__(_format_preflight_error(self.issues))


def preflight_ab1_copy_sources(
    files: Iterable[Path],
    *,
    platform: str | None = None,
    stat_fn: Callable[[Path], os.stat_result] = os.stat,
) -> None:
    """Reject unavailable sources before *any* ``Raw_Data`` copy starts.

    ``platform`` and ``stat_fn`` are injectable only to make the macOS-specific
    availability check testable on every supported platform.
    """

    current_platform = sys.platform if platform is None else platform
    issues: list[Ab1SourcePreflightIssue] = []
    for source in files:
        path = Path(source)
        try:
            source_stat = stat_fn(path)
        except FileNotFoundError:
            issues.append(Ab1SourcePreflightIssue(path, "missing"))
            continue
        except OSError as error:
            reason = "missing" if error.errno == errno.ENOENT else "unavailable"
            issues.append(Ab1SourcePreflightIssue(path, reason))
            continue

        if not stat_module.S_ISREG(source_stat.st_mode):
            issues.append(Ab1SourcePreflightIssue(path, "not_regular_file"))
            continue
        if current_platform == "darwin" and (
            int(getattr(source_stat, "st_flags", 0)) & MACOS_DATALLESS_FILE_FLAG
        ):
            issues.append(Ab1SourcePreflightIssue(path, "cloud_placeholder"))

    if issues:
        raise Ab1SourcePreflightError(issues)


def _format_preflight_error(issues: tuple[Ab1SourcePreflightIssue, ...]) -> str:
    has_cloud_placeholder = any(issue.reason == "cloud_placeholder" for issue in issues)
    if has_cloud_placeholder:
        message = (
            "Some AB1 files are stored in iCloud and are not downloaded to this Mac. "
            "Download them in Finder, then try the import again."
        )
    else:
        message = (
            "Some AB1 source files are unavailable for copying. "
            "Check that they still exist as local files, then try the import again."
        )

    affected = "\n".join(f"- {issue.path.name}\n  {issue.path}" for issue in issues)
    return f"{message}\n\nAffected files:\n{affected}"
