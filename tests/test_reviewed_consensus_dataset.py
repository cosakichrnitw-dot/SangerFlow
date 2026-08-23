"""Tests for converting immutable reviewed consensus values to datasets."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import unittest

from core.human_review import (
    DecisionType,
    HumanReviewDecision,
    ReviewedConsensus,
    apply_review_decisions,
)
from core.lineage import RecordProvenance, RecordRef
from core.sequence_dataset import SourceType
from workflow.reviewed_consensus_dataset import create_dataset_from_reviewed_consensus


def reviewed_result() -> ReviewedConsensus:
    decision = HumanReviewDecision(
        sample_id="IK345",
        consensus_position=3,
        original_base="C",
        reviewed_base="T",
        decision_type=DecisionType.CHANGE,
        reason="Both chromatograms support T",
        evidence_reference=None,
        reviewer="researcher",
        timestamp=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )
    return apply_review_decisions("IK345", "ATGC", (decision,))


class ReviewedConsensusDatasetTests(unittest.TestCase):
    def test_creates_reviewed_dataset_with_sequence_id_and_lineage_metadata(self) -> None:
        reviewed = reviewed_result()
        supplied_metadata = {
            "consensus_method": "consensus-v2.1-shadow",
            "original_read_count": 2,
            "marker": "COI",
        }

        dataset = create_dataset_from_reviewed_consensus(
            reviewed,
            dataset_id="ik345-reviewed",
            name="IK345 reviewed consensus",
            metadata=supplied_metadata,
        )
        supplied_metadata["marker"] = "changed"

        self.assertEqual(dataset.source_type, SourceType.REVIEWED_CONSENSUS)
        self.assertEqual(dataset.sequence_ids, ("IK345",))
        self.assertEqual(dataset.records[0].sequence, "ATGT")
        self.assertIs(dataset.records[0].source_reference, reviewed)
        self.assertTrue(dataset.metadata["reviewed"])
        self.assertEqual(dataset.metadata["source"], "Reviewed Consensus")
        self.assertEqual(dataset.metadata["consensus_method"], "consensus-v2.1-shadow")
        self.assertEqual(dataset.metadata["original_read_count"], 2)
        self.assertEqual(dataset.metadata["applied_decision_count"], 1)
        self.assertEqual(dataset.metadata["marker"], "COI")
        with self.assertRaises(TypeError):
            dataset.metadata["reviewed"] = False  # type: ignore[index]
        self.assertEqual(dataset.sequence_count, 1)
        dataset.validate_unique_ids()

    def test_rejects_invalid_type_unreviewed_value_and_invalid_sequence(self) -> None:
        with self.assertRaisesRegex(ValueError, "ReviewedConsensus"):
            create_dataset_from_reviewed_consensus(  # type: ignore[arg-type]
                object(), dataset_id="reviewed", name="Reviewed"
            )
        unreviewed = ReviewedConsensus("IK345", "ATGC", "ATGC", ())
        with self.assertRaisesRegex(ValueError, "at least one applied decision"):
            create_dataset_from_reviewed_consensus(
                unreviewed, dataset_id="reviewed", name="Reviewed"
            )

        invalid = reviewed_result()
        object.__setattr__(invalid, "reviewed_sequence", "ATGZ")
        with self.assertRaisesRegex(ValueError, "invalid DNA/IUPAC"):
            create_dataset_from_reviewed_consensus(
                invalid, dataset_id="reviewed", name="Reviewed"
            )

    def test_preserves_reviewed_value_and_returns_immutable_dataset(self) -> None:
        reviewed = reviewed_result()
        dataset = create_dataset_from_reviewed_consensus(
            reviewed,
            dataset_id="reviewed",
            name="Reviewed",
        )

        self.assertEqual(reviewed.original_sequence, "ATGC")
        self.assertEqual(reviewed.reviewed_sequence, "ATGT")
        self.assertEqual(dataset.records[0].sequence, "ATGT")
        self.assertIs(dataset.records[0].source_reference, reviewed)
        with self.assertRaises(FrozenInstanceError):
            dataset.name = "changed"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "original_read_count"):
            create_dataset_from_reviewed_consensus(
                reviewed,
                dataset_id="invalid-count",
                name="Invalid count",
                metadata={"original_read_count": -1},
            )

    def test_preserves_direct_forward_reverse_record_provenance(self) -> None:
        dataset = create_dataset_from_reviewed_consensus(
            reviewed_result(),
            dataset_id="reviewed",
            name="Reviewed",
            provenance=RecordProvenance(
                (
                    RecordRef("ab1-dataset", "IK345_F"),
                    RecordRef("ab1-dataset", "IK345_R"),
                )
            ),
        )

        self.assertEqual(
            dataset.records[0].provenance.source_records,
            (
                RecordRef("ab1-dataset", "IK345_F"),
                RecordRef("ab1-dataset", "IK345_R"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
