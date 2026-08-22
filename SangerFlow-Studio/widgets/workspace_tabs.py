"""Central workspace tabs, intentionally independent of analysis widgets."""

from PySide6.QtWidgets import QLabel, QTabBar, QTabWidget, QVBoxLayout, QWidget

from app.app_state import AppState
from controllers.project_controller import ProjectController
from widgets.project_summary_graph import ProjectSummaryGraph


class WorkspaceTabs(QTabWidget):
    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._controller = controller
        self.addTab(self._message_tab("Welcome to SangerFlow-Studio"), "Welcome")
        self._project_summary = ProjectSummaryGraph(state, controller)
        self.addTab(self._project_summary, "Project Summary")
        self.currentChanged.connect(self._tab_changed)
        state.active_tab_changed.connect(self._activate_tab)
        state.project_changed.connect(self._project_changed)

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

    def _project_changed(self, project: object | None) -> None:
        self._controller.activate_tab("Project Summary" if project is not None else "Welcome")

    def hide_permanent_tab_close_buttons(self) -> None:
        """Keep Welcome and Project Summary visibly permanent.

        QTabWidget applies the global closable-tab policy to every tab.  The
        TabManager calls this after enabling closable Viewer tabs and whenever
        it adds a Viewer tab.
        """

        tab_bar = self.tabBar()
        for index in range(min(2, self.count())):
            tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
