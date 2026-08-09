"""Offscreen integration checks for opening a persisted SangerFlow Project."""

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

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from persistence.project_bundle import save_project_bundle
from PySide6.QtWidgets import QApplication
from views.project_view import ProjectView


def _bundle_project() -> Project:
    dataset = SequenceDataset.from_sequence_pairs(
        "bundle-imported-fasta",
        "Imported FASTA",
        SourceType.IMPORTED_FASTA,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )
    project = Project.create("bundle-project", "Bundle Project", {"marker": "COI"})
    project = project.add_dataset(dataset)
    return project.add_analysis_result(
        AnalysisResult(
            result_id="bundle-blast",
            name="BLAST",
            result_type=AnalysisResultType.BLAST,
            parent_dataset_id=dataset.dataset_id,
        )
    )


class ProjectBundleOpenTests(unittest.TestCase):
    def test_controller_loads_bundle_and_refreshes_project_tree_and_inspector(self) -> None:
        with TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "bundle.sangerflow"
            save_project_bundle(_bundle_project(), bundle_path)

            state = AppState()
            controller = ProjectController(state)
            application = QApplication.instance() or QApplication([])
            view = ProjectView(state, controller)
            loaded = controller.open_project_bundle(str(bundle_path))
            application.processEvents()

            self.assertEqual(state.current_project.name, "Bundle Project")
            self.assertIs(state.current_repository, loaded.repository)
            explorer = view.widget(0)
            root = explorer.topLevelItem(0)
            self.assertEqual(root.text(0), "Bundle Project")
            self.assertEqual(root.child(0).text(0), "Datasets")
            self.assertEqual(root.child(0).child(0).text(0), "Imported FASTA")
            self.assertEqual(root.child(1).text(0), "Analysis Results")
            self.assertEqual(root.child(1).child(0).text(0), "BLAST")

            explorer.setCurrentItem(root.child(0).child(0))
            application.processEvents()
            inspector = view.widget(2)
            self.assertEqual(inspector._title.text(), "Dataset")
            inspector_values = [
                inspector._layout.itemAt(index).widget().text()
                for index in range(inspector._layout.count())
                if inspector._layout.itemAt(index).widget() is not None
            ]
            self.assertIn("bundle-imported-fasta", inspector_values)

            state.close_current_bundle()
