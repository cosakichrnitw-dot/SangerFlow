"""MAFFT-specific executable detection and command construction adapter."""

from __future__ import annotations

import shutil
import subprocess
from typing import Callable

from core.tool_manager import ToolInfo, ToolStatus


MAFFT_TOOL_NAME = "MAFFT"


def detect_mafft(
    executable: str = "mafft",
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., object] = subprocess.run,
) -> ToolInfo:
    """Discover MAFFT and return immutable availability/version information."""
    if not isinstance(executable, str) or not executable.strip():
        raise ValueError("executable must be a non-empty string")
    executable_path = which(executable)
    if executable_path is None:
        return ToolInfo(
            name=MAFFT_TOOL_NAME,
            status=ToolStatus.MISSING,
            metadata={"requested_executable": executable},
        )
    try:
        result = runner(
            [executable_path, "--version"],
            text=True,
            capture_output=True,
        )
    except OSError as error:
        return ToolInfo(
            name=MAFFT_TOOL_NAME,
            executable_path=executable_path,
            status=ToolStatus.INVALID,
            metadata={"detection_error": str(error)},
        )
    if getattr(result, "returncode", None) != 0:
        return ToolInfo(
            name=MAFFT_TOOL_NAME,
            executable_path=executable_path,
            status=ToolStatus.INVALID,
            metadata={"version_error": getattr(result, "stderr", "")},
        )
    version_text = (getattr(result, "stdout", "") or getattr(result, "stderr", "")).strip()
    return ToolInfo(
        name=MAFFT_TOOL_NAME,
        version=version_text or None,
        executable_path=executable_path,
        status=ToolStatus.AVAILABLE,
        metadata={"requested_executable": executable},
    )


def build_mafft_command(
    executable_path: str,
    *,
    input_path: str = "-",
    auto: bool = True,
) -> tuple[str, ...]:
    """Build the existing MAFFT alignment command without executing it."""
    if not isinstance(executable_path, str) or not executable_path.strip():
        raise ValueError("executable_path must be a non-empty string")
    if not isinstance(input_path, str) or not input_path:
        raise ValueError("input_path must be a non-empty string")
    command = [executable_path]
    if auto:
        command.append("--auto")
    command.append(input_path)
    return tuple(command)
