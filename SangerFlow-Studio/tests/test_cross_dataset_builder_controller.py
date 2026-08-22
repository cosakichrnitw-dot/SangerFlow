"""Studio controller coverage for the GUI-independent cross-dataset builder."""

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

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.lineage import RecordRef
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType


class CrossDatasetBuilderControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_registers_multiple_parent_dataset_through_app_state(self) -> None:
        first = SequenceDataset.from_sequence_pairs(
            "Run_A", "Run A", SourceType.IMPORTED_FASTA, (("C1", "ATGC"),)
        )
        second = SequenceDataset.from_sequence_pairs(
            "Run_B", "Run B", SourceType.IMPORTED_FASTA, (("C4", "TTTA"),)
        )
        project = Project.create("project", "Project").add_dataset(first).add_dataset(second)
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(project)

        dataset = controller.create_dataset_from_project_record_refs(
            (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")),
            dataset_id="Final_COI",
            name="Final COI",
        )

        self.assertTrue(state.is_dirty)
        self.assertEqual(dataset.sequence_ids, ("C1", "C4"))
        entry = state.current_project.get_entry("Final_COI")
        self.assertEqual(tuple(relation.source_id for relation in entry.lineage_relations), ("Run_A", "Run_B"))


if __name__ == "__main__":
    unittest.main()
