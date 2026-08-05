from datetime import datetime, timezone
import unittest

from core.consensus_review_bridge import ReviewEvidence
from core.human_review import DecisionType
from gui.multiple_consensus_viewer import create_human_review_decision


TIMESTAMP = datetime(2026, 8, 4, 15, 0, tzinfo=timezone.utc)


def make_evidence():
    return ReviewEvidence(
        sample_identifier="IK345",
        alignment_column=3,
        decision_reason="TWO_SIDED_AGREEMENT",
        consensus_base="A",
        v1_base=None,
        forward_read_identifier="IK345_F.ab1",
        forward_base="A",
        forward_quality=40.0,
        forward_raw_index=10,
        forward_trimmed_index=5,
        forward_raw_trace_position=100,
        forward_trimmed_trace_position=80,
        reverse_read_identifier="IK345_R.ab1",
        reverse_base="A",
        reverse_quality=35.0,
        reverse_raw_index=12,
        reverse_trimmed_index=6,
        reverse_raw_trace_position=120,
        reverse_trimmed_trace_position=90,
        forward_jump_target=None,
        reverse_jump_target=None,
    )


class MultipleConsensusHumanReviewTests(unittest.TestCase):
    def test_change_creates_a_separate_human_review_decision_with_evidence(self):
        evidence = make_evidence()
        decision = create_human_review_decision(
            sample_id="IK345",
            consensus_position=3,
            original_base="A",
            decision_type=DecisionType.CHANGE,
            reviewed_base="G",
            reason="Both chromatograms support G",
            evidence_reference=evidence,
            reviewer="reviewer",
            timestamp=TIMESTAMP,
        )

        self.assertEqual(decision.original_base, "A")
        self.assertEqual(decision.reviewed_base, "G")
        self.assertIs(decision.evidence_reference, evidence)
        self.assertEqual(decision.timestamp, TIMESTAMP)

    def test_accept_retains_the_selected_base(self):
        decision = create_human_review_decision(
            sample_id="IK345",
            consensus_position=3,
            original_base="A",
            decision_type=DecisionType.ACCEPT,
            reviewed_base="",
            reason="Evidence is accepted",
            evidence_reference=None,
            timestamp=TIMESTAMP,
        )

        self.assertEqual(decision.reviewed_base, "A")

    def test_gap_is_not_represented_as_a_human_review_decision(self):
        with self.assertRaisesRegex(ValueError, "original_base"):
            create_human_review_decision(
                sample_id="IK345",
                consensus_position=3,
                original_base="-",
                decision_type=DecisionType.CHANGE,
                reviewed_base="G",
                reason="A gap cannot be reviewed as a base",
                evidence_reference=None,
                timestamp=TIMESTAMP,
            )


if __name__ == "__main__":
    unittest.main()
