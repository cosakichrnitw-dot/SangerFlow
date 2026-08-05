"""Tests for immutable alignment dataset viewer adaptation."""

from __future__ import annotations

import unittest

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from workflow.alignment_viewer_adapter import create_alignment_viewer_input


def make_alignment_dataset() -> SequenceDataset:
    source_one = object()
    source_two = object()
    return SequenceDataset(
        "alignment",
        "Alignment",
        SourceType.IMPORTED_ALIGNMENT,
        (
            SequenceRecord("IK345", "ATG-CAA", metadata={"row": 1}, source_reference=source_one),
            SequenceRecord("IK346", "ATGTCAA", metadata={"row": 2}, source_reference=source_two),
        ),
        metadata={"parent_dataset_id": "input", "workflow": "MAFFT"},
    )


class AlignmentViewerAdapterTests(unittest.TestCase):
    def test_creates_legacy_viewer_compatible_input_preserving_rows_and_metadata(self) -> None:
        dataset = make_alignment_dataset()

        viewer_input = create_alignment_viewer_input(dataset, metadata={"opened_from": "router"})

        self.assertEqual(len(viewer_input), 2)
        self.assertEqual(viewer_input.alignment_length, 7)
        self.assertEqual([record.id for record in viewer_input], ["IK345", "IK346"])
        self.assertEqual([str(record.seq) for record in viewer_input], ["ATG-CAA", "ATGTCAA"])
        self.assertEqual(viewer_input.records[0].metadata["row"], 1)
        self.assertIs(viewer_input.records[0].source_reference, dataset.records[0].source_reference)
        self.assertEqual(viewer_input.metadata["parent_dataset_id"], "input")
        self.assertEqual(viewer_input.metadata["opened_from"], "router")
        with self.assertRaises(TypeError):
            viewer_input.metadata["opened_from"] = "changed"  # type: ignore[index]

    def test_rejects_non_alignment_dataset_unequal_lengths_and_ungapped_alignment(self) -> None:
        non_alignment = SequenceDataset.from_sequence_pairs(
            "fasta", "FASTA", SourceType.IMPORTED_FASTA, [("one", "ATGC")]
        )
        unequal = SequenceDataset.from_sequence_pairs(
            "unequal", "Unequal", SourceType.IMPORTED_ALIGNMENT, [("one", "ATG-C"), ("two", "ATGTCA")]
        )
        ungapped = SequenceDataset.from_sequence_pairs(
            "ungapped", "Ungapped", SourceType.IMPORTED_ALIGNMENT, [("one", "ATGC"), ("two", "ATGT")]
        )

        with self.assertRaisesRegex(ValueError, "IMPORTED_ALIGNMENT"):
            create_alignment_viewer_input(non_alignment)
        with self.assertRaisesRegex(ValueError, "equal length"):
            create_alignment_viewer_input(unequal)
        with self.assertRaisesRegex(ValueError, "at least one gap"):
            create_alignment_viewer_input(ungapped)

    def test_input_dataset_is_not_modified(self) -> None:
        dataset = make_alignment_dataset()
        before_sequences = tuple(record.sequence for record in dataset.records)
        before_metadata = dict(dataset.metadata)

        create_alignment_viewer_input(dataset)

        self.assertEqual(tuple(record.sequence for record in dataset.records), before_sequences)
        self.assertEqual(dict(dataset.metadata), before_metadata)


if __name__ == "__main__":
    unittest.main()
