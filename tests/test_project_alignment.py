"""Tests for adding existing MAFFT workflow results to a Project."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.mafft_workflow import align_sequence_dataset
from workflow.project_alignment import add_alignment_to_project


def make_parent_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "ATGCAA"), ("IK346", "ATGTCAA"))
    )


def runner_for(stdout: str):
    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


class ProjectAlignmentTests(unittest.TestCase):
    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_adds_mafft_result_with_parent_and_derivation_without_mutating_inputs(self, _which) -> None:
        parent = make_parent_dataset()
        alignment = align_sequence_dataset(
            parent,
            runner=runner_for(">IK345\nATG-CAA\n>IK346\nATGTCAA\n"),
        )
        project = Project.create("project", "Project").add_dataset(parent)

        updated = add_alignment_to_project(project, alignment, metadata={"note": "test"})

        self.assertEqual(project.dataset_ids, ("input",))
        self.assertEqual(updated.dataset_ids, ("input", "input_mafft"))
        self.assertIs(updated.get_dataset("input_mafft"), alignment)
        entry = updated.get_entry("input_mafft")
        self.assertEqual(entry.parent_dataset_id, "input")
        self.assertEqual(entry.derivation_type, DerivationType.ALIGNED_WITH_MAFFT)
        self.assertTrue(entry.metadata["added_to_project"])
        self.assertEqual(entry.metadata["note"], "test")
        self.assertEqual(alignment.metadata["parent_dataset_id"], "input")
        self.assertEqual(tuple(record.sequence for record in alignment.records), ("ATG-CAA", "ATGTCAA"))

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_rejects_duplicate_dataset_id_and_missing_parent(self, _which) -> None:
        parent = make_parent_dataset()
        alignment = align_sequence_dataset(
            parent,
            runner=runner_for(">IK345\nATG-CAA\n>IK346\nATGTCAA\n"),
        )
        project = Project.create("project", "Project").add_dataset(parent)
        with_alignment = add_alignment_to_project(project, alignment)

        with self.assertRaisesRegex(ValueError, "already exists"):
            add_alignment_to_project(with_alignment, alignment)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            add_alignment_to_project(
                project,
                alignment,
                parent_dataset_id="not-in-project",
            )
        self.assertEqual(project.dataset_ids, ("input",))

    def test_rejects_non_alignment_dataset(self) -> None:
        project = Project.create("project", "Project")

        with self.assertRaisesRegex(ValueError, "IMPORTED_ALIGNMENT"):
            add_alignment_to_project(project, make_parent_dataset(), parent_dataset_id="input")

    def test_adds_alignment_dataset_model_to_project(self) -> None:
        parent = make_parent_dataset()
        alignment = AlignmentDataset.from_sequence_dataset(
            alignment_id="input_alignment",
            name="Input Alignment",
            parent_dataset=parent,
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-CAA"),
                AlignmentRecord("IK346", "IK346", "ATGTCAA"),
            ),
            metadata={
                "parent_dataset_id": "input",
                "derivation_type": DerivationType.ALIGNMENT_FROM_DATASET.value,
            },
        )
        project = Project.create("project", "Project").add_dataset(parent)

        updated = add_alignment_to_project(project, alignment)

        self.assertEqual(updated.dataset_ids, ("input", "input_alignment"))
        self.assertIs(updated.get_dataset("input_alignment"), alignment)
        self.assertEqual(
            updated.get_entry("input_alignment").derivation_type,
            DerivationType.ALIGNMENT_FROM_DATASET,
        )


if __name__ == "__main__":
    unittest.main()
