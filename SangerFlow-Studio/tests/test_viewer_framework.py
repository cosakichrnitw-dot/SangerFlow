"""Checks for the Studio viewer framework primitives."""

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
from app.selection import SelectionKind, StudioSelection
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.analysis_result import AnalysisResultType
from core.sequence_dataset import SequenceDataset, SourceType
from PySide6.QtWidgets import QApplication
from widgets.viewers import BaseViewer, ViewerContext, ViewerRegistry
from widgets.workspace_tabs import WorkspaceTabs


class ExampleViewer(BaseViewer):
    def __init__(self, title: str = "Example Viewer", viewer_id: str = "example-viewer") -> None:
        super().__init__(
            viewer_id=viewer_id,
            viewer_title=title,
            viewer_kind="example",
            source_object_id="example-source",
        )
        self.dataset = None
        self.result = None

    def open_dataset(self, dataset: object) -> None:
        self.dataset = dataset

    def open_result(self, result: object) -> None:
        self.result = result


class ViewerFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_base_viewer_contract(self) -> None:
        viewer = ExampleViewer()

        self.assertEqual(viewer.viewer_id, "example-viewer")
        self.assertEqual(viewer.viewer_title, "Example Viewer")
        self.assertEqual(viewer.viewer_kind, "example")
        self.assertEqual(viewer.source_object_id, "example-source")
        self.assertFalse(viewer.is_dirty)
        self.assertEqual(viewer.supported_actions, ())
        self.assertEqual(viewer.save_state()["viewer_id"], "example-viewer")
        self.assertTrue(viewer.close_viewer())

    def test_registry_resolves_dataset_and_result_viewers(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        context = ViewerContext(state, controller)
        registry = ViewerRegistry()

        registry.register_dataset_viewer(
            SourceType.IMPORTED_FASTA,
            viewer_key="dataset-example",
            label="Dataset Example",
            factory=lambda _context, dataset: _viewer_for_dataset(dataset),
            default=True,
        )
        registry.register_result_viewer(
            AnalysisResultType.BLAST,
            viewer_key="blast-example",
            label="BLAST Example",
            factory=lambda _context, result: _viewer_for_result(result),
            default=True,
        )

        dataset = SequenceDataset.from_sequence_pairs(
            "example-dataset",
            "Example Dataset",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        result = _Result(AnalysisResultType.BLAST)

        dataset_viewer = registry.create_viewer_for(dataset, context)
        result_viewer = registry.create_viewer_for(result, context)

        self.assertIs(dataset_viewer.dataset, dataset)
        self.assertIs(result_viewer.result, result)
        self.assertEqual(
            registry.default_viewer_for(dataset).viewer_key,
            "dataset-example",
        )
        self.assertEqual(
            registry.default_viewer_for(result).viewer_key,
            "blast-example",
        )

    def test_registry_rejects_duplicate_viewer_key(self) -> None:
        registry = ViewerRegistry()
        registry.register_dataset_viewer(
            SourceType.IMPORTED_FASTA,
            viewer_key="dataset-example",
            label="Dataset Example",
            factory=lambda _context, _dataset: ExampleViewer(),
        )

        with self.assertRaises(ValueError):
            registry.register_dataset_viewer(
                SourceType.IMPORTED_FASTA,
                viewer_key="dataset-example",
                label="Dataset Example",
                factory=lambda _context, _dataset: ExampleViewer(),
            )

    def test_tab_manager_opens_focuses_and_closes_viewers(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        manager = TabManager(tabs, state)
        viewer = ExampleViewer()

        opened: list[object] = []
        closed: list[str] = []
        state.viewer_opened.connect(opened.append)
        state.viewer_closed.connect(closed.append)

        viewer_id = manager.open_viewer(viewer, resource_key="dataset:example")
        self.application.processEvents()

        self.assertEqual(viewer_id, "example-viewer")
        self.assertEqual(tabs.count(), 3)
        self.assertIs(state.active_viewer, viewer)
        self.assertEqual(opened, [viewer])
        self.assertIsNone(state.selected_item)

        focused_id = manager.open_viewer(ExampleViewer(), resource_key="dataset:example")
        self.assertEqual(focused_id, "example-viewer")
        self.assertEqual(tabs.count(), 3)

        self.assertTrue(manager.close_viewer("example-viewer"))
        self.assertEqual(closed, ["example-viewer"])
        self.assertEqual(tabs.count(), 2)

    def test_tab_manager_close_buttons_others_and_all(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        manager = TabManager(tabs, state)

        viewer_1 = ExampleViewer("Viewer 1", "viewer-1")
        viewer_2 = ExampleViewer("Viewer 2", "viewer-2")
        viewer_3 = ExampleViewer("Viewer 3", "viewer-3")
        manager.open_viewer(viewer_1, resource_key="dataset:1")
        manager.open_viewer(viewer_2, resource_key="dataset:2")
        manager.open_viewer(viewer_3, resource_key="dataset:3")

        self.assertTrue(tabs.tabsClosable())
        self.assertEqual(manager.viewer_ids(), ("viewer-1", "viewer-2", "viewer-3"))

        manager.close_others("viewer-2")

        self.assertEqual(manager.viewer_ids(), ("viewer-2",))
        self.assertEqual(tabs.count(), 3)

        manager.close_all()

        self.assertEqual(manager.viewer_ids(), ())
        self.assertEqual(tabs.count(), 2)

    def test_studio_selection_helpers(self) -> None:
        project = _Project()
        dataset_entry = _DatasetEntry()
        result_entry = _ResultEntry()

        self.assertEqual(StudioSelection.project(project).object_id, "project-1")
        self.assertEqual(
            StudioSelection.dataset(dataset_entry).kind,
            SelectionKind.DATASET,
        )
        self.assertEqual(
            StudioSelection.analysis_result(result_entry).kind,
            SelectionKind.ANALYSIS_RESULT,
        )


def _viewer_for_dataset(dataset: object) -> ExampleViewer:
    viewer = ExampleViewer("Dataset Viewer")
    viewer.open_dataset(dataset)
    return viewer


def _viewer_for_result(result: object) -> ExampleViewer:
    viewer = ExampleViewer("Result Viewer")
    viewer.open_result(result)
    return viewer


class _Result:
    def __init__(self, result_type: AnalysisResultType) -> None:
        self.result_type = result_type


class _Project:
    project_id = "project-1"


class _Dataset:
    dataset_id = "dataset-1"


class _DatasetEntry:
    dataset = _Dataset()


class _ResultEntry:
    result_id = "result-1"
