"""Central workspace tabs, intentionally independent of analysis widgets."""

from PySide6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from app.app_state import AppState
from controllers.project_controller import ProjectController


class WorkspaceTabs(QTabWidget):
    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._controller = controller
        self.addTab(self._message_tab("Welcome to SangerFlow-Studio"), "Welcome")
        self.addTab(self._message_tab("Open a Project to view its datasets and analysis results."), "Project Summary")
        self.currentChanged.connect(self._tab_changed)
        state.active_tab_changed.connect(self._activate_tab)

    @staticmethod
    def _message_tab(message: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel(message))
        layout.addStretch()
        return widget

    def _tab_changed(self, index: int) -> None:
        self._controller.activate_tab(self.tabText(index))

    def _activate_tab(self, tab_name: str) -> None:
        for index in range(self.count()):
            if self.tabText(index) == tab_name and index != self.currentIndex():
                self.setCurrentIndex(index)
                return
