from datetime import datetime, timezone
import unittest

from core.human_review import (
    DecisionType,
    HumanReviewDecision,
    apply_review_decisions,
)


TIMESTAMP = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def decision(position, original, reviewed, decision_type):
    return HumanReviewDecision(
        sample_id="IK345",
        consensus_position=position,
        original_base=original,
        reviewed_base=reviewed,
        decision_type=decision_type,
        reason="Human chromatogram review",
        evidence_reference={"source": "ReviewEvidence"},
        reviewer="researcher",
        timestamp=TIMESTAMP,
    )


class HumanReviewTests(unittest.TestCase):
    def test_change_derives_reviewed_sequence_without_mutating_original(self):
        original = "ATGC"
        result = apply_review_decisions(
            "IK345",
            original,
            (decision(3, "C", "T", DecisionType.CHANGE),),
        )

        self.assertEqual(original, "ATGC")
        self.assertEqual(result.reviewed_sequence, "ATGT")
        self.assertEqual(result.applied_decisions[0].consensus_position, 3)

    def test_accept_keeps_sequence_unchanged_and_is_recorded(self):
        result = apply_review_decisions(
            "IK345",
            "ATGC",
            (decision(1, "T", "T", DecisionType.ACCEPT),),
        )

        self.assertEqual(result.reviewed_sequence, "ATGC")
        self.assertEqual(result.applied_decisions[0].decision_type, DecisionType.ACCEPT)

    def test_ambiguous_applies_iupac_base(self):
        result = apply_review_decisions(
            "IK345",
            "ATGC",
            (decision(2, "G", "R", DecisionType.AMBIGUOUS),),
        )

        self.assertEqual(result.reviewed_sequence, "ATRC")

    def test_reject_is_recorded_without_changing_or_removing_a_base(self):
        result = apply_review_decisions(
            "IK345",
            "ATGC",
            (decision(2, "G", None, DecisionType.REJECT),),
        )

        self.assertEqual(result.reviewed_sequence, "ATGC")
        self.assertEqual(len(result.applied_decisions), 1)
        self.assertIs(result.applied_decisions[0].decision_type, DecisionType.REJECT)

    def test_rejects_decision_that_does_not_match_original_candidate_base(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            apply_review_decisions(
                "IK345",
                "ATGC",
                (decision(2, "C", "T", DecisionType.CHANGE),),
            )

    def test_review_record_allows_an_empty_reason_and_a_proposed_gap(self):
        record = HumanReviewDecision(
            sample_id="IK345",
            consensus_position=2,
            original_base="G",
            reviewed_base="-",
            decision_type=DecisionType.CHANGE,
            reason="",
            evidence_reference=None,
            reviewer="matrix-cell-editor",
            timestamp=TIMESTAMP,
        )

        self.assertEqual(record.reviewed_base, "-")
        self.assertEqual(record.reason, "")


if __name__ == "__main__":
    unittest.main()
