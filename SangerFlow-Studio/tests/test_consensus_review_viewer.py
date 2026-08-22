"""Tests for Studio Consensus Review workflow integration."""

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
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.models import SangerRead
from core.project import Project
from core.sequence_dataset import SourceType
from persistence.project_bundle import load_project_bundle, save_project_bundle
from views.project_view import ProjectView
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers.consensus_review_viewer import (
    ConsensusChange,
    ConsensusReviewViewer,
    build_reviewed_consensus_dataset,
)


def _alignment_dataset() -> AlignmentDataset:
    return AlignmentDataset(
        alignment_id="alignment-1",
        name="COI alignment",
        parent_dataset_id="reads-1",
        records=(
            AlignmentRecord("read-1", "read-1", "ATGC"),
            AlignmentRecord("read-2", "read-2", "ATGT"),
        ),
    )


def _read(filename: str, sequence: str) -> SangerRead:
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[30] * len(sequence),
        traces={
            "A": [0, 10, 0, 5, 0, 10, 0, 5],
            "C": [0, 5, 0, 10, 0, 5, 0, 10],
            "G": [0, 8, 0, 4, 0, 8, 0, 4],
            "T": [0, 4, 0, 8, 0, 4, 0, 8],
        },
        base_positions=[1, 3, 5, 7],
        trim_start=0,
        trim_end=len(sequence),
        trimmed_sequence=sequence,
        trimmed_quality=[30] * len(sequence),
        trimmed_base_positions=[1, 3, 5, 7],
        trimmed_traces={
            "A": [0, 10, 0, 5, 0, 10, 0, 5],
            "C": [0, 5, 0, 10, 0, 5, 0, 10],
            "G": [0, 8, 0, 4, 0, 8, 0, 4],
            "T": [0, 4, 0, 8, 0, 4, 0, 8],
        },
    )


class ConsensusReviewViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_edits_reviewed_consensus_and_preserves_original_with_undo_redo(self) -> None:
        viewer = ConsensusReviewViewer(_alignment_dataset())

        self.assertEqual(viewer.original_consensus, "ATGC")
        self.assertEqual(viewer.reviewed_consensus, "ATGC")

        viewer.select_position(4)
        self.assertTrue(viewer.edit_selected_base("N"))
        self.assertEqual(viewer.original_consensus, "ATGC")
        self.assertEqual(viewer.reviewed_consensus, "ATGN")
        self.assertEqual(len(viewer.change_log), 1)
        self.assertEqual(viewer.change_log[0].position, 4)
        self.assertEqual(viewer.change_log[0].original_base, "C")
        self.assertEqual(viewer.change_log[0].reviewed_base, "N")

        viewer.undo()
        self.assertEqual(viewer.reviewed_consensus, "ATGC")
        self.assertEqual(viewer.change_log, ())

        viewer.redo()
        self.assertEqual(viewer.reviewed_consensus, "ATGN")
        self.assertEqual(len(viewer.change_log), 1)

    def test_create_reviewed_consensus_dataset_keeps_change_log_in_metadata(self) -> None:
        viewer = ConsensusReviewViewer(_alignment_dataset())
        viewer.edit_base(2, "-")

        dataset = viewer.create_reviewed_dataset()

        self.assertEqual(dataset.source_type, SourceType.REVIEWED_CONSENSUS)
        self.assertEqual(dataset.records[0].sequence, "A-GC")
        self.assertTrue(dataset.metadata["reviewed"])
        self.assertEqual(dataset.metadata["original_consensus"], "ATGC")
        self.assertEqual(dataset.metadata["reviewed_consensus"], "A-GC")
        self.assertEqual(dataset.metadata["parent_alignment_id"], "alignment-1")
        self.assertEqual(dataset.metadata["change_log"][0]["position"], 2)

    def test_controller_registers_reviewed_consensus_dataset_in_project(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        alignment = _alignment_dataset()
        project = Project.create("project", "Project").add_dataset(alignment)
        controller.open_project(project)
        viewer = ConsensusReviewViewer(alignment, context=view.viewer_context)
        viewer.edit_base(4, "N")

        dataset = viewer.create_and_register_reviewed_dataset()

        self.assertIsNotNone(dataset)
        self.assertTrue(state.is_dirty)
        self.assertEqual(
            state.current_project.dataset_ids,
            ("alignment-1", "alignment-1_reviewed_consensus"),
        )
        entry = state.current_project.get_entry("alignment-1_reviewed_consensus")
        self.assertEqual(entry.parent_dataset_id, "alignment-1")
        self.assertEqual(entry.display_name, "Reviewed Consensus")

    def test_reviewed_consensus_metadata_survives_project_bundle_reload(self) -> None:
        alignment = _alignment_dataset()
        dataset = build_reviewed_consensus_dataset(
            alignment,
            dataset_id="reviewed-1",
            name="Reviewed",
            original_consensus="ATGC",
            reviewed_consensus="ATGN",
            change_log=(
                ConsensusChange(
                    position=4,
                    original_base="C",
                    reviewed_base="N",
                    changed_at="2026-08-10T00:00:00+00:00",
                ),
            ),
        )
        project = Project.create("project", "Project").add_dataset(alignment).add_dataset(
            dataset,
            parent_dataset_id="alignment-1",
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            save_project_bundle(project, path)
            loaded = load_project_bundle(path)
            try:
                loaded_dataset = loaded.project.get_dataset("reviewed-1")
                self.assertEqual(loaded_dataset.records[0].sequence, "ATGN")
                self.assertEqual(loaded_dataset.metadata["original_consensus"], "ATGC")
                self.assertEqual(loaded_dataset.metadata["reviewed_consensus"], "ATGN")
                self.assertEqual(loaded_dataset.metadata["change_log"][0]["position"], 4)
                self.assertEqual(
                    loaded_dataset.metadata["change_log"][0]["reviewed_base"], "N"
                )
            finally:
                loaded.cleanup()

    def test_alignment_chromatogram_viewer_exposes_review_consensus_action(self) -> None:
        alignment = _alignment_dataset()
        viewer = AlignmentChromatogramViewer(
            (_read("read-1", "ATGC"), _read("read-2", "ATGT")),
            alignment=(type("Record", (), {"id": "read-1", "seq": "ATGC"})(), type("Record", (), {"id": "read-2", "seq": "ATGT"})()),
            alignment_dataset=alignment,
        )

        action_ids = tuple(
            action.action_id
            for action in viewer.action_providers[0].actions_for(viewer)
        )

        self.assertIn("alignment_chromatogram.review_consensus", action_ids)

    def test_export_reviewed_dataset_to_existing_sequence_formats(self) -> None:
        viewer = ConsensusReviewViewer(_alignment_dataset())
        viewer.edit_base(4, "N")
        dataset = viewer.create_reviewed_dataset()

        with TemporaryDirectory() as directory:
            from export.sequence_export import (
                export_dataset_to_fasta,
                export_dataset_to_nexus,
                export_dataset_to_phylip,
            )

            root = Path(directory)
            export_dataset_to_fasta(dataset, root / "reviewed.fasta")
            export_dataset_to_nexus(dataset, root / "reviewed.nex")
            export_dataset_to_phylip(dataset, root / "reviewed.phy")

            self.assertIn(">alignment-1_reviewed_consensus", (root / "reviewed.fasta").read_text())
            self.assertIn("#NEXUS", (root / "reviewed.nex").read_text())
            self.assertIn("1 4", (root / "reviewed.phy").read_text())


if __name__ == "__main__":
    unittest.main()
