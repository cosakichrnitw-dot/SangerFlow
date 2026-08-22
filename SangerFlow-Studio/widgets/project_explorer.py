"""Working-view Project navigation with separate immutable revision history."""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.app_state import AppState
from app.icon_registry import studio_icon
from app.gui_thread import assert_main_gui_thread
from app.selection import StudioSelection
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset
from core.project import Project, ProjectDatasetEntry, RevisionState
from core.sequence_dataset import SequenceDataset


class ProjectExplorer(QWidget):
    """Present current work, immutable history, and archives as distinct views.

    The Explorer deliberately does *not* reproduce the scientific provenance
    graph.  Project Summary owns that responsibility; this widget is a concise
    operational navigation surface.
    """

    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._state = state
        self._controller = controller
        self._tree = QTreeWidget()
        self._content_visible = True
        self._tree.setHeaderLabels(["Project Explorer"])
        self._tree.itemSelectionChanged.connect(self._selection_changed)
        self._tree.itemDoubleClicked.connect(self._item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search Project...")
        self._search.textChanged.connect(self._apply_filter)
        self._visibility_button = QToolButton()
        self._visibility_button.setObjectName("projectExplorerVisibilityButton")
        self._visibility_button.setToolTip("Show or hide Project Explorer")
        # The control is embedded into the normal search header while the
        # Explorer is visible.  It moves to this tiny rail only while the
        # content is collapsed, leaving a reliable restoration affordance
        # without a permanent, visually heavy sidebar stripe.
        self._rail = QWidget()
        self._rail.setObjectName("projectExplorerToggleRail")
        self._rail.setFixedWidth(22)
        self._rail_layout = QVBoxLayout(self._rail)
        self._rail_layout.setContentsMargins(0, 0, 0, 0)
        self._rail_layout.addStretch(1)
        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self._header = QHBoxLayout()
        self._header.setContentsMargins(0, 0, 0, 0)
        self._header.setSpacing(2)
        self._header.addWidget(self._visibility_button)
        self._header.addWidget(self._search, 1)
        content_layout.addLayout(self._header)
        content_layout.addWidget(self._tree, 1)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._rail)
        layout.addWidget(self._content, 1)
        self._rail.setVisible(False)
        state.project_changed.connect(self._render_project)
        self._render_project(state.project)

    # Lightweight compatibility delegation for existing integrations/tests.
    def topLevelItem(self, index: int) -> QTreeWidgetItem | None:  # noqa: N802
        return self._tree.topLevelItem(index)

    def setCurrentItem(self, item: QTreeWidgetItem | None) -> None:  # noqa: N802
        self._tree.setCurrentItem(item)

    @property
    def tree(self) -> QTreeWidget:
        return self._tree

    def set_visibility_action(self, action: object) -> None:
        """Share the View-menu QAction with the navigation header button."""

        if hasattr(action, "triggered"):
            self._visibility_button.setDefaultAction(action)

    def set_content_visible(self, visible: bool) -> None:
        """Collapse to a small top-left recovery control, not an empty pane."""

        self._content_visible = bool(visible)
        self._move_visibility_control(to_rail=not self._content_visible)
        self._content.setVisible(self._content_visible)
        if self._content_visible:
            self.setMinimumWidth(180)
            self.setMaximumWidth(16_777_215)
        else:
            self.setMinimumWidth(28)
            self.setMaximumWidth(28)

    @property
    def content_visible(self) -> bool:
        return self._content_visible

    def _move_visibility_control(self, *, to_rail: bool) -> None:
        """Keep exactly one shared QAction presentation at a stable location."""

        if to_rail:
            self._header.removeWidget(self._visibility_button)
            self._rail_layout.insertWidget(0, self._visibility_button, 0, Qt.AlignmentFlag.AlignTop)
            self._rail.setVisible(True)
        else:
            self._rail_layout.removeWidget(self._visibility_button)
            self._header.insertWidget(0, self._visibility_button)
            self._rail.setVisible(False)

    def _render_project(self, project: object | None) -> None:
        assert_main_gui_thread("ProjectExplorer._render_project/QTreeWidget")
        self._tree.clear()
        if not isinstance(project, Project):
            self._tree.addTopLevelItem(QTreeWidgetItem(["No project open"]))
            return

        root = QTreeWidgetItem([project.name])
        root.setData(0, Qt.ItemDataRole.UserRole, StudioSelection.project(project))
        working = _section("Working Datasets")
        alignments = _section("Alignments")
        results = _section("Results")
        history = _section("History")
        archived = _section("Archived")
        for section in (working, alignments, results, history, archived):
            root.addChild(section)

        for entry in project.current_dataset_entries():
            item = _dataset_item(entry)
            if isinstance(entry.dataset, AlignmentDataset):
                alignments.addChild(item)
            elif isinstance(entry.dataset, SequenceDataset):
                working.addChild(item)

        # Result entries intentionally remain visible even if their exact
        # source Dataset revision has been superseded or archived.
        for entry in project.analysis_results:
            item = QTreeWidgetItem([entry.display_name])
            item.setData(0, Qt.ItemDataRole.UserRole, StudioSelection.analysis_result(entry))
            results.addChild(item)

        for logical_id in project.logical_dataset_ids:
            revisions = project.dataset_revision_history(logical_id)
            if not revisions:
                continue
            family = QTreeWidgetItem([revisions[-1].display_name])
            family.setData(0, Qt.ItemDataRole.UserRole, None)
            for entry in revisions:
                operation = entry.revision_operation.value.replace("_", " ").title()
                label = f"r{entry.revision_number} — {operation} ({entry.revision_state.value.title()})"
                revision = QTreeWidgetItem([label])
                revision.setToolTip(0, _dataset_id(entry.dataset))
                revision.setData(0, Qt.ItemDataRole.UserRole, StudioSelection.dataset(entry))
                family.addChild(revision)
            history.addChild(family)

        for entry in project.archived_dataset_entries():
            archived.addChild(_dataset_item(entry))

        self._tree.addTopLevelItem(root)
        root.setExpanded(True)
        for section in (working, alignments, results, archived):
            section.setExpanded(True)
        self._apply_filter(self._search.text())

    def _apply_filter(self, value: str) -> None:
        query = value.strip().casefold()

        def visit(item: QTreeWidgetItem) -> bool:
            child_match = any(visit(item.child(index)) for index in range(item.childCount()))
            own_match = not query or query in item.text(0).casefold()
            visible = own_match or child_match
            item.setHidden(not visible)
            return visible

        for index in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(index))

    def _selection_changed(self) -> None:
        assert_main_gui_thread("ProjectExplorer._selection_changed/QTreeWidget")
        selected = self._tree.selectedItems()
        self._controller.select_item(selected[0].data(0, Qt.ItemDataRole.UserRole) if selected else None)

    def _item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        selection = item.data(0, Qt.ItemDataRole.UserRole)
        if selection is None:
            return
        self._controller.select_item(selection, open_viewer=False)
        self._controller.open_selected_item()

    def _show_context_menu(self, position: QPoint) -> None:
        item = self._tree.itemAt(position)
        if item is None:
            return
        selection = item.data(0, Qt.ItemDataRole.UserRole)
        if selection is None or getattr(selection, "kind", None) != "dataset":
            return
        entry = getattr(selection, "value", None)
        if not isinstance(entry, ProjectDatasetEntry):
            return
        menu = QMenu(self)
        open_action = menu.addAction(studio_icon("sequence_editor"), "Open")
        open_action.triggered.connect(lambda: self._open_entry(entry))
        rename_action = menu.addAction(studio_icon("rename"), "Rename Dataset…")
        rename_action.triggered.connect(lambda: self._rename_entry(entry))
        menu.addSeparator()
        if entry.revision_state is RevisionState.ARCHIVED:
            restore_action = menu.addAction(studio_icon("restore"), "Restore")
            restore_action.triggered.connect(lambda: self._restore_entry(entry))
        elif self._state.current_project and self._state.current_project.is_current_revision(_dataset_id(entry.dataset)):
            archive_action = menu.addAction(studio_icon("archive"), "Archive")
            archive_action.triggered.connect(lambda: self._archive_entry(entry))
        delete_action = menu.addAction(studio_icon("delete"), "Delete from Project…")
        delete_action.triggered.connect(lambda: self._delete_entry(entry))
        menu.exec(self._tree.viewport().mapToGlobal(position))

    def _open_entry(self, entry: ProjectDatasetEntry) -> None:
        self._controller.select_item(StudioSelection.dataset(entry), open_viewer=False)
        self._controller.open_selected_item()

    def _rename_entry(self, entry: ProjectDatasetEntry) -> None:
        name, accepted = QInputDialog.getText(
            self, "Rename Dataset", "Dataset display name:", text=entry.display_name
        )
        if not accepted or not name.strip():
            return
        try:
            self._controller.rename_dataset(_dataset_id(entry.dataset), name.strip())
        except ValueError as error:
            QMessageBox.warning(self, "Rename Dataset", str(error))

    def _archive_entry(self, entry: ProjectDatasetEntry) -> None:
        try:
            self._controller.archive_logical_dataset(entry.logical_id)
        except ValueError as error:
            QMessageBox.warning(self, "Archive Dataset", str(error))

    def _restore_entry(self, entry: ProjectDatasetEntry) -> None:
        try:
            self._controller.restore_logical_dataset(entry.logical_id)
        except ValueError as error:
            QMessageBox.warning(self, "Restore Dataset", str(error))

    def _delete_entry(self, entry: ProjectDatasetEntry) -> None:
        name = entry.display_name
        dependencies = self._controller.dataset_delete_dependencies(_dataset_id(entry.dataset))
        if dependencies:
            QMessageBox.information(
                self,
                f"Cannot delete “{name}”.",
                "This dataset is used by:\n" + "\n".join(f"- {label}" for label in dependencies)
                + "\n\nArchive it instead?",
            )
            return
        response = QMessageBox.question(
            self,
            "Delete from Project",
            f"Delete “{name}” from this Project? This only succeeds for a safe leaf Dataset.",
            QMessageBox.StandardButton.Delete | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response is not QMessageBox.StandardButton.Delete:
            return
        try:
            self._controller.remove_dataset(_dataset_id(entry.dataset))
        except ValueError as error:
            QMessageBox.warning(self, f"Cannot delete “{name}”.", str(error))


def _section(label: str) -> QTreeWidgetItem:
    item = QTreeWidgetItem([label])
    item.setData(0, Qt.ItemDataRole.UserRole, None)
    return item


def _dataset_item(entry: ProjectDatasetEntry) -> QTreeWidgetItem:
    item = QTreeWidgetItem([entry.display_name])
    item.setToolTip(0, _dataset_id(entry.dataset))
    item.setData(0, Qt.ItemDataRole.UserRole, StudioSelection.dataset(entry))
    return item


def _dataset_id(dataset: object) -> str:
    return str(getattr(dataset, "dataset_id", None) or getattr(dataset, "alignment_id", ""))
