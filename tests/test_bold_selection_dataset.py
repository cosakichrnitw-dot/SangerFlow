"""Tests for immutable BOLD-selection to SequenceDataset conversion."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.bold_filter import BoldResultSelection
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from workflow.bold_selection_dataset import create_dataset_from_bold_selection


def make_source_dataset(*, bold_result_id: str | None = "coi-bold") -> SequenceDataset:
    metadata = {} if bold_result_id is None else {"bold_result_id": bold_result_id}
    taxonomy_reference = {"species_name": "Rhynchobatus australiae", "bin_uri": "BOLD:AAA001"}
    return SequenceDataset(
        dataset_id="coi-trimmed",
        name="COI trimmed",
        source_type=SourceType.AB1_TRIMMED,
        records=(
            SequenceRecord("IK345", "ATGC", source_reference=taxonomy_reference),
            SequenceRecord("IK346", "ATGT", source_reference={"species_name": "Dasyatis kuhlii"}),
            SequenceRecord("IK347", "ATGA"),
        ),
        metadata=metadata,
    )


class BoldSelectionDatasetTests(unittest.TestCase):
    def test_creates_dataset_in_selection_order_and_preserves_record_context(self) -> None:
        source = make_source_dataset()
        selection = BoldResultSelection("coi-bold", ("IK347", "IK345"), {"min_similarity": 98.0})
        user_metadata = {"population": "Central Java"}

        subset = create_dataset_from_bold_selection(
            source,
            selection,
            dataset_id="coi-r-australiae",
            name="R. australiae COI",
            metadata=user_metadata,
        )
        user_metadata["population"] = "changed"

        self.assertEqual(subset.sequence_ids, ("IK347", "IK345"))
        self.assertEqual(tuple(record.sequence for record in subset.records), ("ATGA", "ATGC"))
        self.assertIs(subset.get_record("IK345").source_reference, source.get_record("IK345").source_reference)
        self.assertEqual(subset.get_record("IK345").source_reference["bin_uri"], "BOLD:AAA001")
        self.assertEqual(subset.metadata["source_dataset_id"], "coi-trimmed")
        self.assertEqual(subset.metadata["derived_from"], "BOLD_SELECTION")
        self.assertEqual(subset.metadata["bold_result_id"], "coi-bold")
        self.assertEqual(subset.metadata["selected_query_count"], 2)
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
            create_dataset_from_bold_selection(
                source, BoldResultSelection("coi-bold", ()), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "does not match"):
            create_dataset_from_bold_selection(
                source, BoldResultSelection("other-bold", ("IK345",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "absent"):
            create_dataset_from_bold_selection(
                source, BoldResultSelection("coi-bold", ("missing",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "SequenceDataset"):
            create_dataset_from_bold_selection(  # type: ignore[arg-type]
                object(), BoldResultSelection("coi-bold", ("IK345",)), dataset_id="subset", name="Subset"
            )
        with self.assertRaisesRegex(ValueError, "BoldResultSelection"):
            create_dataset_from_bold_selection(  # type: ignore[arg-type]
                source, object(), dataset_id="subset", name="Subset"
            )
