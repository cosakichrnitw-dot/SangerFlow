"""Checks for Dataset Viewer routing and display."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.app_state import AppState
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from PySide6.QtWidgets import QApplication, QToolBar
from views.project_view import ProjectView
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers import ViewerContext
from widgets.viewers.alignment_viewer import AlignmentViewer, create_alignment_viewer
from widgets.viewers.dataset_viewer import DatasetViewer
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.viewer_registry import ViewerRegistry
from widgets.workspace_tabs import WorkspaceTabs


class DatasetViewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_sequence_dataset_viewer_displays_summary_and_records(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )

        viewer = DatasetViewer(dataset)

        self.assertEqual(viewer.viewer_title, "COI Imported")
        self.assertEqual(viewer.viewer_kind, "dataset")
        self.assertEqual(viewer._name_value.text(), "COI Imported")
        self.assertEqual(viewer._type_value.text(), "IMPORTED_FASTA")
        self.assertEqual(viewer._count_value.text(), "2")
        self.assertEqual(viewer._records_table.rowCount(), 2)
        self.assertEqual(viewer._records_table.item(0, 0).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 1).text(), "4")

    def test_alignment_dataset_viewer_displays_alignment_records(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )

        viewer = DatasetViewer(alignment)

        self.assertEqual(viewer.viewer_title, "COI Alignment")
        self.assertEqual(viewer._type_value.text(), "AlignmentDataset")
        self.assertEqual(viewer._count_value.text(), "2")
        self.assertEqual(viewer._records_table.item(0, 0).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 2).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 3).text(), "ATG-C")

    def test_dataset_viewer_action_opens_alignment_viewer_for_alignment_dataset(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        tab_manager = TabManager(tabs, state)
        context = ViewerContext(state, controller, tab_manager=tab_manager)
        dataset_viewer = DatasetViewer(alignment, context)
        tab_manager.open_viewer(dataset_viewer, resource_key="dataset:coi-alignment")
        from app.action_manager import ActionManager

        action_manager = ActionManager(state)
        toolbar = QToolBar()
        action_manager.attach_toolbar(toolbar)
        state.set_active_viewer(dataset_viewer)
        self.application.processEvents()

        action = action_manager.action("dataset.open_alignment_viewer")
        self.assertIsNotNone(action)
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.application.processEvents()

        self.assertIsInstance(tabs.widget(3), AlignmentViewer)
        action.trigger()
        self.application.processEvents()
        self.assertEqual(tabs.count(), 4)

    def test_project_explorer_selection_opens_dataset_viewer_tab(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        dataset_item = explorer.topLevelItem(0).child(0).child(0)

        explorer.setCurrentItem(dataset_item)
        self.application.processEvents()

        self.assertEqual(tabs.count(), 3)
        self.assertEqual(tabs.tabText(2), "COI Imported")
        self.assertIsInstance(tabs.widget(2), DatasetViewer)
        self.assertIs(state.active_viewer, tabs.widget(2))
        self.assertIs(state.selected_item.payload.dataset, dataset)
        self.assertEqual(view.tab_manager.viewer_ids(), ("dataset-viewer-coi-import",))

        self.assertTrue(view.tab_manager.close_viewer("dataset-viewer-coi-import"))
        self.assertEqual(tabs.count(), 2)

    def test_alignment_dataset_routes_to_alignment_viewer_by_default(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        registry = ViewerRegistry()
        registry.register_model_viewer(
            AlignmentDataset,
            viewer_key="alignment-dataset-viewer",
            label="Alignment Viewer",
            factory=create_alignment_viewer,
            default=True,
        )

        viewer = registry.create_viewer_for(alignment, ViewerContext(state, controller))

        self.assertIsInstance(viewer, AlignmentViewer)
        self.assertEqual(viewer.viewer_id, "alignment-viewer-coi-alignment")

    def test_project_explorer_opens_alignment_dataset_in_alignment_viewer(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
            ),
        )
        project = (
            Project.create("project-1", "Project 1")
            .add_dataset(source)
            .add_dataset(
                alignment,
                parent_dataset_id="coi-import",
            )
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        alignment_item = explorer.topLevelItem(0).child(0).child(1)

        explorer.setCurrentItem(alignment_item)
        self.application.processEvents()

        self.assertEqual(tabs.count(), 3)
        self.assertIsInstance(tabs.widget(2), AlignmentViewer)
        self.assertEqual(tabs.tabText(2), "Alignment: COI Alignment")

    def test_alignment_viewer_shows_gaps_and_selects_cell_and_column(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        viewer = AlignmentViewer(alignment)

        selected = viewer.select_alignment_cell(0, 3)
        viewer.select_column(2)

        self.assertEqual(viewer._table.item(1, 4).text(), "-")
        self.assertEqual(selected, ("IK345", 4, "-"))
        self.assertEqual(viewer.selected_column, 3)

    def test_alignment_viewer_action_opens_alignment_chromatogram_viewer(self) -> None:
        from core.models import SangerRead
        from core.trimming import trim_sequence

        def read(filename: str, sequence: str) -> SangerRead:
            trace_length = max(40, len(sequence) * 10)
            return trim_sequence(
                SangerRead(
                    filename=filename,
                    sequence=sequence,
                    quality=[35 for _ in sequence],
                    traces={base: [10 for _ in range(trace_length)] for base in "ACGT"},
                    base_positions=[5 + index * 8 for index in range(len(sequence))],
                    average_quality=35.0,
                )
            )

        reads = (read("IK345", "ATGC"), read("IK346", "ATGT"))
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGC"),
                AlignmentRecord("IK346", "IK346", "ATGT"),
            ),
            metadata={"source_reads": reads},
        )
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        tab_manager = TabManager(tabs, state)
        context = ViewerContext(state, controller, tab_manager=tab_manager)
        viewer = AlignmentViewer(alignment, context=context)
        toolbar = QToolBar()
        from app.action_manager import ActionManager

        action_manager = ActionManager(state)
        action_manager.attach_toolbar(toolbar)

        tab_manager.open_viewer(viewer, resource_key="alignment:coi-alignment")
        self.application.processEvents()
        state.set_active_viewer(viewer)

        action = action_manager.action("alignment.review_chromatograms")
        self.assertIsNotNone(action)
        action.trigger()
        self.application.processEvents()

        self.assertIsInstance(tabs.widget(3), AlignmentChromatogramViewer)
        action.trigger()
        self.application.processEvents()
        self.assertEqual(tabs.count(), 4)

    def test_dataset_viewer_action_opens_placeholder_viewer(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        explorer.setCurrentItem(explorer.topLevelItem(0).child(0).child(0))
        self.application.processEvents()

        dataset_viewer = tabs.widget(2)
        action = view.action_manager.action("dataset.open_placeholder_viewer")

        self.assertIsNotNone(action)
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.application.processEvents()

        self.assertEqual(tabs.count(), 4)
        self.assertIsInstance(tabs.widget(3), PlaceholderViewer)
        self.assertEqual(tabs.tabText(3), "Placeholder: COI Imported")
        self.assertEqual(
            view.tab_manager.viewer_ids(),
            ("dataset-viewer-coi-import", "placeholder-viewer-coi-import"),
        )
