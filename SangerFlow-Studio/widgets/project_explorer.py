"""Tree presentation of immutable Project datasets and analysis results."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from app.app_state import AppState
from app.selection import StudioSelection
from controllers.project_controller import ProjectController


class ProjectExplorer(QTreeWidget):
    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._controller = controller
        self.setHeaderLabels(["Project Explorer"])
        self.itemSelectionChanged.connect(self._selection_changed)
        state.project_changed.connect(self._render_project)
        self._render_project(state.project)

    def _render_project(self, project: object | None) -> None:
        self.clear()
        if project is None:
            self.addTopLevelItem(QTreeWidgetItem(["No project open"]))
            return
        root = QTreeWidgetItem([getattr(project, "name", "Project")])
        root.setData(0, Qt.UserRole, StudioSelection.project(project))
        datasets = QTreeWidgetItem(["Datasets"])
        results = QTreeWidgetItem(["Analysis Results"])
        root.addChild(datasets)
        root.addChild(results)
        for entry in getattr(project, "dataset_entries", ()):
            item = QTreeWidgetItem([entry.display_name])
            item.setData(0, Qt.UserRole, StudioSelection.dataset(entry))
            datasets.addChild(item)
        for entry in getattr(project, "analysis_results", ()):
            item = QTreeWidgetItem([entry.display_name])
            item.setData(0, Qt.UserRole, StudioSelection.analysis_result(entry))
            results.addChild(item)
        self.addTopLevelItem(root)
        root.setExpanded(True)
        datasets.setExpanded(True)
        results.setExpanded(True)

    def _selection_changed(self) -> None:
        selected = self.selectedItems()
        self._controller.select_item(selected[0].data(0, Qt.UserRole) if selected else None)
