"""Tests for adapting legacy MAFFT output to AlignmentDataset values."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.alignment_dataset import AlignmentRecord
from core.project import DerivationType
from core.sequence_dataset import SequenceRecord, SequenceDataset, SourceType
from workflow.mafft_alignment_dataset import create_alignment_dataset_from_mafft


def make_source_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-candidates",
        "COI candidates",
        SourceType.CONSENSUS_CANDIDATE,
        (("IK345", "ATGCAA"), ("IK346", "ATGTCAA")),
    )


class MafftAlignmentDatasetTests(unittest.TestCase):
    def test_creates_alignment_dataset_with_required_mafft_lineage_metadata(self) -> None:
        source = make_source_dataset()
        aligned = create_alignment_dataset_from_mafft(
            source,
            (
                SequenceRecord("IK345", "ATG-CAA", metadata={"quality": "reviewed"}),
                {"record_id": "IK346", "aligned_sequence": "ATGTCAA"},
            ),
            dataset_id="coi-mafft",
            name="COI MAFFT alignment",
            metadata={"mafft_alignment_id": "mafft-1"},
        )

        self.assertEqual(aligned.alignment_id, "coi-mafft")
        self.assertEqual(aligned.parent_dataset_id, "coi-candidates")
        self.assertEqual(aligned.record_ids(), ("IK345", "IK346"))
        self.assertEqual(aligned.get_record("IK345").aligned_sequence, "ATG-CAA")
        self.assertEqual(aligned.get_record("IK345").metadata["quality"], "reviewed")
        self.assertEqual(aligned.metadata["alignment_method"], "MAFFT")
        self.assertEqual(aligned.metadata["software"], "MAFFT")
        self.assertEqual(aligned.metadata["parent_dataset_id"], "coi-candidates")
        self.assertEqual(
            aligned.metadata["derivation_type"],
            DerivationType.ALIGNMENT_FROM_DATASET.value,
        )
        self.assertEqual(aligned.metadata["mafft_alignment_id"], "mafft-1")
        self.assertEqual(source.records[0].sequence, "ATGCAA")

    def test_validates_source_ids_and_keeps_result_immutable(self) -> None:
        source = make_source_dataset()
        with self.assertRaisesRegex(ValueError, "source_record_id"):
            create_alignment_dataset_from_mafft(
                source,
                (AlignmentRecord("unknown", "not-in-source", "ATG-CAA"),),
                dataset_id="invalid",
                name="Invalid",
            )
        aligned = create_alignment_dataset_from_mafft(
            source,
            (
                AlignmentRecord("IK345", "IK345", "ATG-CAA"),
                AlignmentRecord("IK346", "IK346", "ATGTCAA"),
            ),
            dataset_id="coi-mafft",
            name="COI MAFFT alignment",
        )
        with self.assertRaises(FrozenInstanceError):
            aligned.name = "Changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            aligned.metadata["software"] = "other"  # type: ignore[index]

    def test_rejects_non_dataset_and_invalid_aligned_record(self) -> None:
        with self.assertRaisesRegex(ValueError, "source_dataset"):
            create_alignment_dataset_from_mafft(  # type: ignore[arg-type]
                object(), (), dataset_id="bad", name="Bad"
            )
        with self.assertRaisesRegex(ValueError, "aligned_records"):
            create_alignment_dataset_from_mafft(
                make_source_dataset(),
                (object(),),  # type: ignore[arg-type]
                dataset_id="bad",
                name="Bad",
            )


if __name__ == "__main__":
    unittest.main()
