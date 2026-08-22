"""Tests for Studio FASTA/FAS import into Project datasets and viewers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset
from core.sequence_dataset import SequenceDataset, SourceType
from views.project_view import ProjectView
from widgets.viewers.alignment_viewer import AlignmentViewer
from widgets.viewers.dataset_viewer import DatasetViewer


class SequenceFileImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_open_fas_imports_sequence_dataset_and_opens_dataset_viewer(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coi.fas"
            path.write_text(">IK345 sample A\nATGC\n>IK346 sample B\nATGT\n", encoding="utf-8")

            controller.open_sequence_file(str(path))

        project = state.current_project
        self.assertIsNotNone(project)
        self.assertEqual(project.dataset_count, 1)
        dataset = project.dataset_entries[0].dataset
        self.assertIsInstance(dataset, SequenceDataset)
        self.assertEqual(dataset.source_type, SourceType.IMPORTED_FASTA)
        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))
        self.assertIsInstance(state.active_viewer, DatasetViewer)
        view.close()

    def test_open_gapped_fasta_imports_alignment_dataset_and_opens_alignment_viewer(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coi_alignment.fasta"
            path.write_text(">IK345\nATG-C\n>IK346\nATGGC\n", encoding="utf-8")

            controller.open_sequence_file(str(path))

        project = state.current_project
        self.assertIsNotNone(project)
        self.assertEqual(project.dataset_count, 2)
        parent_dataset = project.dataset_entries[0].dataset
        alignment_dataset = project.dataset_entries[1].dataset
        self.assertIsInstance(parent_dataset, SequenceDataset)
        self.assertIsInstance(alignment_dataset, AlignmentDataset)
        self.assertEqual(alignment_dataset.parent_dataset_id, parent_dataset.dataset_id)
        self.assertEqual(alignment_dataset.get_record("IK345").aligned_sequence, "ATG-C")
        self.assertIsInstance(state.active_viewer, AlignmentViewer)
        view.close()


if __name__ == "__main__":
    unittest.main()
