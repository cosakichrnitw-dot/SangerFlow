"""Internal Project Dataset drag routing regression coverage."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(studio_root), str(studio_root.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.internal_dataset_drag import (
    InternalDatasetDragError,
    create_project_dataset_mime_data,
    decode_project_dataset_drag,
)
from app.main import build_application
from app.selection import StudioSelection
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from widgets.viewers.dataset_viewer import DatasetViewer


def _dataset(identifier: str) -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        identifier, identifier, SourceType.IMPORTED_FASTA, (("sample-1", "ATGC"),)
    )


class InternalDatasetDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_payload_is_identity_only_and_round_trips(self) -> None:
        mime_data = create_project_dataset_mime_data(
            project_id="project-1", dataset_id="dataset-b", dataset_type="sequence_dataset"
        )
        payload = decode_project_dataset_drag(mime_data)
        self.assertEqual(payload.project_id, "project-1")
        self.assertEqual(payload.dataset_id, "dataset-b")
        self.assertEqual(payload.dataset_type, "sequence_dataset")

    def test_invalid_payload_is_rejected_without_model_lookup(self) -> None:
        with self.assertRaises(InternalDatasetDragError):
            decode_project_dataset_drag(create_project_dataset_mime_data(
                project_id="project-1", dataset_id="dataset-b", dataset_type=""
            ))

    def test_sequence_dataset_drop_selects_the_dragged_dataset_and_opens_existing_settings(self) -> None:
        application, window = build_application()
        first, second = _dataset("dataset-a"), _dataset("dataset-b")
        project = Project.create("project-1", "Project").add_dataset(first).add_dataset(second)
        window._state.set_project(project)
        application.processEvents()

        # Simulate a different current selection: the drop must win.
        first_entry = project.get_entry(first.dataset_id)
        window._controller.select_item(StudioSelection.dataset(first_entry), open_viewer=True)
        application.processEvents()
        with patch("controllers.project_controller.AlignmentSettingsDialog.exec", return_value=0) as execute:
            window._align_dropped_sequence_dataset(project.project_id, second.dataset_id)
            application.processEvents()
            application.processEvents()

        self.assertTrue(execute.called)
        self.assertIsInstance(window._state.active_viewer, DatasetViewer)
        self.assertEqual(window._state.active_viewer.dataset.dataset_id, second.dataset_id)
        self.assertEqual(window._state.selected_item.object_id, second.dataset_id)
        window.close()

    def test_current_sequence_dataset_tree_item_is_drag_enabled(self) -> None:
        application, window = build_application()
        dataset = _dataset("dataset-a")
        project = Project.create("project-1", "Project").add_dataset(dataset)
        window._state.set_project(project)
        application.processEvents()
        explorer = window._project_view.widget(0)
        root = explorer.topLevelItem(0)
        working = root.child(0)
        item = working.child(0)
        self.assertTrue(bool(item.flags() & Qt.ItemFlag.ItemIsDragEnabled))
        self.assertEqual(item.data(0, Qt.ItemDataRole.UserRole).object_id, dataset.dataset_id)
        window.close()

    def test_stale_dataset_drop_is_safely_rejected(self) -> None:
        application, window = build_application()
        project = Project.create("project-1", "Project").add_dataset(_dataset("dataset-a"))
        window._state.set_project(project)
        window._align_dropped_sequence_dataset(project.project_id, "missing-dataset")
        application.processEvents()
        self.assertIsNone(window._state.active_viewer)
        self.assertIn("no longer available", window.statusBar().currentMessage())
        window.close()

    def test_align_target_rejects_non_sequence_dataset_payload(self) -> None:
        application, window = build_application()
        manager = window._project_view.action_manager
        self.assertFalse(
            manager.accepts_sequence_dataset_align_drop(
                create_project_dataset_mime_data(
                    project_id="project-1", dataset_id="alignment-1", dataset_type="alignment_dataset"
                )
            )
        )
        window.close()
