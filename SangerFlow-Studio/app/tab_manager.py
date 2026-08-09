"""Viewer tab lifecycle management for SangerFlow-Studio."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QMenu

from app.app_state import AppState
from widgets.workspace_tabs import WorkspaceTabs


class TabManager(QObject):
    """Owns viewer tabs without deciding which viewer should be created."""

    def __init__(self, tabs: WorkspaceTabs, state: AppState) -> None:
        super().__init__()
        self._tabs = tabs
        self._state = state
        self._viewers: dict[str, object] = {}
        self._resource_to_viewer: dict[str, str] = {}
        self._tab_bar = self._tabs.tabBar()
        self._tabs.setTabsClosable(True)
        self._tabs.tabCloseRequested.connect(self._close_tab_index)
        self._tab_bar.installEventFilter(self)
        self._tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tabs.customContextMenuRequested.connect(self._show_context_menu)
        self._tabs.currentChanged.connect(self._active_tab_changed)

    def open_viewer(self, viewer: object, *, resource_key: str | None = None) -> str:
        """Add or focus a viewer tab and return its stable viewer ID."""

        viewer_id = getattr(viewer, "viewer_id")
        if resource_key and resource_key in self._resource_to_viewer:
            existing_viewer_id = self._resource_to_viewer[resource_key]
            self.focus_viewer(existing_viewer_id)
            return existing_viewer_id
        if viewer_id in self._viewers:
            self.focus_viewer(viewer_id)
            return viewer_id

        title = getattr(viewer, "viewer_title", viewer_id)
        self._viewers[viewer_id] = viewer
        if resource_key:
            self._resource_to_viewer[resource_key] = viewer_id
        index = self._tabs.addTab(viewer, title)
        self._tabs.setCurrentIndex(index)
        self._connect_viewer_signals(viewer)
        self._state.viewer_opened.emit(viewer)
        self._state.set_active_viewer(viewer)
        return viewer_id

    def focus_viewer(self, viewer_id: str) -> bool:
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if getattr(widget, "viewer_id", None) == viewer_id:
                self._tabs.setCurrentIndex(index)
                self._state.set_active_viewer(widget)
                return True
        return False

    def close_viewer(self, viewer_id: str) -> bool:
        viewer = self._viewers.get(viewer_id)
        if viewer is None:
            return False
        close_viewer = getattr(viewer, "close_viewer", None)
        if callable(close_viewer) and not close_viewer():
            return False

        for index in range(self._tabs.count()):
            if self._tabs.widget(index) is viewer:
                self._tabs.removeTab(index)
                break

        self._viewers.pop(viewer_id, None)
        for key, value in tuple(self._resource_to_viewer.items()):
            if value == viewer_id:
                self._resource_to_viewer.pop(key, None)
        self._state.viewer_closed.emit(viewer_id)
        if self._state.active_viewer is viewer:
            self._state.set_active_viewer(None)
        return True

    def close_others(self, viewer_id: str) -> None:
        for existing_viewer_id in tuple(self._viewers):
            if existing_viewer_id != viewer_id:
                self.close_viewer(existing_viewer_id)

    def close_all(self) -> None:
        for viewer_id in tuple(self._viewers):
            self.close_viewer(viewer_id)

    def active_viewer(self) -> object | None:
        widget = self._tabs.currentWidget()
        return widget if getattr(widget, "viewer_id", None) else None

    def viewer_ids(self) -> tuple[str, ...]:
        return tuple(self._viewers)

    def _connect_viewer_signals(self, viewer: object) -> None:
        signal = getattr(viewer, "selection_changed", None)
        if signal is not None:
            signal.connect(self._state.set_selected_item)

    def _active_tab_changed(self, _index: int) -> None:
        viewer = self.active_viewer()
        self._state.set_active_viewer(viewer)

    def _close_tab_index(self, index: int) -> None:
        widget = self._tabs.widget(index)
        viewer_id = getattr(widget, "viewer_id", None)
        if viewer_id is not None:
            self.close_viewer(viewer_id)

    def _show_context_menu(self, position) -> None:
        index = self._tabs.tabBar().tabAt(position)
        if index < 0:
            return
        widget = self._tabs.widget(index)
        viewer_id = getattr(widget, "viewer_id", None)
        if viewer_id is None:
            return
        menu = QMenu(self._tabs)
        close_action = menu.addAction("Close")
        close_others_action = menu.addAction("Close Others")
        close_all_action = menu.addAction("Close All")
        action = menu.exec(self._tabs.mapToGlobal(position))
        if action is close_action:
            self.close_viewer(viewer_id)
        elif action is close_others_action:
            self.close_others(viewer_id)
        elif action is close_all_action:
            self.close_all()

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt override
        tab_bar = getattr(self, "_tab_bar", None)
        if tab_bar is not None and watched is tab_bar and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.MiddleButton:
                index = tab_bar.tabAt(event.position().toPoint())
                if index >= 0:
                    self._close_tab_index(index)
                    return True
        return super().eventFilter(watched, event)
