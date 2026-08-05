from datetime import datetime, timezone
import unittest

from core.consensus_review_session import ConsensusReviewSession
from core.human_review import DecisionType, HumanReviewDecision
from core.reviewed_consensus import ReviewedConsensus, build_reviewed_consensus


TIMESTAMP = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def decision(position, original, reviewed, decision_type):
    return HumanReviewDecision(
        sample_id="IK345",
        consensus_position=position,
        original_base=original,
        reviewed_base=reviewed,
        decision_type=decision_type,
        reason="Human chromatogram review",
        evidence_reference=None,
        reviewer="researcher",
        timestamp=TIMESTAMP,
    )


def session_with(*decisions):
    return ConsensusReviewSession(
        sample_id="IK345",
        candidate_reference=object(),
        decisions=list(decisions),
    )


class ReviewedConsensusTests(unittest.TestCase):
    def test_change_applies_the_session_decision(self):
        result = build_reviewed_consensus(
            "IK345",
            "ATGC",
            session_with(decision(3, "C", "T", DecisionType.CHANGE)),
        )

        self.assertIsInstance(result, ReviewedConsensus)
        self.assertEqual(result.reviewed_sequence, "ATGT")

    def test_accept_keeps_the_sequence_unchanged(self):
        result = build_reviewed_consensus(
            "IK345",
            "ATGC",
            session_with(decision(1, "T", "T", DecisionType.ACCEPT)),
        )

        self.assertEqual(result.reviewed_sequence, "ATGC")

    def test_ambiguous_applies_an_iupac_base(self):
        result = build_reviewed_consensus(
            "IK345",
            "ATGC",
            session_with(decision(0, "A", "R", DecisionType.AMBIGUOUS)),
        )

        self.assertEqual(result.reviewed_sequence, "RTGC")

    def test_reject_is_retained_without_changing_the_sequence(self):
        result = build_reviewed_consensus(
            "IK345",
            "ATGC",
            session_with(decision(2, "G", None, DecisionType.REJECT)),
        )

        self.assertEqual(result.reviewed_sequence, "ATGC")
        self.assertEqual(result.applied_decisions[0].decision_type, DecisionType.REJECT)

    def test_original_sequence_is_not_modified(self):
        original_sequence = "ATGC"
        result = build_reviewed_consensus(
            "IK345",
            original_sequence,
            session_with(decision(3, "C", "T", DecisionType.CHANGE)),
        )

        self.assertEqual(original_sequence, "ATGC")
        self.assertEqual(result.original_sequence, "ATGC")


if __name__ == "__main__":
    unittest.main()
