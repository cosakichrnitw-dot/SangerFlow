from datetime import datetime, timezone
import unittest

from core.consensus_review_session import ConsensusReviewSession
from core.human_review import DecisionType, HumanReviewDecision


TIMESTAMP = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def make_decision(decision_type: DecisionType) -> HumanReviewDecision:
    reviewed_base = {
        DecisionType.ACCEPT: "A",
        DecisionType.CHANGE: "G",
        DecisionType.AMBIGUOUS: "R",
        DecisionType.REJECT: None,
    }[decision_type]
    return HumanReviewDecision(
        sample_id="IK345",
        consensus_position=3,
        original_base="A",
        reviewed_base=reviewed_base,
        decision_type=decision_type,
        reason="review test",
        evidence_reference=None,
        reviewer="tester",
        timestamp=TIMESTAMP,
    )


class ConsensusReviewSessionTests(unittest.TestCase):
    def test_empty_session_has_no_decisions_or_changes(self):
        candidate_reference = object()
        session = ConsensusReviewSession(
            sample_id="IK345",
            candidate_reference=candidate_reference,
        )

        self.assertTrue(session.session_id)
        self.assertIs(session.candidate_reference, candidate_reference)
        self.assertEqual(session.get_decisions(), ())
        self.assertFalse(session.has_changes())

    def test_add_decision_and_get_decisions(self):
        session = ConsensusReviewSession(sample_id="IK345", candidate_reference=object())
        decision = make_decision(DecisionType.ACCEPT)

        session.add_decision(decision)

        self.assertEqual(session.get_decisions(), (decision,))
        self.assertIsNot(session.get_decisions(), session.decisions)

    def test_change_decision_marks_session_as_having_changes(self):
        session = ConsensusReviewSession(sample_id="IK345", candidate_reference=object())

        session.add_decision(make_decision(DecisionType.CHANGE))

        self.assertTrue(session.has_changes())

    def test_accept_only_session_has_no_changes(self):
        session = ConsensusReviewSession(sample_id="IK345", candidate_reference=object())

        session.add_decision(make_decision(DecisionType.ACCEPT))

        self.assertFalse(session.has_changes())


if __name__ == "__main__":
    unittest.main()
