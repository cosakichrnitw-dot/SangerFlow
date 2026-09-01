"""Viewer tab lifecycle management for SangerFlow-Studio."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QMenu

from app.app_state import AppState
from app.gui_thread import assert_main_gui_thread
from app.icon_registry import studio_icon
from widgets.workspace_tabs import WorkspaceTabs


@dataclass
class ViewerClosePlan:
    """One viewer's non-destructive close decision."""

    viewer_id: str
    intent: object


@dataclass
class CloseAllPlan:
    """A complete close transaction prepared without closing any tab."""

    viewers: tuple[ViewerClosePlan, ...]
    drain_remaining: bool = True
    committed: bool = False

    @property
    def requires_project_persistence(self) -> bool:
        return any(plan.intent == "save" for plan in self.viewers)


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
        self._tabs.hide_permanent_tab_close_buttons()
        self._tabs.tabCloseRequested.connect(self._close_tab_index)
        self._tab_bar.installEventFilter(self)
        self._tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tabs.customContextMenuRequested.connect(self._show_context_menu)
        self._tabs.currentChanged.connect(self._active_tab_changed)

    def open_viewer(self, viewer: object, *, resource_key: str | None = None) -> str:
        """Add or focus a viewer tab and return its stable viewer ID."""

        assert_main_gui_thread("TabManager.open_viewer/QTabWidget.addTab")
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
        self._tabs.hide_permanent_tab_close_buttons()
        self._tabs.setCurrentIndex(index)
        self._connect_viewer_signals(viewer)
        self._state.viewer_opened.emit(viewer)
        self._state.set_active_viewer(viewer)
        return viewer_id

    def focus_viewer(self, viewer_id: str) -> bool:
        assert_main_gui_thread("TabManager.focus_viewer/QTabWidget.setCurrentIndex")
        for index in range(self._tabs.count()):
            widget = self._tabs.widget(index)
            if getattr(widget, "viewer_id", None) == viewer_id:
                self._tabs.setCurrentIndex(index)
                self._state.set_active_viewer(widget)
                return True
        return False

    def close_viewer(self, viewer_id: str) -> bool:
        assert_main_gui_thread("TabManager.close_viewer/QTabWidget.removeTab")
        viewer = self._viewers.get(viewer_id)
        if viewer is None:
            return False
        intent = self._prepare_viewer_close(viewer)
        if intent is None or not self._commit_viewer_close(viewer, intent):
            return False
        return self._remove_viewer(viewer_id)

    def _remove_viewer(self, viewer_id: str) -> bool:
        """Detach a viewer after its close intent has already committed."""

        assert_main_gui_thread("TabManager._remove_viewer/QTabWidget.removeTab")
        viewer = self._viewers.get(viewer_id)
        if viewer is None:
            return False

        self._disconnect_viewer_signals(viewer)
        self._viewers.pop(viewer_id, None)
        for key, value in tuple(self._resource_to_viewer.items()):
            if value == viewer_id:
                self._resource_to_viewer.pop(key, None)

        # Drop all active GUI action references before this QWidget leaves its
        # tab.  currentChanged may select a permanent tab during removeTab().
        if self._state.active_viewer is viewer:
            self._state.set_active_viewer(None)

        for index in range(self._tabs.count()):
            if self._tabs.widget(index) is viewer:
                self._tabs.removeTab(index)
                break

        # removeTab() does not transfer ownership.  Detach first, then let Qt
        # delete the no-longer-visible viewer on the event loop; this avoids
        # hidden viewer widgets and their signal connections accumulating.
        hide = getattr(viewer, "hide", None)
        if callable(hide):
            hide()
        set_parent = getattr(viewer, "setParent", None)
        if callable(set_parent):
            set_parent(None)
        delete_later = getattr(viewer, "deleteLater", None)
        if callable(delete_later):
            delete_later()
        self._state.viewer_closed.emit(viewer_id)
        return True

    def close_others(self, viewer_id: str) -> bool:
        plan = self.prepare_close_all(exclude_viewer_ids={viewer_id})
        if plan is None:
            return False
        if not self.commit_close_changes(plan):
            return False
        return self.finalize_close_all(plan)

    def close_all(self) -> bool:
        """Close every viewer as one all-or-nothing transaction."""

        plan = self.prepare_close_all()
        if plan is None:
            return False
        if not self.commit_close_changes(plan):
            return False
        return self.finalize_close_all(plan)

    def prepare_close_all(
        self,
        *,
        exclude_viewer_ids: set[str] | None = None,
    ) -> CloseAllPlan | None:
        """Collect every close decision without saving, discarding, or closing.

        Returning ``None`` means a viewer selected Cancel.  No viewer state or
        tab ownership has changed in that case.
        """

        excluded = exclude_viewer_ids or set()
        plans: list[ViewerClosePlan] = []
        for viewer_id, viewer in tuple(self._viewers.items()):
            if viewer_id in excluded:
                continue
            intent = self._prepare_viewer_close(viewer)
            if intent is None:
                return None
            plans.append(ViewerClosePlan(viewer_id, intent))
        return CloseAllPlan(tuple(plans), drain_remaining=not excluded)

    def commit_close_changes(self, plan: CloseAllPlan) -> bool:
        """Save accepted editor intents but keep every tab open.

        This is deliberately separate from :meth:`finalize_close_all` so a
        Project-level bundle save can still fail without losing visible tabs.
        """

        if plan.committed:
            return True
        for entry in plan.viewers:
            viewer = self._viewers.get(entry.viewer_id)
            if viewer is None or not self._commit_viewer_close(viewer, entry.intent):
                return False
        plan.committed = True
        return True

    def finalize_close_all(self, plan: CloseAllPlan) -> bool:
        """Remove tabs only after all accepted close changes have committed."""

        if not plan.committed:
            return False
        for entry in plan.viewers:
            if entry.viewer_id in self._viewers and not self._remove_viewer(entry.viewer_id):
                return False

        # Saving an Editor can open a clean immutable-revision replacement.
        # It was created by this already-accepted transaction, so close it too
        # without another prompt.  A dirty unexpected viewer is never removed.
        while plan.drain_remaining and self._viewers:
            viewer_id, viewer = next(iter(self._viewers.items()))
            if bool(getattr(viewer, "is_dirty", False)):
                return False
            if not self._remove_viewer(viewer_id):
                return False
        return True

    @staticmethod
    def _prepare_viewer_close(viewer: object) -> object | None:
        prepare_close = getattr(viewer, "prepare_close", None)
        if callable(prepare_close):
            return prepare_close()
        return "close"

    @staticmethod
    def _commit_viewer_close(viewer: object, intent: object) -> bool:
        commit_close = getattr(viewer, "commit_close", None)
        if callable(commit_close):
            return bool(commit_close(intent))
        close_viewer = getattr(viewer, "close_viewer", None)
        return not callable(close_viewer) or bool(close_viewer())

    def active_viewer(self) -> object | None:
        widget = self._tabs.currentWidget()
        return widget if getattr(widget, "viewer_id", None) else None

    def viewer_for_resource_key(self, resource_key: str) -> object | None:
        """Return an already-open viewer for a resource key, if one exists."""

        viewer_id = self._resource_to_viewer.get(resource_key)
        if viewer_id is None:
            return None
        return self._viewers.get(viewer_id)

    def viewer_ids(self) -> tuple[str, ...]:
        return tuple(self._viewers)

    def _connect_viewer_signals(self, viewer: object) -> None:
        signal = getattr(viewer, "selection_changed", None)
        if signal is not None:
            signal.connect(self._state.set_selected_item)

    def _disconnect_viewer_signals(self, viewer: object) -> None:
        signal = getattr(viewer, "selection_changed", None)
        if signal is not None:
            try:
                signal.disconnect(self._state.set_selected_item)
            except (RuntimeError, TypeError):
                # A viewer without the connection is already safe to close.
                pass

    def _active_tab_changed(self, _index: int) -> None:
        assert_main_gui_thread("TabManager._active_tab_changed")
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
        close_action = menu.addAction(studio_icon("close"), "Close")
        close_others_action = menu.addAction(studio_icon("close"), "Close Others")
        close_all_action = menu.addAction(studio_icon("close"), "Close All")
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
