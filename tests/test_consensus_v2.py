from dataclasses import FrozenInstanceError
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import DecisionReason, build_pair_consensus
from core.consensus_v2 import (
    ConfidenceLevel,
    ConsensusV2DecisionReason,
    EvidenceContext,
    SelectedSource,
    build_pair_consensus_v2,
)


def make_view(orientation, sequence, quality, filename):
    length = len(sequence)
    return AssemblyReadView(
        source_filename=filename,
        orientation=orientation,
        sequence=sequence,
        quality=quality,
        assembly_to_trimmed_index=range(length),
        assembly_to_raw_index=range(100, 100 + length),
        assembly_to_raw_trace_position=range(1000, 1000 + length),
        assembly_to_trimmed_trace_position=range(10, 10 * (length + 1), 10),
    )


def make_alignment(forward_sequence, forward_quality, reverse_sequence, reverse_quality, columns):
    forward = make_view(ReadOrientation.FORWARD, forward_sequence, forward_quality, "F.ab1")
    reverse = make_view(ReadOrientation.REVERSE, reverse_sequence, reverse_quality, "R.ab1")
    return PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(
                index,
                None if forward_index is None else forward.coordinate_at(forward_index),
                None if reverse_index is None else reverse.coordinate_at(reverse_index),
            )
            for index, (forward_index, reverse_index) in enumerate(columns)
        ],
    )


class PairConsensusV2Tests(unittest.TestCase):
    def test_two_sided_agreement_combines_sub_q20_evidence(self):
        result = build_pair_consensus_v2(
            make_alignment("A", [18], "A", [17], [(0, 0)])
        )

        decision = result.decisions[0]
        self.assertEqual(result.sequence, "A")
        self.assertEqual(decision.reason, ConsensusV2DecisionReason.TWO_SIDED_AGREEMENT)
        self.assertEqual(decision.evidence_context, EvidenceContext.TWO_SIDED_AGREEMENT)
        self.assertEqual(decision.confidence_level, ConfidenceLevel.MODERATE)
        self.assertEqual(decision.selected_source, SelectedSource.BOTH)
        self.assertEqual(decision.quality_difference, 1.0)
        self.assertGreater(decision.evidence_margin, 0)

    def test_extreme_low_quality_agreement_remains_unresolved(self):
        result = build_pair_consensus_v2(
            make_alignment("A", [2], "A", [3], [(0, 0)])
        )

        decision = result.decisions[0]
        self.assertEqual(result.sequence, "N")
        self.assertEqual(
            decision.reason, ConsensusV2DecisionReason.TWO_SIDED_AGREEMENT_LOW_CONFIDENCE
        )
        self.assertEqual(decision.confidence_level, ConfidenceLevel.UNRESOLVED)
        self.assertEqual(decision.selected_source, SelectedSource.NONE)

    def test_conflict_selects_higher_quality_forward_without_v1_difference_gate(self):
        result = build_pair_consensus_v2(
            make_alignment("A", [40], "G", [39], [(0, 0)])
        )

        decision = result.decisions[0]
        self.assertEqual(result.sequence, "A")
        self.assertEqual(decision.reason, ConsensusV2DecisionReason.HIGHER_QUALITY_FORWARD)
        self.assertEqual(decision.selected_source, SelectedSource.FORWARD)
        self.assertEqual(decision.evidence_context, EvidenceContext.TWO_SIDED_CONFLICT)
        self.assertEqual(decision.legacy_reason, DecisionReason.UNRESOLVED_CONFLICT)
        self.assertEqual(result.metrics.resolved_conflict_count, 1)

    def test_conflict_selects_higher_quality_reverse(self):
        result = build_pair_consensus_v2(
            make_alignment("A", [20], "G", [35], [(0, 0)])
        )

        self.assertEqual(result.sequence, "G")
        self.assertEqual(
            result.decisions[0].reason, ConsensusV2DecisionReason.HIGHER_QUALITY_REVERSE
        )

    def test_equal_quality_conflict_remains_unresolved(self):
        result = build_pair_consensus_v2(
            make_alignment("A", [30], "G", [30], [(0, 0)])
        )

        self.assertEqual(result.sequence, "N")
        self.assertEqual(
            result.decisions[0].reason, ConsensusV2DecisionReason.UNRESOLVED_CONFLICT_TIE
        )

    def test_one_sided_gap_and_iupac_keep_v1_outcomes(self):
        alignment = make_alignment(
            "AR",
            [35, 40],
            "AT",
            [35, 40],
            [(0, 0), (1, 1)],
        )
        v1 = build_pair_consensus(alignment)
        v2 = build_pair_consensus_v2(alignment)

        self.assertEqual(v1.sequence, v2.sequence)
        self.assertEqual(
            v2.decisions[1].reason,
            ConsensusV2DecisionReason.INHERITED_AMBIGUOUS_INPUT,
        )
        one_sided = make_alignment("AC", [35, 35], "A", [35], [(0, 0), (1, None)])
        self.assertEqual(build_pair_consensus_v2(one_sided).sequence, "AC")
        self.assertEqual(
            build_pair_consensus_v2(one_sided).decisions[1].reason,
            ConsensusV2DecisionReason.INHERITED_ONE_SIDED,
        )

    def test_v1_input_and_v2_result_are_immutable(self):
        alignment = make_alignment("A", [18], "A", [17], [(0, 0)])
        v1_before = build_pair_consensus(alignment)
        first = build_pair_consensus_v2(alignment)
        second = build_pair_consensus_v2(alignment)

        self.assertEqual(first, second)
        self.assertEqual(build_pair_consensus(alignment), v1_before)
        with self.assertRaises(FrozenInstanceError):
            first.sequence = "N"


if __name__ == "__main__":
    unittest.main()
