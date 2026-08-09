"""Core registry for optional external analysis tools.

The manager stores immutable discovery information only.  Tool-specific
subprocess calls remain in adapters under :mod:`tools`, so SangerFlow core can
remain usable when an external executable is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Callable, Mapping


class ToolStatus(str, Enum):
    """Availability state reported by an external-tool adapter."""

    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class ToolInfo:
    """Immutable discovery state for one optional external executable."""

    name: str
    version: str | None = None
    executable_path: str | None = None
    status: ToolStatus = ToolStatus.UNKNOWN
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("tool name must be a non-empty string")
        if self.version is not None and (
            not isinstance(self.version, str) or not self.version.strip()
        ):
            raise ValueError("tool version must be a non-empty string or None")
        if self.executable_path is not None and (
            not isinstance(self.executable_path, str) or not self.executable_path.strip()
        ):
            raise ValueError("executable_path must be a non-empty string or None")
        if not isinstance(self.status, ToolStatus):
            raise ValueError("status must be a ToolStatus")
        if self.status is ToolStatus.AVAILABLE and self.executable_path is None:
            raise ValueError("an AVAILABLE tool requires executable_path")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


ToolDetector = Callable[[], ToolInfo]


class ToolManager:
    """Controlled in-memory registry of optional tool discovery adapters."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolInfo] = {}
        self._detectors: dict[str, ToolDetector] = {}

    def register_tool(
        self,
        tool: ToolInfo,
        *,
        detector: ToolDetector | None = None,
    ) -> None:
        """Register a named tool and optional side-effecting adapter detector."""
        if not isinstance(tool, ToolInfo):
            raise ValueError("tool must be a ToolInfo")
        if tool.name in self._tools:
            raise ValueError(f"tool is already registered: {tool.name}")
        if detector is not None and not callable(detector):
            raise ValueError("detector must be callable or None")
        self._tools[tool.name] = tool
        if detector is not None:
            self._detectors[tool.name] = detector

    def get_tool(self, name: str) -> ToolInfo:
        """Return registered ToolInfo, or raise KeyError for an unknown name."""
        try:
            return self._tools[name]
        except KeyError as error:
            raise KeyError(name) from error

    def list_tools(self) -> tuple[ToolInfo, ...]:
        """Return tools in stable registration order."""
        return tuple(self._tools.values())

    def detect_tools(self) -> tuple[ToolInfo, ...]:
        """Run registered adapter detectors and return current tool state.

        A detector failure is isolated to that tool and recorded as INVALID;
        it never prevents other tools or SangerFlow core from operating.
        """
        for name, detector in tuple(self._detectors.items()):
            try:
                detected = detector()
                if not isinstance(detected, ToolInfo):
                    raise ValueError("detector must return ToolInfo")
                if detected.name != name:
                    raise ValueError("detector returned a ToolInfo for another tool")
            except Exception as error:  # Adapter failures must be non-fatal.
                detected = ToolInfo(
                    name=name,
                    status=ToolStatus.INVALID,
                    metadata={"detection_error": str(error)},
                )
            self._tools[name] = detected
        return self.list_tools()
