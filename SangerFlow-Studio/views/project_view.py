"""Composite project workspace view."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSplitter

from app.action_manager import ActionManager
from app.app_state import AppState
from app.dock_manager import DockManager
from app.read_visibility import ReadVisibilityManager
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.analysis_result import AnalysisResultType
from core.alignment_dataset import AlignmentDataset
from core.sequence_dataset import SequenceDataset
from widgets.inspector_panel import InspectorPanel
from widgets.project_explorer import ProjectExplorer
from widgets.viewers import (
    ViewerContext,
    ViewerRegistry,
    create_alignment_viewer,
    create_blast_result_viewer,
    create_bold_result_viewer,
    create_dataset_viewer,
)
from widgets.workspace_tabs import WorkspaceTabs


class ProjectView(QSplitter):
    """Resizable Explorer / Workspace / Inspector composition."""

    project_explorer_visibility_changed = Signal(bool)

    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._project_explorer = ProjectExplorer(state, controller)
        self.addWidget(self._project_explorer)
        self._workspace_tabs = WorkspaceTabs(state, controller)
        self.tab_manager = TabManager(self._workspace_tabs, state)
        self.action_manager = ActionManager(state)
        self.read_visibility_manager = ReadVisibilityManager()
        self.dock_manager = DockManager(self.read_visibility_manager)
        self.viewer_registry = ViewerRegistry()
        self._register_default_viewers()
        self.viewer_context = ViewerContext(
            state,
            controller,
            tab_manager=self.tab_manager,
            action_manager=self.action_manager,
            dock_manager=self.dock_manager,
            read_visibility_manager=self.read_visibility_manager,
        )
        controller.configure_viewer_framework(
            viewer_registry=self.viewer_registry,
            viewer_context=self.viewer_context,
            tab_manager=self.tab_manager,
        )
        self.addWidget(self._workspace_tabs)
        self._inspector_panel = InspectorPanel(state)
        self.addWidget(self._inspector_panel)
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 4)
        self.setStretchFactor(2, 1)
        self.setSizes([260, 820, 280])

    @property
    def project_explorer_visible(self) -> bool:
        return self._project_explorer.content_visible

    def set_project_explorer_visibility_action(self, action: object) -> None:
        self._project_explorer.set_visibility_action(action)

    @property
    def inspector_visible(self) -> bool:
        return self._inspector_panel.isVisible()

    def set_project_explorer_visible(self, visible: bool) -> None:
        self._project_explorer.set_content_visible(bool(visible))
        sizes = self.sizes()
        if visible:
            self.setSizes([260, max(1, sizes[1]), max(1, sizes[2])])
        else:
            self.setSizes([28, max(1, sizes[1]), max(1, sizes[2])])
        self.project_explorer_visibility_changed.emit(bool(visible))

    def set_inspector_visible(self, visible: bool) -> None:
        self._inspector_panel.setVisible(bool(visible))
        self.dock_manager.set_docks_visible(bool(visible))

    def _register_default_viewers(self) -> None:
        self.viewer_registry.register_model_viewer(
            SequenceDataset,
            viewer_key="sequence-dataset-viewer",
            label="Dataset Viewer",
            factory=create_dataset_viewer,
            default=True,
        )
        self.viewer_registry.register_model_viewer(
            AlignmentDataset,
            viewer_key="alignment-dataset-viewer",
            label="Sequence Editor — Aligned",
            factory=create_alignment_viewer,
            default=True,
        )
        self.viewer_registry.register_result_viewer(
            AnalysisResultType.BLAST,
            viewer_key="blast-result-viewer",
            label="BLAST Result Viewer",
            factory=create_blast_result_viewer,
            default=True,
        )
        self.viewer_registry.register_result_viewer(
            AnalysisResultType.BOLD,
            viewer_key="bold-result-viewer",
            label="BOLD Result Viewer",
            factory=create_bold_result_viewer,
            default=True,
        )
