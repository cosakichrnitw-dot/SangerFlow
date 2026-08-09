"""Tests for the reviewed-consensus Project registration GUI action."""

from __future__ import annotations

from datetime import datetime, timezone
import unittest

from core.human_review import DecisionType, HumanReviewDecision, apply_review_decisions
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from gui.consensus_review_actions import (
    ConsensusReviewActionError,
    register_reviewed_consensus_in_project,
)


def _reviewed_consensus():
    decision = HumanReviewDecision(
        sample_id="IK345",
        consensus_position=2,
        original_base="G",
        reviewed_base="T",
        decision_type=DecisionType.CHANGE,
        reason="Trace confirmed",
        evidence_reference=None,
        reviewer="researcher",
        timestamp=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )
    return apply_review_decisions("IK345", "ATGC", (decision,))


class ConsensusReviewActionsTests(unittest.TestCase):
    def setUp(self) -> None:
        candidate = SequenceDataset.from_sequence_pairs(
            "candidate-coi",
            "Consensus Candidates",
            SourceType.CONSENSUS_CANDIDATE,
            (("IK345", "ATGC"),),
        )
        self.project = Project.create("project", "Project").add_dataset(candidate)
        self.reviewed = _reviewed_consensus()

    def test_registers_reviewed_dataset_and_notifies_application_owner(self) -> None:
        received = []
        updated = register_reviewed_consensus_in_project(
            self.project,
            self.reviewed,
            dataset_id="ik345-reviewed",
            name="IK345 Reviewed",
            parent_dataset_id="candidate-coi",
            metadata={"consensus_method": "v2.1", "original_read_count": 2},
            on_project_changed=received.append,
        )

        self.assertEqual(self.project.dataset_ids, ("candidate-coi",))
        self.assertEqual(updated.dataset_ids, ("candidate-coi", "ik345-reviewed"))
        self.assertEqual(received, [updated])
        dataset = updated.get_dataset("ik345-reviewed")
        self.assertEqual(dataset.records[0].sequence, "ATTC")
        self.assertEqual(dataset.metadata["parent_dataset_id"], "candidate-coi")
        self.assertEqual(
            updated.get_entry("ik345-reviewed").derivation_type,
            DerivationType.REVIEWED_FROM_CONSENSUS,
        )
        self.assertEqual(updated.lineage("ik345-reviewed"), ("candidate-coi", "ik345-reviewed"))

    def test_rejects_invalid_registration_without_changing_project(self) -> None:
        with self.assertRaises(ConsensusReviewActionError):
            register_reviewed_consensus_in_project(
                self.project,
                self.reviewed,
                dataset_id="reviewed",
                name="Reviewed",
                parent_dataset_id="missing",
            )
        self.assertEqual(self.project.dataset_ids, ("candidate-coi",))


if __name__ == "__main__":
    unittest.main()
