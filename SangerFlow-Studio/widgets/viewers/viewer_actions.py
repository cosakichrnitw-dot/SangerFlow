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
    # Presentation metadata deliberately remains small.  Action IDs and
    # callbacks are the stable application contract; these fields only decide
    # where a currently active viewer action is presented.
    toolbar: bool = False
    toolbar_group: str | None = None
    menu_group: str | None = None
    context_scope: str | None = None
    priority: int = 0


class ViewerActionProvider(Protocol):
    """Protocol for objects that expose actions for one viewer."""

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        ...
