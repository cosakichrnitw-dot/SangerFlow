"""Tests for reviewed-consensus dataset project registration."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from core.human_review import DecisionType, HumanReviewDecision, apply_review_decisions
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.project_reviewed_consensus import (
    add_reviewed_consensus_dataset_to_project,
)
from workflow.reviewed_consensus_dataset import create_dataset_from_reviewed_consensus


class ProjectReviewedConsensusAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate_dataset = SequenceDataset.from_sequence_pairs(
            dataset_id="candidate_coi",
            name="Consensus candidates",
            source_type=SourceType.CONSENSUS_CANDIDATE,
            sequences=(("IK345", "ATGC"),),
        )
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
        reviewed = apply_review_decisions("IK345", "ATGC", (decision,))
        self.reviewed_dataset = create_dataset_from_reviewed_consensus(
            reviewed,
            dataset_id="reviewed_coi",
            name="Reviewed COI",
            metadata={
                "consensus_method": "v2.1",
                "original_read_count": 2,
            },
        )
        self.project = Project.create("central_java", "Central Java").add_dataset(
            self.candidate_dataset
        )

    def test_registers_dataset_with_reviewed_consensus_derivation(self) -> None:
        updated = add_reviewed_consensus_dataset_to_project(
            self.project,
            self.reviewed_dataset,
            parent_dataset_id="candidate_coi",
            display_name="IK345 reviewed consensus",
            metadata={"note": "chromatogram reviewed"},
        )

        self.assertEqual(updated.dataset_ids, ("candidate_coi", "reviewed_coi"))
        self.assertIs(updated.get_dataset("reviewed_coi"), self.reviewed_dataset)
        entry = updated.get_entry("reviewed_coi")
        self.assertEqual(entry.display_name, "IK345 reviewed consensus")
        self.assertEqual(entry.parent_dataset_id, "candidate_coi")
        self.assertEqual(entry.derivation_type, DerivationType.REVIEWED_FROM_CONSENSUS)
        self.assertEqual(entry.metadata["created_by"], "Reviewed Consensus")
        self.assertEqual(entry.metadata["derivation_detail"], "REVIEWED_CONSENSUS")
        self.assertEqual(entry.metadata["consensus_method"], "v2.1")
        self.assertEqual(entry.metadata["original_read_count"], 2)
        self.assertEqual(entry.metadata["note"], "chromatogram reviewed")
        self.assertEqual(updated.lineage("reviewed_coi"), ("candidate_coi", "reviewed_coi"))

    def test_uses_parent_dataset_id_from_dataset_metadata(self) -> None:
        dataset = create_dataset_from_reviewed_consensus(
            apply_review_decisions(
                "IK345",
                "ATGC",
                (
                    HumanReviewDecision(
                        sample_id="IK345",
                        consensus_position=0,
                        original_base="A",
                        reviewed_base="A",
                        decision_type=DecisionType.ACCEPT,
                        reason="confirmed",
                        evidence_reference=None,
                        reviewer="researcher",
                        timestamp=datetime(2026, 8, 5, tzinfo=timezone.utc),
                    ),
                ),
            ),
            dataset_id="reviewed_with_parent",
            name="Reviewed with parent",
            metadata={"parent_dataset_id": "candidate_coi"},
        )

        updated = add_reviewed_consensus_dataset_to_project(self.project, dataset)

        self.assertEqual(
            updated.get_entry("reviewed_with_parent").parent_dataset_id,
            "candidate_coi",
        )

    def test_preserves_original_project_dataset_and_reviewed_consensus(self) -> None:
        original_dataset_metadata = dict(self.reviewed_dataset.metadata)
        original_sequence = self.reviewed_dataset.records[0].sequence

        updated = add_reviewed_consensus_dataset_to_project(
            self.project, self.reviewed_dataset, parent_dataset_id="candidate_coi"
        )

        self.assertEqual(self.project.dataset_ids, ("candidate_coi",))
        self.assertFalse(self.project.has_dataset("reviewed_coi"))
        self.assertEqual(self.reviewed_dataset.records[0].sequence, original_sequence)
        self.assertEqual(dict(self.reviewed_dataset.metadata), original_dataset_metadata)
        self.assertIs(updated.get_dataset("reviewed_coi"), self.reviewed_dataset)

    def test_rejects_invalid_inputs_and_missing_parent(self) -> None:
        with self.assertRaises(TypeError):
            add_reviewed_consensus_dataset_to_project(
                object(), self.reviewed_dataset, parent_dataset_id="candidate_coi"
            )
        with self.assertRaises(TypeError):
            add_reviewed_consensus_dataset_to_project(
                self.project, object(), parent_dataset_id="candidate_coi"
            )
        with self.assertRaises(ValueError):
            add_reviewed_consensus_dataset_to_project(
                self.project, self.candidate_dataset, parent_dataset_id="candidate_coi"
            )
        with self.assertRaises(ValueError):
            add_reviewed_consensus_dataset_to_project(self.project, self.reviewed_dataset)
        with self.assertRaises(ValueError):
            add_reviewed_consensus_dataset_to_project(
                self.project, self.reviewed_dataset, parent_dataset_id="unknown"
            )

    def test_rejects_duplicate_dataset_id(self) -> None:
        updated = add_reviewed_consensus_dataset_to_project(
            self.project, self.reviewed_dataset, parent_dataset_id="candidate_coi"
        )

        with self.assertRaises(ValueError):
            add_reviewed_consensus_dataset_to_project(
                updated, self.reviewed_dataset, parent_dataset_id="candidate_coi"
            )


if __name__ == "__main__":
    unittest.main()
