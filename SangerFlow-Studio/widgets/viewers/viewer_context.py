"""Small service context passed to Studio viewers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ViewerContext:
    """Application services a viewer may use without importing the shell."""

    app_state: object
    project_controller: object
    tab_manager: object | None = None
    dataset_controller: object | None = None
    analysis_controller: object | None = None
    result_resolver: object | None = None
    action_manager: object | None = None
    dock_manager: object | None = None
    read_visibility_manager: object | None = None
