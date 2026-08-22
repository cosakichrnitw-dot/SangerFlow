"""Tests for immutable BLAST-selection to SequenceDataset conversion."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.blast_filter import BlastResultSelection
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from core.lineage import RecordProvenance, RecordRef
from workflow.blast_selection_dataset import create_dataset_from_blast_selection


def make_source_dataset(*, blast_result_id: str | None = "coi-blast") -> SequenceDataset:
    metadata = {} if blast_result_id is None else {"blast_result_id": blast_result_id}
    return SequenceDataset(
        dataset_id="coi-trimmed",
        name="COI trimmed",
        source_type=SourceType.AB1_TRIMMED,
        records=(
            SequenceRecord("IK345", "ATGC"),
            SequenceRecord("IK346", "ATGT"),
            SequenceRecord("IK347", "ATGA"),
        ),
        metadata=metadata,
    )


class BlastSelectionDatasetTests(unittest.TestCase):
    def test_creates_dataset_in_selection_order_with_required_metadata(self) -> None:
        source = make_source_dataset()
        selection = BlastResultSelection("coi-blast", ("IK347", "IK345"), {"min_identity": 98.0})
        user_metadata = {"population": "Central Java"}

        subset = create_dataset_from_blast_selection(
            source,
            selection,
            dataset_id="coi-r-australiae",
            name="R. australiae COI",
            metadata=user_metadata,
        )
        user_metadata["population"] = "changed"

        self.assertEqual(subset.sequence_ids, ("IK347", "IK345"))
        self.assertEqual(tuple(record.sequence for record in subset.records), ("ATGA", "ATGC"))
        self.assertEqual(subset.metadata["source_dataset_id"], "coi-trimmed")
        self.assertEqual(subset.metadata["derived_from"], "BLAST_SELECTION")
        self.assertEqual(subset.metadata["blast_result_id"], "coi-blast")
        self.assertEqual(subset.metadata["selected_query_count"], 2)
        self.assertEqual(
            subset.get_record("IK347").provenance,
            RecordProvenance((RecordRef("coi-trimmed", "IK347"),)),
        )
        self.assertEqual(subset.metadata["population"], "Central Java")
        with self.assertRaises(TypeError):
            subset.metadata["population"] = "changed"  # type: ignore[index]
        self.assertEqual(source.sequence_ids, ("IK345", "IK346", "IK347"))
        self.assertEqual(selection.selected_query_ids, ("IK347", "IK345"))
        with self.assertRaises(FrozenInstanceError):
            subset.name = "changed"  # type: ignore[misc]

    def test_rejects_empty_wrong_mismatched_and_missing_selection_inputs(self) -> None:
        source = make_source_dataset()
        with self.assertRaisesRegex(ValueError, "at least one"):
            create_dataset_from_blast_selection(
                source, BlastResultSelection("coi-blast", ()), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            create_dataset_from_blast_selection(
                source, BlastResultSelection("other-blast", ("IK345",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "absent"):
            create_dataset_from_blast_selection(
                source, BlastResultSelection("coi-blast", ("missing",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "SequenceDataset"):
            create_dataset_from_blast_selection(  # type: ignore[arg-type]
                object(), BlastResultSelection("coi-blast", ("IK345",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "BlastResultSelection"):
            create_dataset_from_blast_selection(  # type: ignore[arg-type]
                source, object(), dataset_id="subset", name="Subset"
            )
