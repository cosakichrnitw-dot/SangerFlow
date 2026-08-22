"""Phase 2E DAG graph and canonical Explorer representation coverage."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsSimpleTextItem, QTreeWidgetItem

from app.app_state import AppState
from app.selection import SelectionKind, StudioSelection
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.lineage import LineageRelation, LineageRelationType, LineageSourceKind, RecordRef
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import Project, RevisionOperation
from core.sequence_dataset import SequenceDataset, SourceType
from widgets.project_explorer import ProjectExplorer
from widgets.project_summary_graph import ProjectSummaryGraph


def _dataset(identifier: str) -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        identifier,
        identifier,
        SourceType.REVIEWED_CONSENSUS,
        ((f"{identifier}_record", "ATGC"),),
    )


def _dag_project() -> Project:
    first, second, third = (_dataset("Run_01"), _dataset("Run_02"), _dataset("Run_03"))
    final = _dataset("Final_COI")
    project = Project.create("project", "Project").add_dataset(first).add_dataset(second).add_dataset(third)
    project = project.add_dataset(
        final,
        lineage_relations=(
            LineageRelation(LineageSourceKind.DATASET, "Run_01", LineageRelationType.MERGED_FROM_DATASETS),
            LineageRelation(LineageSourceKind.DATASET, "Run_02", LineageRelationType.MERGED_FROM_DATASETS),
            LineageRelation(LineageSourceKind.DATASET, "Run_03", LineageRelationType.MERGED_FROM_DATASETS),
        ),
    )
    result = AnalysisResult("blast", "BLAST", AnalysisResultType.BLAST, "Final_COI")
    project = project.add_analysis_result(result)
    selected = _dataset("BLAST_Selected")
    return project.add_dataset(
        selected,
        lineage_relations=(
            LineageRelation(LineageSourceKind.DATASET, "Final_COI", LineageRelationType.SUBSET_FROM_DATASET),
            LineageRelation(LineageSourceKind.ANALYSIS_RESULT, "blast", LineageRelationType.SELECTED_FROM_BLAST),
        ),
    )


class _Controller:
    def __init__(self) -> None:
        self.selected: list[object] = []
        self.open_count = 0

    def select_item(self, selection: object, *, open_viewer: bool = True) -> None:
        self.selected.append(selection)

    def open_selected_item(self) -> None:
        self.open_count += 1


class MultiParentLineageVisualizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.state = AppState()
        self.controller = _Controller()
        self.project = _dag_project()
        self.graph = ProjectSummaryGraph(self.state, self.controller)
        self.explorer = ProjectExplorer(self.state, self.controller)
        self.state.set_project(self.project)
        self.application.processEvents()

    def tearDown(self) -> None:
        self.graph.close()
        self.explorer.close()

    def test_graph_uses_one_canonical_node_and_all_formal_edges(self) -> None:
        self.assertEqual(len(self.graph.node_items()), 6)
        edges = tuple(item.data(0) for item in self.graph.edge_items())
        edge_keys = {(edge.source_identifier, edge.target_identifier, edge.relation_type) for edge in edges}
        self.assertIn(("dataset:Run_01", "dataset:Final_COI", "MERGED_FROM_DATASETS"), edge_keys)
        self.assertIn(("dataset:Run_02", "dataset:Final_COI", "MERGED_FROM_DATASETS"), edge_keys)
        self.assertIn(("dataset:Run_03", "dataset:Final_COI", "MERGED_FROM_DATASETS"), edge_keys)
        self.assertIn(("dataset:Final_COI", "result:blast", "ANALYSIS_RESULT_PARENT"), edge_keys)
        self.assertIn(("dataset:Final_COI", "dataset:BLAST_Selected", "SUBSET_FROM_DATASET"), edge_keys)
        self.assertIn(("result:blast", "dataset:BLAST_Selected", "SELECTED_FROM_BLAST"), edge_keys)
        self.assertTrue(all(item.toolTip() for item in self.graph.edge_items()))

    def test_revision_edges_are_distinct_from_scientific_lineage_edges(self) -> None:
        source = _dataset("Test_E_1")
        first = AlignmentDataset(
            alignment_id="test-e-alignment-r1",
            name="Test_E_1 alignment",
            parent_dataset_id=source.dataset_id,
            records=(AlignmentRecord("sample", "sample", "ATGC"),),
            metadata={"alignment_method": "MAFFT"},
        )
        second = AlignmentDataset(
            alignment_id="test-e-alignment-r2",
            name="Test_E_1 alignment",
            parent_dataset_id=source.dataset_id,
            records=(AlignmentRecord("sample", "sample", "ATGN"),),
            metadata={"alignment_method": "MAFFT"},
        )
        project = Project.create("revision-project", "Revision Project").add_dataset(source)
        project = project.add_dataset(first, parent_dataset_id=source.dataset_id)
        project = project.add_dataset_revision(
            first.alignment_id,
            second,
            operation=RevisionOperation.ALIGNMENT_EDIT,
            parent_dataset_id=source.dataset_id,
            lineage_relations=project.get_entry(first.alignment_id).lineage_relations,
        )
        self.state.set_project(project)
        self.application.processEvents()

        edges = tuple(item.data(0) for item in self.graph.edge_items())
        scientific = {
            (edge.source_identifier, edge.target_identifier)
            for edge in edges
            if edge.edge_kind == "scientific"
        }
        revision = next(edge for edge in edges if edge.edge_kind == "revision")
        self.assertIn(("dataset:Test_E_1", "dataset:test-e-alignment-r1"), scientific)
        self.assertNotIn(("dataset:Test_E_1", "dataset:test-e-alignment-r2"), scientific)
        self.assertEqual(
            (revision.source_identifier, revision.target_identifier, revision.display_label),
            ("dataset:test-e-alignment-r1", "dataset:test-e-alignment-r2", "edited revision"),
        )
        self.assertEqual(revision.relation_type, "REVISION")
        revision_two_node = next(
            item for item in self.graph.node_items()
            if item.data(0).payload.dataset.alignment_id == second.alignment_id
        )
        node_text = "\n".join(
            child.text() for child in revision_two_node.childItems()
            if isinstance(child, QGraphicsSimpleTextItem)
        )
        self.assertIn("r2 [CURRENT]", node_text)

    def test_graph_navigation_supports_zoom_reset_and_fit(self) -> None:
        self.graph.resize(320, 200)
        baseline = self.graph.transform().m11()
        self.graph.zoom_in()
        self.assertGreater(self.graph.transform().m11(), baseline)
        self.graph.zoom_out()
        self.graph.reset_zoom()
        self.assertAlmostEqual(self.graph.transform().m11(), 1.0)
        self.graph.fit_all()
        self.assertGreater(self.graph.sceneRect().width(), 0)
        self.assertGreaterEqual(self.graph.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(self.graph.verticalScrollBar().maximum(), 0)

    def test_graph_zoom_back_restores_prior_view_and_accepts_pinch_path(self) -> None:
        baseline = self.graph.transform().m11()
        self.graph.zoom_in()
        self.assertTrue(self.graph.zoom_back())
        self.assertAlmostEqual(self.graph.transform().m11(), baseline)

        class _Pinch:
            def __init__(self) -> None:
                self.accepted = False

            @staticmethod
            def gestureType():
                return Qt.NativeGestureType.ZoomNativeGesture

            @staticmethod
            def value():
                return 0.2

            def accept(self) -> None:
                self.accepted = True

        pinch = _Pinch()
        self.graph.nativeGestureEvent(pinch)
        self.assertTrue(pinch.accepted)
        self.assertGreater(self.graph.transform().m11(), baseline)

    def test_graph_zoom_is_bounded_and_viewport_pinch_path_updates_same_transform(self) -> None:
        for _ in range(80):
            self.graph.zoom_in()
        self.assertLessEqual(self.graph.transform().m11(), 4.0)
        for _ in range(160):
            self.graph.zoom_out()
        self.assertGreaterEqual(self.graph.transform().m11(), 0.35)

        class _Pinch:
            def state(self):
                return Qt.GestureState.GestureStarted

            @staticmethod
            def totalScaleFactor():
                return 1.1

        class _GestureEvent:
            accepted = False

            @staticmethod
            def gesture(_type):
                return _Pinch()

            def accept(self, _gesture):
                self.accepted = True

        event = _GestureEvent()
        before = self.graph.transform().m11()
        self.assertTrue(self.graph._handle_pinch_gesture(event))
        self.assertTrue(event.accepted)
        self.assertGreater(self.graph.transform().m11(), before)

    def test_graph_click_and_double_click_delegate_to_controller(self) -> None:
        self.graph.resize(1000, 600)
        self.graph.show()
        self.application.processEvents()
        node = next(
            node
            for node in self.graph.node_items()
            if node.data(0).object_id == "Final_COI"
        )
        point = self.graph.mapFromScene(node.sceneBoundingRect().center())
        QTest.mouseClick(self.graph.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.mouseDClick(self.graph.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(any(getattr(item, "object_id", None) == "Final_COI" for item in self.controller.selected))
        self.assertGreaterEqual(self.controller.open_count, 1)

    def test_explorer_is_a_working_view_while_graph_retains_dag_provenance(self) -> None:
        root = self.explorer.topLevelItem(0)
        self.assertEqual(tuple(root.child(index).text(0) for index in range(root.childCount())), (
            "Working Datasets", "Alignments", "Results", "History", "Archived"
        ))
        working = root.child(0)
        self.assertEqual(_count_items(working, "Final_COI"), 1)
        results = root.child(2)
        blast = _find_child(results, "BLAST")
        self.assertIsNotNone(blast)
        self.explorer._item_double_clicked(blast, 0)
        self.assertEqual(self.controller.open_count, 1)

    def test_explorer_search_keeps_alias_context_and_refresh_does_not_duplicate_nodes(self) -> None:
        self.explorer._search.setText("Run_03")
        root = self.explorer.topLevelItem(0)
        final_item = _find_item(root, "Final_COI")
        self.assertFalse(final_item.isHidden())
        self.explorer._search.clear()
        for _ in range(10):
            self.graph.refresh()
        self.assertEqual(len(self.graph.node_items()), 6)

    def test_project_rename_and_remove_refresh_canonical_graph_and_explorer(self) -> None:
        renamed = self.project.rename_dataset("Run_01", "Renamed Run 01")
        self.state.replace_project(renamed)
        self.application.processEvents()
        root = self.explorer.topLevelItem(0)
        self.assertIsNotNone(_find_item(root, "Renamed Run 01"))
        self.assertEqual(len(self.graph.node_items()), 6)

        updated = renamed.remove_dataset("BLAST_Selected")
        self.state.replace_project(updated)
        self.application.processEvents()
        self.assertEqual(len(self.graph.node_items()), 5)
        self.assertIsNone(_find_item(self.explorer.topLevelItem(0), "BLAST_Selected"))


def _find_item(root: QTreeWidgetItem, label: str) -> QTreeWidgetItem | None:
    if root.text(0) == label:
        return root
    for index in range(root.childCount()):
        found = _find_item(root.child(index), label)
        if found is not None:
            return found
    return None


def _find_child(parent: QTreeWidgetItem | None, label: str) -> QTreeWidgetItem | None:
    if parent is None:
        return None
    return next((parent.child(index) for index in range(parent.childCount()) if parent.child(index).text(0) == label), None)


def _count_items(root: QTreeWidgetItem, label: str) -> int:
    return int(root.text(0) == label) + sum(_count_items(root.child(index), label) for index in range(root.childCount()))


if __name__ == "__main__":
    unittest.main()
