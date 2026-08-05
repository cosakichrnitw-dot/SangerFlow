"""Tests for the immutable sequence dataset prototype."""

from __future__ import annotations

import unittest

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


class SequenceDatasetTests(unittest.TestCase):
    def make_dataset(self) -> SequenceDataset:
        return SequenceDataset.from_sequence_pairs(
            dataset_id="validation-coi",
            name="Validation COI",
            source_type=SourceType.IMPORTED_FASTA,
            sequences=[("IK345", "atgc"), ("IK346", "ATG-")],
        )

    def test_normal_factory_preserves_record_order_and_normalizes_sequence(self) -> None:
        dataset = self.make_dataset()

        self.assertEqual(dataset.sequence_count, 2)
        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(tuple(record.sequence for record in dataset.records), ("ATGC", "ATG-"))

    def test_duplicate_sequence_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate"):
            SequenceDataset.from_sequence_pairs(
                "dataset",
                "Dataset",
                SourceType.AB1_RAW,
                [("same", "A"), ("same", "T")],
            )

    def test_invalid_dna_character_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid DNA/IUPAC"):
            SequenceRecord("invalid", "ATUZ")

    def test_iupac_and_gap_symbols_are_allowed(self) -> None:
        record = SequenceRecord("iupac", "acgtnryswkmbdhv-")

        self.assertEqual(record.sequence, "ACGTNRYSWKMBDHV-")

    def test_length_statistics_and_equal_length_status(self) -> None:
        dataset = self.make_dataset()
        unequal = SequenceDataset.from_sequence_pairs(
            "unequal", "Unequal", SourceType.IMPORTED_ALIGNMENT, [("a", "AT"), ("b", "ATGC")]
        )

        self.assertEqual(dataset.lengths, (4, 4))
        self.assertEqual(dataset.minimum_length, 4)
        self.assertEqual(dataset.maximum_length, 4)
        self.assertTrue(dataset.has_gaps)
        self.assertTrue(dataset.is_equal_length)
        self.assertFalse(unequal.is_equal_length)

    def test_get_record_returns_matching_record_and_missing_id_raises_key_error(self) -> None:
        dataset = self.make_dataset()

        self.assertEqual(dataset.get_record("IK346").sequence, "ATG-")
        with self.assertRaises(KeyError):
            dataset.get_record("missing")

    def test_selected_records_returns_new_dataset_in_requested_order(self) -> None:
        dataset = self.make_dataset()
        selected = dataset.selected_records(["IK346", "IK345"])

        self.assertIsNot(selected, dataset)
        self.assertEqual(selected.sequence_ids, ("IK346", "IK345"))
        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(selected.metadata, dataset.metadata)

    def test_empty_dataset_and_empty_record_sequence_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            SequenceDataset("empty", "Empty", SourceType.IMPORTED_FASTA, ())
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            SequenceRecord("empty", "")

    def test_metadata_is_copied_and_read_only(self) -> None:
        record_metadata = {"origin": "manual"}
        dataset_metadata = {"project": "COI"}
        record = SequenceRecord("record", "ATGC", metadata=record_metadata)
        dataset = SequenceDataset(
            "dataset", "Dataset", SourceType.CONSENSUS_CANDIDATE, (record,), dataset_metadata
        )

        record_metadata["origin"] = "changed"
        dataset_metadata["project"] = "changed"
        self.assertEqual(record.metadata["origin"], "manual")
        self.assertEqual(dataset.metadata["project"], "COI")
        with self.assertRaises(TypeError):
            record.metadata["origin"] = "other"  # type: ignore[index]
        with self.assertRaises(TypeError):
            dataset.metadata["project"] = "other"  # type: ignore[index]

    def test_source_reference_is_preserved_but_never_modified(self) -> None:
        source = {"sequence": "source-value"}
        record = SequenceRecord("source", "ATGC", source_reference=source)
        dataset = SequenceDataset(
            "source-dataset", "Source dataset", SourceType.AB1_TRIMMED, (record,)
        )

        self.assertIs(dataset.records[0].source_reference, source)
        self.assertEqual(source, {"sequence": "source-value"})


if __name__ == "__main__":
    unittest.main()
