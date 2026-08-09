"""Viewer-provided action descriptors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True)
class ViewerAction:
    """A GUI action offered by the active viewer."""

    action_id: str
    label: str
    callback: Callable[[], None]
    tooltip: str = ""
    enabled: bool = True


class ViewerActionProvider(Protocol):
    """Protocol for objects that expose actions for one viewer."""

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        ...
