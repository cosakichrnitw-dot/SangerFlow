"""Regression coverage for Studio stabilization pass 1."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsSimpleTextItem,
    QPlainTextEdit,
    QPushButton,
    QToolBar,
)

from app.action_manager import ActionManager
from app.app_state import AppState
from app.selection import StudioSelection
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from widgets.inspector_panel import InspectorPanel
from widgets.metadata_presentation import show_source_filepaths_dialog
from widgets.quality_report_dock import QualityReportDock
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.dataset_viewer import DatasetViewer
from widgets.viewers.viewer_actions import ViewerAction
from widgets.viewers.viewer_context import ViewerContext
from widgets.viewers.viewer_registry import ViewerRegistry
from widgets.workspace_tabs import WorkspaceTabs
from widgets.project_summary_graph import ProjectSummaryGraph


class _ExportViewer(BaseViewer):
    def __init__(self, identifier: str) -> None:
        super().__init__(
            viewer_id=f"export-{identifier}",
            viewer_title="Export test",
            viewer_kind="test",
        )
        self._provider = _ExportActionProvider()

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._provider,)


class _ExportActionProvider:
    def actions_for(self, _viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction("dataset.export_fasta", "Export FASTA", lambda: None),
            ViewerAction("dataset.test_action", "Test", lambda: None),
        )


class _ReadQuality:
    def __init__(self, quality: tuple[int, ...]) -> None:
        self.read_id = "C13_FishF1"
        self.quality = quality
        self.sequence_length = len(quality)
        self.q20_rate = 100.0 * sum(value >= 20 for value in quality) / len(quality)
        self.q30_rate = 100.0 * sum(value >= 30 for value in quality) / len(quality)
        self.trim_length = len(quality)


class StabilizationPass1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_export_toolbar_button_is_permanent_while_its_viewer_actions_are_replaced(self) -> None:
        state = AppState()
        toolbar = QToolBar()
        manager = ActionManager(state)
        manager.attach_toolbar(toolbar)

        for index in range(8):
            state.set_active_viewer(_ExportViewer(str(index)))
            self.application.processEvents()
            action = manager._fixed_actions["export"]
            self.assertIn(action, toolbar.actions())
            self.assertTrue(action.isEnabled())
        state.set_active_viewer(None)
        self.application.processEvents()
        QCoreApplication.sendPostedEvents()

        self.assertIsNone(manager._export_toolbar_action)
        self.assertIn(manager._fixed_actions["export"], toolbar.actions())
        self.assertFalse(manager._fixed_actions["export"].isEnabled())
        self.assertEqual(manager.action_ids(), ())

    def test_closed_viewers_are_removed_and_permanent_tabs_are_not_closable(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        manager = TabManager(tabs, state)
        controller.configure_viewer_framework(
            viewer_registry=ViewerRegistry(),
            viewer_context=ViewerContext(state, controller, tab_manager=manager),
            tab_manager=manager,
        )
        viewer = _ExportViewer("one")
        manager.open_viewer(viewer, resource_key="dataset:one")

        self.assertIsNone(tabs.tabBar().tabButton(0, tabs.tabBar().ButtonPosition.RightSide))
        self.assertIsNone(tabs.tabBar().tabButton(1, tabs.tabBar().ButtonPosition.RightSide))
        self.assertTrue(manager.close_viewer(viewer.viewer_id))
        self.application.processEvents()
        QCoreApplication.sendPostedEvents()

        self.assertEqual(manager.viewer_ids(), ())
        self.assertIsNone(manager.viewer_for_resource_key("dataset:one"))
        self.assertEqual(tabs.count(), 2)

    def test_project_summary_graph_refreshes_once_per_project_change(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        graph = tabs._project_summary
        with patch.object(graph, "refresh", wraps=graph.refresh) as refresh:
            state.set_project(Project.create("project", "Project"))
            self.application.processEvents()
        self.assertEqual(refresh.call_count, 1)

    def test_project_summary_graph_coalesces_project_and_repository_changes(self) -> None:
        state = AppState()
        graph = ProjectSummaryGraph(state, ProjectController(state))
        with patch.object(graph, "refresh", wraps=graph.refresh) as refresh:
            state.set_project(Project.create("project", "Project"), repository=object())
            self.application.processEvents()
        self.assertEqual(refresh.call_count, 1)
        graph.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_project_summary_graph_destruction_cancels_pending_refresh(self) -> None:
        state = AppState()
        graph = ProjectSummaryGraph(state, ProjectController(state))
        state.set_project(Project.create("first", "First"))
        self.assertTrue(graph._refresh_timer.isActive())

        graph.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.application.processEvents()

    def test_destroyed_project_summary_graph_receives_no_later_state_callbacks(self) -> None:
        state = AppState()
        graph = ProjectSummaryGraph(state, ProjectController(state))
        graph.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

        # The direct QObject-bound connections must have been removed with the
        # graph; each state change below therefore completes without accessing
        # a deleted QGraphicsView.
        state.set_project(Project.create("second", "Second"))
        state.set_repository(object())
        self.application.processEvents()

    def test_graph_destruction_after_state_change_cancels_queued_refresh(self) -> None:
        state = AppState()
        graph = ProjectSummaryGraph(state, ProjectController(state))
        graph.deleteLater()
        state.set_project(Project.create("third", "Third"))
        state.set_repository(object())
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.application.processEvents()

    def test_project_summary_nodes_are_compact_non_overlapping_and_not_duplicated(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "raw", "A dataset name intentionally long enough to be elided in the lineage overview",
            SourceType.AB1_RAW, (("sample", "ATGC"),),
        )
        derived = SequenceDataset.from_sequence_pairs(
            "derived", "Derived consensus", SourceType.REVIEWED_CONSENSUS, (("sample", "ATGC"),),
        )
        alignment = AlignmentDataset(
            alignment_id="alignment",
            name="Derived consensus alignment",
            parent_dataset_id="derived",
            records=(AlignmentRecord("sample", "sample", "ATGC"),),
        )
        project = (
            Project.create("project", "Project")
            .add_dataset(source)
            .add_dataset(derived, parent_dataset_id="raw")
            .add_dataset(alignment, parent_dataset_id="derived")
            .add_analysis_result(
                AnalysisResult("blast", "BLAST Identification", AnalysisResultType.BLAST, "raw")
            )
        )
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        graph = tabs._project_summary
        state.set_project(project)
        self.application.processEvents()

        expected_count = project.dataset_count + project.analysis_result_count
        self.assertEqual(len(graph.node_items()), expected_count)
        for node in graph.node_items():
            text_items = [item for item in node.childItems() if isinstance(item, QGraphicsSimpleTextItem)]
            self.assertGreaterEqual(len(text_items), 3)
            previous_bottom = node.sceneBoundingRect().top()
            for item in sorted(text_items, key=lambda value: value.sceneBoundingRect().top()):
                rect = item.sceneBoundingRect()
                self.assertGreaterEqual(rect.left(), node.sceneBoundingRect().left())
                self.assertLessEqual(rect.right(), node.sceneBoundingRect().right())
                self.assertGreaterEqual(rect.top(), previous_bottom)
                self.assertLessEqual(rect.bottom(), node.sceneBoundingRect().bottom())
                previous_bottom = rect.bottom()
            self.assertTrue(node.toolTip())

        for _ in range(10):
            graph.refresh()
        self.assertEqual(len(graph.node_items()), expected_count)

    def test_viewer_and_permanent_tab_switches_leave_no_closed_viewer(self) -> None:
        """Exercise the Welcome/Summary/Viewer lifetime sequence offscreen."""

        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        manager = TabManager(tabs, state)
        controller.configure_viewer_framework(
            viewer_registry=ViewerRegistry(),
            viewer_context=ViewerContext(state, controller, tab_manager=manager),
            tab_manager=manager,
        )
        state.set_project(Project.create("first", "First"))
        viewer = _ExportViewer("first")
        manager.open_viewer(viewer, resource_key="dataset:first")
        for index in (0, 1, 2, 0, 1, 2, 0):
            tabs.setCurrentIndex(index)
            self.application.processEvents()
        self.assertTrue(manager.close_viewer(viewer.viewer_id))
        self.assertEqual(manager.viewer_ids(), ())

        viewer = _ExportViewer("reopened")
        manager.open_viewer(viewer, resource_key="dataset:reopened")
        controller.close_project()
        self.application.processEvents()
        self.assertIsNone(state.current_project)
        self.assertEqual(manager.viewer_ids(), ())
        state.set_project(Project.create("second", "Second"))
        self.assertEqual(tabs.currentIndex(), 1)

    def test_metadata_paths_are_bounded_but_dialog_retains_all_values(self) -> None:
        paths = tuple(f"/very/long/root/{index}/" + "nested/" * 35 + "sample.ab1" for index in range(10))
        dataset = SequenceDataset(
            dataset_id="raw",
            name="Raw AB1",
            source_type=SourceType.AB1_RAW,
            records=(SequenceRecord("C13", "ATGC"),),
            metadata={"source_filepaths": paths, "project_note": "x" * 800},
        )
        viewer = DatasetViewer(dataset)
        viewer.show()
        self.application.processEvents()

        self.assertIn("source_filepaths=10 files", viewer._metadata_value.text())
        self.assertLess(viewer.minimumSizeHint().width(), 1200)
        self.assertTrue(viewer._source_files_button.isVisible())
        with patch.object(QDialog, "exec", return_value=0):
            dialog = show_source_filepaths_dialog(viewer, paths)
        value = dialog.findChild(QPlainTextEdit)
        self.assertIsNotNone(value)
        self.assertEqual(value.toPlainText().splitlines(), list(paths))
        viewer.close()

    def test_inspector_uses_the_same_bounded_source_file_summary(self) -> None:
        paths = tuple(f"/absolute/{index}/" + "very-long-segment/" * 30 + "read.ab1" for index in range(11))
        dataset = SequenceDataset(
            dataset_id="raw",
            name="Raw AB1",
            source_type=SourceType.AB1_RAW,
            records=(SequenceRecord("C13", "ATGC"),),
            metadata={"source_filepaths": paths},
        )
        project = Project.create("project", "Project").add_dataset(dataset)
        state = AppState()
        inspector = InspectorPanel(state)
        state.set_selected_item(StudioSelection.dataset(project.get_entry("raw")))
        inspector.show()
        self.application.processEvents()

        labels = [label.text() for label in inspector.findChildren(QPushButton)]
        self.assertIn("11 files  [Show…]", labels)
        values = [label.text() for label in inspector.findChildren(type(inspector._title))]
        self.assertTrue(any("source_filepaths=11 files" in value for value in values))
        self.assertLess(inspector.minimumSizeHint().width(), 1200)
        inspector.close()

    def test_dataset_hq_percent_matches_quality_dock_q40_and_handles_empty_source(self) -> None:
        # 3 / 4 bases meet Q40, including the exact Q40 boundary.
        source = _ReadQuality((40, 39, 41, 40))
        dataset = SequenceDataset(
            dataset_id="raw",
            name="Raw AB1",
            source_type=SourceType.AB1_RAW,
            records=(
                SequenceRecord("C13", "ATGC", source_reference=source),
                SequenceRecord("no-source", "ATGC"),
            ),
        )
        viewer = DatasetViewer(dataset)
        self.assertEqual(viewer._records_table.horizontalHeaderItem(3).text(), "HQ%")
        self.assertEqual(viewer._records_table.item(0, 3).text(), "75.0%")
        self.assertEqual(viewer._records_table.item(1, 3).text(), "—")

        from app.read_visibility import ReadVisibilityManager

        dock = QualityReportDock(visibility_manager=ReadVisibilityManager())
        dock.set_reads((source,), source_key="raw")
        self.assertEqual(dock._table.item(0, 5).text(), "75.0")
        viewer.close()
        dock.close()

    def test_c13_q40_fixture_rounds_to_the_geneious_hq_value(self) -> None:
        source = _ReadQuality((40,) * 7463 + (39,) * 2537)
        dataset = SequenceDataset(
            dataset_id="c13",
            name="C13",
            source_type=SourceType.AB1_RAW,
            records=(SequenceRecord("C13_FishF1", "A" * 10000, source_reference=source),),
        )
        viewer = DatasetViewer(dataset)
        self.assertEqual(viewer._records_table.item(0, 3).text(), "74.6%")
        viewer.close()
