"""Tests for the SequenceDataset-to-MAFFT workflow adapter."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.sequence_dataset import SequenceDataset, SourceType
from workflow.mafft_workflow import align_sequence_dataset


def make_unaligned_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "imported",
        "Imported FASTA",
        SourceType.IMPORTED_FASTA,
        (("IK345", "ATGCAA"), ("IK346", "ATGTCAA")),
    )


def runner_for(stdout: str):
    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


class MafftWorkflowTests(unittest.TestCase):
    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_aligns_dataset_with_existing_mafft_core_and_returns_new_dataset(self, _which) -> None:
        input_dataset = make_unaligned_dataset()

        aligned_dataset = align_sequence_dataset(
            input_dataset,
            alignment_id="workflow-test",
            runner=runner_for(">IK346\nATGTCAA\n>IK345\nATG-CAA\n"),
        )

        self.assertEqual(aligned_dataset.dataset_id, "imported_mafft")
        self.assertEqual(aligned_dataset.source_type, SourceType.IMPORTED_ALIGNMENT)
        self.assertEqual(aligned_dataset.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(
            tuple(record.sequence for record in aligned_dataset.records),
            ("ATG-CAA", "ATGTCAA"),
        )
        self.assertEqual(aligned_dataset.metadata["parent_dataset_id"], "imported")
        self.assertEqual(aligned_dataset.metadata["derivation_type"], "ALIGNED_WITH_MAFFT")
        self.assertEqual(aligned_dataset.metadata["alignment_length"], 7)
        self.assertEqual(aligned_dataset.metadata["gap_count"], 1)
        self.assertEqual(aligned_dataset.metadata["mafft_alignment_id"], "workflow-test")
        self.assertEqual(
            tuple(record.sequence for record in input_dataset.records),
            ("ATGCAA", "ATGTCAA"),
        )
        self.assertEqual(input_dataset.source_type, SourceType.IMPORTED_FASTA)
        self.assertIs(aligned_dataset.records[0].source_reference, input_dataset.records[0])

    def test_allows_explicit_alignment_dataset_identity_and_name(self) -> None:
        with patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft"):
            aligned_dataset = align_sequence_dataset(
                make_unaligned_dataset(),
                dataset_id="population-a-alignment",
                name="Population A alignment",
                runner=runner_for(">IK345\nATG-CAA\n>IK346\nATGTCAA\n"),
            )

        self.assertEqual(aligned_dataset.dataset_id, "population-a-alignment")
        self.assertEqual(aligned_dataset.name, "Population A alignment")

    def test_rejects_gap_containing_input_without_changing_it(self) -> None:
        input_dataset = SequenceDataset.from_sequence_pairs(
            "already-aligned",
            "Already aligned",
            SourceType.IMPORTED_ALIGNMENT,
            (("IK345", "ATG-CAA"), ("IK346", "ATGTCAA")),
        )

        with self.assertRaisesRegex(ValueError, "without gaps"):
            align_sequence_dataset(input_dataset)
        self.assertEqual(
            tuple(record.sequence for record in input_dataset.records),
            ("ATG-CAA", "ATGTCAA"),
        )


if __name__ == "__main__":
    unittest.main()
