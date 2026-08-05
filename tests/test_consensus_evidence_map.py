import unittest

from core.consensus_evidence_map import ConsensusEvidenceEntry, ConsensusEvidenceMap
from core.consensus_review_bridge import ReviewEvidence, TraceJumpTarget
from gui.multiple_consensus_viewer import (
    _evidence_text_for_selection,
    dispatch_multiple_evidence_trace_jump,
)


def make_evidence(sample_id="IK345"):
    return ReviewEvidence(
        sample_identifier=sample_id,
        alignment_column=3,
        decision_reason="TWO_SIDED_AGREEMENT",
        consensus_base="T",
        v1_base=None,
        forward_read_identifier=f"{sample_id}_F.ab1",
        forward_base="T",
        forward_quality=38.0,
        forward_raw_index=120,
        forward_trimmed_index=110,
        forward_raw_trace_position=1400,
        forward_trimmed_trace_position=1300,
        reverse_read_identifier=f"{sample_id}_R.ab1",
        reverse_base="T",
        reverse_quality=34.0,
        reverse_raw_index=140,
        reverse_trimmed_index=100,
        reverse_raw_trace_position=1500,
        reverse_trimmed_trace_position=1200,
        forward_jump_target=None,
        reverse_jump_target=None,
    )


class ConsensusEvidenceMapTests(unittest.TestCase):
    def test_lookup_returns_existing_evidence_by_sample_and_consensus_position(self):
        evidence = make_evidence()
        evidence_map = ConsensusEvidenceMap(
            (ConsensusEvidenceEntry("IK345", 2, evidence),)
        )

        self.assertIs(evidence_map.lookup("IK345", 2), evidence)
        self.assertIsNone(evidence_map.lookup("IK345", 3))

    def test_gap_position_never_performs_evidence_lookup(self):
        evidence_map = ConsensusEvidenceMap(
            (ConsensusEvidenceEntry("IK345", 2, make_evidence()),)
        )

        self.assertIsNone(evidence_map.lookup("IK345", None))
        self.assertEqual(
            _evidence_text_for_selection(evidence_map, "IK345", None),
            "Gap position has no chromatogram evidence.\n",
        )

    def test_evidence_panel_text_reads_forward_and_reverse_values_without_navigation(self):
        evidence_map = ConsensusEvidenceMap(
            (ConsensusEvidenceEntry("IK345", 2, make_evidence()),)
        )

        text = _evidence_text_for_selection(evidence_map, "IK345", 2)

        self.assertIn("Forward\nBase: T\nQuality: 38.0", text)
        self.assertIn("Reverse\nBase: T\nQuality: 34.0", text)
        self.assertIn("Raw trace position: 1400", text)

    def test_rejects_duplicate_sample_position_entries(self):
        evidence = make_evidence()
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ConsensusEvidenceMap(
                (
                    ConsensusEvidenceEntry("IK345", 2, evidence),
                    ConsensusEvidenceEntry("IK345", 2, evidence),
                )
            )

    def test_trace_jump_callback_receives_existing_raw_trace_position(self):
        received = []
        target = TraceJumpTarget("IK345_COl-1_F.ab1", 1400)

        dispatched = dispatch_multiple_evidence_trace_jump(
            lambda read_identifier, raw_trace_position: received.append(
                (read_identifier, raw_trace_position)
            ),
            target,
        )

        self.assertTrue(dispatched)
        self.assertEqual(received, [("IK345_COl-1_F.ab1", 1400)])

    def test_missing_callback_or_target_keeps_navigation_safe(self):
        self.assertFalse(dispatch_multiple_evidence_trace_jump(None, None))


if __name__ == "__main__":
    unittest.main()
