"""Tests for immutable already-aligned sequence dataset models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.sequence_dataset import SequenceDataset, SourceType


def make_parent_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-candidates",
        "COI Candidates",
        SourceType.CONSENSUS_CANDIDATE,
        (("IK345", "ATGCAA"), ("IK346", "ATGTCAA")),
    )


def make_records() -> tuple[AlignmentRecord, ...]:
    return (
        AlignmentRecord("IK345", "IK345", "ATG-CAA", metadata={"sample": "IK345"}),
        AlignmentRecord("IK346", "IK346", "ATGTCAA"),
    )


class AlignmentDatasetTests(unittest.TestCase):
    def test_creates_alignment_with_length_lineage_and_marker_regions(self) -> None:
        parent = make_parent_dataset()
        dataset = AlignmentDataset.from_sequence_dataset(
            alignment_id="coi-mafft-001",
            name="COI MAFFT",
            parent_dataset=parent,
            records=make_records(),
            marker_regions=({"name": "COI", "start": 1, "end": 7},),
            metadata={"aligner": "MAFFT"},
        )

        self.assertEqual(dataset.parent_dataset_id, "coi-candidates")
        self.assertEqual(dataset.record_ids(), ("IK345", "IK346"))
        self.assertEqual(dataset.get_record("IK345").source_record_id, "IK345")
        self.assertEqual(dataset.length, 7)
        self.assertEqual(dataset.sequence_count, 2)
        self.assertEqual(dataset.marker_regions, (MarkerRegion("COI", 1, 7),))
        self.assertEqual(dataset.metadata["aligner"], "MAFFT")
        self.assertEqual(parent.sequence_ids, ("IK345", "IK346"))

    def test_rejects_length_source_marker_and_sequence_validation_errors(self) -> None:
        with self.assertRaisesRegex(ValueError, "same alignment length"):
            AlignmentDataset(
                "bad", "Bad", "parent", (AlignmentRecord("a", "a", "ATG"), AlignmentRecord("b", "b", "ATGC"))
            )
        with self.assertRaisesRegex(ValueError, "source_record_id"):
            AlignmentDataset.from_sequence_dataset(
                alignment_id="bad-source",
                name="Bad source",
                parent_dataset=make_parent_dataset(),
                records=(AlignmentRecord("other", "missing", "ATGC"),),
            )
        with self.assertRaisesRegex(ValueError, "outside alignment length"):
            AlignmentDataset(
                "bad-region",
                "Bad region",
                "parent",
                (AlignmentRecord("a", "a", "ATGC"),),
                marker_regions=(MarkerRegion("COI", 1, 5),),
            )
        with self.assertRaisesRegex(ValueError, "invalid DNA/IUPAC"):
            AlignmentRecord("a", "a", "ATGZ")

    def test_values_and_metadata_are_immutable(self) -> None:
        dataset = AlignmentDataset.from_sequence_dataset(
            alignment_id="coi",
            name="COI",
            parent_dataset=make_parent_dataset(),
            records=make_records(),
        )
        with self.assertRaises(FrozenInstanceError):
            dataset.name = "Changed"  # type: ignore[misc]
        with self.assertRaises(TypeError):
            dataset.metadata["x"] = "y"  # type: ignore[index]
        with self.assertRaises(TypeError):
            dataset.records[0].metadata["x"] = "y"  # type: ignore[index]
        with self.assertRaises(KeyError):
            dataset.get_record("unknown")


if __name__ == "__main__":
    unittest.main()
