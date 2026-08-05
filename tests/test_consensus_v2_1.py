import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus_v2_1 import (
    ConfidenceLevel,
    ConsensusV21DecisionReason,
    ConsensusV21Scoring,
    EvidenceContext,
    SelectedSource,
    build_pair_consensus_v2_1,
)


def make_view(orientation, sequence, quality):
    length = len(sequence)
    return AssemblyReadView(
        source_filename=f"{orientation.value}.ab1",
        orientation=orientation,
        sequence=sequence,
        quality=quality,
        assembly_to_trimmed_index=range(length),
        assembly_to_raw_index=range(100, 100 + length),
        assembly_to_raw_trace_position=range(1000, 1000 + length),
        assembly_to_trimmed_trace_position=range(10, 10 * (length + 1), 10),
    )


def make_alignment(forward_sequence, forward_quality, reverse_sequence, reverse_quality, columns):
    forward = make_view(ReadOrientation.FORWARD, forward_sequence, forward_quality)
    reverse = make_view(ReadOrientation.REVERSE, reverse_sequence, reverse_quality)
    return PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(
                alignment_index,
                None if forward_index is None else forward.coordinate_at(forward_index),
                None if reverse_index is None else reverse.coordinate_at(reverse_index),
            )
            for alignment_index, (forward_index, reverse_index) in enumerate(columns)
        ],
    )


class ConsensusV21Tests(unittest.TestCase):
    def test_two_sided_agreement_uses_both_low_but_non_extreme_reads(self):
        result = build_pair_consensus_v2_1(
            make_alignment("A", [16], "A", [17], [(0, 0)])
        )

        decision = result.decisions[0]
        self.assertEqual(result.consensus_sequence, "A")
        self.assertEqual(decision.decision_reason, ConsensusV21DecisionReason.TWO_SIDED_AGREEMENT)
        self.assertEqual(decision.selected_source, SelectedSource.BOTH)
        self.assertEqual(decision.confidence_level, ConfidenceLevel.MEDIUM)
        self.assertEqual(decision.evidence_context, EvidenceContext.OVERLAP)
        self.assertEqual(result.metrics.changed_from_v1_count, 1)
        self.assertEqual(result.metrics.total_columns, 1)
        self.assertEqual(result.metrics.agreement_count, 1)
        self.assertEqual(result.algorithm_version, "consensus-v2.1-shadow-0")

    def test_extreme_low_quality_agreement_is_unresolved(self):
        result = build_pair_consensus_v2_1(
            make_alignment("A", [2], "A", [3], [(0, 0)])
        )

        decision = result.decisions[0]
        self.assertEqual(result.consensus_sequence, "N")
        self.assertEqual(decision.decision_reason, ConsensusV21DecisionReason.INSUFFICIENT_EVIDENCE)
        self.assertEqual(decision.selected_source, SelectedSource.NONE)
        self.assertEqual(decision.confidence_level, ConfidenceLevel.LOW)

        relaxed = build_pair_consensus_v2_1(
            make_alignment("A", [2], "A", [3], [(0, 0)]),
            ConsensusV21Scoring(extreme_low_quality=1),
        )
        self.assertEqual(relaxed.consensus_sequence, "A")

    def test_conflicts_select_higher_quality_read_or_stay_unresolved_when_equal(self):
        forward = build_pair_consensus_v2_1(
            make_alignment("A", [40], "G", [35], [(0, 0)])
        )
        reverse = build_pair_consensus_v2_1(
            make_alignment("A", [35], "G", [40], [(0, 0)])
        )
        equal = build_pair_consensus_v2_1(
            make_alignment("A", [20], "G", [20], [(0, 0)])
        )

        self.assertEqual(forward.consensus_sequence, "A")
        self.assertEqual(
            forward.decisions[0].decision_reason,
            ConsensusV21DecisionReason.HIGHER_QUALITY_FORWARD,
        )
        self.assertEqual(reverse.consensus_sequence, "G")
        self.assertEqual(
            reverse.decisions[0].decision_reason,
            ConsensusV21DecisionReason.HIGHER_QUALITY_REVERSE,
        )
        self.assertEqual(equal.consensus_sequence, "N")
        self.assertEqual(
            equal.decisions[0].decision_reason,
            ConsensusV21DecisionReason.UNRESOLVED_CONFLICT,
        )

    def test_terminal_one_sided_uses_legacy_conservative_policy(self):
        result = build_pair_consensus_v2_1(
            make_alignment("AC", [35, 35], "A", [35], [(0, 0), (1, None)])
        )

        decision = result.decisions[1]
        self.assertEqual(result.consensus_sequence, "AC")
        self.assertEqual(decision.decision_reason, ConsensusV21DecisionReason.ONE_SIDED_FORWARD)
        self.assertEqual(decision.evidence_context, EvidenceContext.TERMINAL_ONE_SIDED_FORWARD)

    def test_internal_gap_and_iupac_use_legacy_conservative_policy(self):
        gap = build_pair_consensus_v2_1(
            make_alignment("ACG", [35, 35, 35], "AG", [35, 35], [(0, 0), (1, None), (2, 1)])
        )
        iupac = build_pair_consensus_v2_1(
            make_alignment("R", [40], "A", [40], [(0, 0)])
        )

        self.assertEqual(gap.consensus_sequence, "ACG")
        self.assertEqual(
            gap.decisions[1].evidence_context, EvidenceContext.INTERNAL_GAP_FORWARD
        )
        self.assertEqual(gap.decisions[1].decision_reason, ConsensusV21DecisionReason.ONE_SIDED_FORWARD)
        self.assertEqual(iupac.consensus_sequence, "N")
        self.assertEqual(iupac.decisions[0].decision_reason, ConsensusV21DecisionReason.AMBIGUOUS_INPUT)
        self.assertEqual(iupac.decisions[0].evidence_context, EvidenceContext.IUPAC_AMBIGUITY)


if __name__ == "__main__":
    unittest.main()
