"""Dock panel lifecycle management for SangerFlow-Studio."""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import QMainWindow

from app.gui_thread import assert_main_gui_thread


class DockManager(QObject):
    """Own reusable dock panels without putting dock logic inside viewers."""

    def __init__(self, visibility_manager: object) -> None:
        super().__init__()
        self._main_window: QMainWindow | None = None
        self._visibility_manager = visibility_manager
        self._quality_dock = None

    def attach_main_window(self, main_window: QMainWindow) -> None:
        assert_main_gui_thread("DockManager.attach_main_window")
        self._main_window = main_window

    def show_quality_report(
        self,
        read_views: tuple[object, ...],
        *,
        source_key: str,
    ) -> object | None:
        assert_main_gui_thread("DockManager.show_quality_report/QDockWidget")
        if self._main_window is None:
            return None
        from widgets.quality_report_dock import QualityReportDock

        if self._quality_dock is None:
            self._quality_dock = QualityReportDock(
                visibility_manager=self._visibility_manager,
                parent=self._main_window,
            )
            self._main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea,
                self._quality_dock,
            )
        self._quality_dock.set_reads(read_views, source_key=source_key)
        self._quality_dock.show()
        self._quality_dock.raise_()
        return self._quality_dock

    def set_docks_visible(self, visible: bool) -> None:
        """Hide/show existing dock panels without destroying their session state."""

        assert_main_gui_thread("DockManager.set_docks_visible/QDockWidget")
        if self._quality_dock is not None:
            self._quality_dock.setVisible(bool(visible))
