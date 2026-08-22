"""Phase 1B controller integration for immutable Dataset revisions."""

from __future__ import annotations

import csv
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

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import Project, RevisionOperation, RevisionState
from core.sequence_dataset import SequenceDataset, SourceType


def _dataset(dataset_id: str = "coi") -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        dataset_id,
        "COI working dataset",
        SourceType.IMPORTED_FASTA,
        (("C1", "ATGC"), ("C2", "ATGT")),
    )


class _EditedAlignmentViewer:
    def __init__(self, dataset: AlignmentDataset) -> None:
        self.dataset = dataset

    def create_edited_alignment_dataset(self, *, alignment_id: str, name: str, metadata=None) -> AlignmentDataset:
        return AlignmentDataset(
            alignment_id=alignment_id,
            name=name,
            parent_dataset_id=self.dataset.parent_dataset_id,
            records=(
                AlignmentRecord("C1", "C1", "AT-C"),
                AlignmentRecord("C2", "C2", "ATGT"),
            ),
            metadata={**dict(self.dataset.metadata), **(metadata or {})},
        )


class RevisionWorkflowIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state = AppState()
        self.controller = ProjectController(self.state)

    def test_single_and_batch_rename_are_full_current_revisions(self) -> None:
        original = _dataset()
        self.controller.open_project(Project.create("project", "Project").add_dataset(original, display_name="Final COI"))
        single = self.controller.create_dataset_revision_with_record_renames(
            original, {"C1": "C1_CO1"}, operation=RevisionOperation.RECORD_RENAME
        )
        project = self.state.current_project
        self.assertEqual(single.sequence_ids, ("C1_CO1", "C2"))
        self.assertEqual(single.get_record("C1_CO1").provenance.source_records[0].dataset_id, "coi")
        self.assertEqual(single.get_record("C2").provenance.source_records[0].sequence_id, "C2")
        self.assertEqual(project.get_entry("coi").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(project.get_entry(single.dataset_id).display_name, "Final COI")
        self.assertEqual(project.get_entry(single.dataset_id).revision_operation, RevisionOperation.RECORD_RENAME)

        batch = self.controller.create_dataset_revision_with_record_renames(
            single,
            {"C1_CO1": "C1_COI", "C2": "C2_COI"},
            operation=RevisionOperation.BATCH_RENAME,
        )
        self.assertEqual(batch.sequence_ids, ("C1_COI", "C2_COI"))
        self.assertEqual(batch.get_record("C1_COI").provenance.source_records[0].dataset_id, single.dataset_id)
        self.assertEqual(project.get_entry("coi").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(self.state.current_project.current_dataset_entry("coi").dataset.dataset_id, batch.dataset_id)

    def test_metadata_merge_is_next_revision_and_stale_or_archived_edits_are_rejected(self) -> None:
        original = _dataset()
        self.controller.open_project(Project.create("project", "Project").add_dataset(original))
        with TemporaryDirectory() as directory:
            csv_path = Path(directory) / "metadata.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("Sample_ID", "Species"))
                writer.writeheader()
                writer.writerow({"Sample_ID": "C1", "Species": "Species A"})
            merged = self.controller.import_sample_metadata_for_dataset(original, str(csv_path))

        project = self.state.current_project
        self.assertEqual(merged.get_record("C1").sequence, "ATGC")
        self.assertEqual(merged.get_record("C1").metadata["species"], "Species A")
        self.assertEqual(merged.get_record("C1").provenance.source_records[0].dataset_id, "coi")
        self.assertEqual(project.get_entry("coi").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(project.get_entry(merged.dataset_id).revision_operation, RevisionOperation.METADATA_MERGE)
        with self.assertRaisesRegex(ValueError, "no longer current"):
            self.controller.create_dataset_revision_with_record_renames(
                original, {"C1": "C1_old"}, operation=RevisionOperation.RECORD_RENAME
            )
        self.state.replace_project(project.archive_logical_dataset("coi"))
        with self.assertRaisesRegex(ValueError, "archived"):
            self.controller.create_dataset_revision_with_record_renames(
                merged, {"C1": "C1_archived"}, operation=RevisionOperation.RECORD_RENAME
            )

    def test_alignment_save_is_revision_but_subset_remains_new_logical_dataset(self) -> None:
        source = _dataset()
        alignment = AlignmentDataset(
            alignment_id="coi_alignment",
            name="COI Alignment",
            parent_dataset_id="coi",
            records=(AlignmentRecord("C1", "C1", "ATGC"), AlignmentRecord("C2", "C2", "ATGT")),
        )
        self.controller.open_project(
            Project.create("project", "Project").add_dataset(source).add_dataset(alignment, parent_dataset_id="coi")
        )
        edited = self.controller.register_edited_alignment_from_viewer(_EditedAlignmentViewer(alignment))
        project = self.state.current_project
        self.assertEqual(project.get_entry("coi_alignment").revision_state, RevisionState.SUPERSEDED)
        edited_entry = project.get_entry(edited.alignment_id)
        self.assertEqual(edited_entry.logical_id, "coi_alignment")
        self.assertEqual(edited_entry.revision_operation, RevisionOperation.ALIGNMENT_EDIT)
        self.assertEqual(edited_entry.parent_dataset_id, "coi")
        self.assertEqual(edited_entry.lineage_relations[0].source_id, "coi")

        subset = self.controller.create_dataset_from_record_selection(source, ("C1",))
        self.assertNotEqual(project.get_entry("coi").logical_id, self.state.current_project.get_entry(subset.dataset_id).logical_id)
        self.assertTrue(self.state.current_project.is_current_revision("coi"))


if __name__ == "__main__":
    unittest.main()
