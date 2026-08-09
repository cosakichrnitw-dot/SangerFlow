"""Minimal viewer action management for SangerFlow-Studio."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar

from app.app_state import AppState


class ActionManager(QObject):
    """Expose active-viewer actions through a toolbar."""

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._toolbar: QToolBar | None = None
        self._actions: dict[str, QAction] = {}
        state.active_viewer_changed.connect(self.update_for_active_viewer)

    def attach_toolbar(self, toolbar: QToolBar) -> None:
        self._toolbar = toolbar
        self.update_for_active_viewer(self._state.active_viewer)

    def update_for_active_viewer(self, viewer: object | None = None) -> None:
        if self._toolbar is None:
            return
        for action in self._actions.values():
            self._toolbar.removeAction(action)
        self._actions.clear()
        if viewer is None:
            return
        for provider in getattr(viewer, "action_providers", ()):
            for descriptor in provider.actions_for(viewer):
                action = QAction(descriptor.label, self._toolbar)
                action.setEnabled(descriptor.enabled)
                action.setToolTip(descriptor.tooltip or descriptor.label)
                action.triggered.connect(
                    lambda _checked=False, callback=descriptor.callback: callback()
                )
                self._toolbar.addAction(action)
                self._actions[descriptor.action_id] = action

    def action(self, action_id: str) -> QAction | None:
        return self._actions.get(action_id)

    def action_ids(self) -> tuple[str, ...]:
        return tuple(self._actions)
