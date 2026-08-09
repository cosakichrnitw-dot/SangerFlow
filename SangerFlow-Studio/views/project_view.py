"""Composite project workspace view."""

from PySide6.QtWidgets import QSplitter

from app.action_manager import ActionManager
from app.app_state import AppState
from app.dock_manager import DockManager
from app.read_visibility import ReadVisibilityManager
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset
from core.sequence_dataset import SequenceDataset
from widgets.inspector_panel import InspectorPanel
from widgets.project_explorer import ProjectExplorer
from widgets.viewers import (
    ViewerContext,
    ViewerRegistry,
    create_alignment_viewer,
    create_dataset_viewer,
)
from widgets.workspace_tabs import WorkspaceTabs


class ProjectView(QSplitter):
    """Resizable Explorer / Workspace / Inspector composition."""

    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self.addWidget(ProjectExplorer(state, controller))
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
        self.addWidget(InspectorPanel(state))
        self.setStretchFactor(0, 1)
        self.setStretchFactor(1, 4)
        self.setStretchFactor(2, 1)
        self.setSizes([260, 820, 280])

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
            label="Alignment Viewer",
            factory=create_alignment_viewer,
            default=True,
        )
