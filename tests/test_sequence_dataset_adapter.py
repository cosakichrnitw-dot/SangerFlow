"""Tests for the trimmed-sequence dataset adapter."""

from __future__ import annotations

import unittest

from core.sequence_dataset import SourceType
from core.sequence_dataset_adapter import from_trimmed_sequences


class TrimmedSequenceDatasetAdapterTests(unittest.TestCase):
    def test_creates_trimmed_dataset_preserving_input_order(self) -> None:
        source = [("IK345", "atgc"), ("IK346", "ATG-")]

        dataset = from_trimmed_sequences("trimmed", "Trimmed reads", source)

        self.assertEqual(dataset.source_type, SourceType.AB1_TRIMMED)
        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(tuple(record.sequence for record in dataset.records), ("ATGC", "ATG-"))
        self.assertEqual(source, [("IK345", "atgc"), ("IK346", "ATG-")])

    def test_metadata_is_preserved_as_a_read_only_dataset_snapshot(self) -> None:
        source_metadata = {"representation": "trimmed", "trim_method": "existing"}

        dataset = from_trimmed_sequences(
            "trimmed", "Trimmed reads", [("IK345", "ATGC")], metadata=source_metadata
        )
        source_metadata["trim_method"] = "changed"

        self.assertEqual(dataset.metadata["representation"], "trimmed")
        self.assertEqual(dataset.metadata["trim_method"], "existing")
        with self.assertRaises(TypeError):
            dataset.metadata["trim_method"] = "other"  # type: ignore[index]

    def test_duplicate_ids_and_invalid_sequence_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            from_trimmed_sequences(
                "trimmed", "Trimmed", [("same", "ATGC"), ("same", "ATGT")]
            )
        with self.assertRaisesRegex(ValueError, "invalid DNA/IUPAC"):
            from_trimmed_sequences("trimmed", "Trimmed", [("invalid", "ATUZ")])


if __name__ == "__main__":
    unittest.main()
