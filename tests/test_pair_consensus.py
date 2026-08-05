import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import (
    ConsensusScoring,
    DecisionReason,
    build_pair_consensus,
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
    forward = make_view(
        ReadOrientation.FORWARD, forward_sequence, forward_quality, "forward.ab1"
    )
    reverse = make_view(
        ReadOrientation.REVERSE, reverse_sequence, reverse_quality, "reverse.ab1"
    )
    return PairAlignment(
        forward_view=forward,
        reverse_view=reverse,
        columns=[
            AlignmentColumn(
                alignment_index=index,
                forward=None if forward_index is None else forward.coordinate_at(forward_index),
                reverse=None if reverse_index is None else reverse.coordinate_at(reverse_index),
            )
            for index, (forward_index, reverse_index) in enumerate(columns)
        ],
    )


class PairConsensusTests(unittest.TestCase):
    def test_both_sides_agree(self):
        result = build_pair_consensus(
            make_alignment("A", [35], "A", [30], [(0, 0)])
        )

        self.assertEqual(result.sequence, "A")
        self.assertEqual(result.decisions[0].reason, DecisionReason.BOTH_AGREE)
        self.assertEqual(result.metrics.overlap_length, 1)
        self.assertEqual(result.metrics.overlap_identity, 1.0)

    def test_higher_quality_forward_resolves_conflict(self):
        result = build_pair_consensus(
            make_alignment("A", [40], "G", [20], [(0, 0)])
        )

        self.assertEqual(result.sequence, "A")
        self.assertEqual(
            result.decisions[0].reason, DecisionReason.HIGHER_QUALITY_FORWARD
        )
        self.assertEqual(result.metrics.conflict_count, 1)
        self.assertEqual(result.metrics.resolved_conflict_count, 1)

    def test_higher_quality_reverse_resolves_conflict(self):
        result = build_pair_consensus(
            make_alignment("A", [20], "G", [40], [(0, 0)])
        )

        self.assertEqual(result.sequence, "G")
        self.assertEqual(
            result.decisions[0].reason, DecisionReason.HIGHER_QUALITY_REVERSE
        )

    def test_small_quality_difference_leaves_conflict_unresolved(self):
        result = build_pair_consensus(
            make_alignment("A", [30], "G", [25], [(0, 0)])
        )

        self.assertEqual(result.sequence, "N")
        self.assertEqual(
            result.decisions[0].reason, DecisionReason.UNRESOLVED_CONFLICT
        )
        self.assertEqual(result.metrics.unresolved_base_count, 1)
        self.assertEqual(result.metrics.resolved_conflict_count, 0)

    def test_one_sided_forward_coverage(self):
        result = build_pair_consensus(
            make_alignment("AC", [35, 35], "A", [35], [(0, 0), (1, None)])
        )

        self.assertEqual(result.sequence, "AC")
        self.assertEqual(result.decisions[1].reason, DecisionReason.ONE_SIDED_FORWARD)
        self.assertEqual(result.metrics.one_sided_coverage_count, 1)

    def test_gap_on_forward_side_uses_reverse_evidence(self):
        result = build_pair_consensus(
            make_alignment("A", [35], "AT", [35, 35], [(0, 0), (None, 1)])
        )

        self.assertEqual(result.sequence, "AT")
        self.assertEqual(result.decisions[1].reason, DecisionReason.ONE_SIDED_REVERSE)

    def test_iupac_input_is_preserved_as_explicit_unresolved_evidence(self):
        result = build_pair_consensus(
            make_alignment("R", [40], "A", [40], [(0, 0)])
        )

        self.assertEqual(result.sequence, "N")
        self.assertEqual(result.decisions[0].reason, DecisionReason.AMBIGUOUS_INPUT)
        self.assertEqual(result.metrics.conflict_count, 1)
        self.assertEqual(result.metrics.unresolved_base_count, 1)

    def test_assembly_metrics_cover_overlap_conflict_and_one_sided_coverage(self):
        result = build_pair_consensus(
            make_alignment(
                "ACGT",
                [35, 40, 35, 35],
                "AGT",
                [35, 20, 35],
                [(0, 0), (1, 1), (2, None), (3, 2)],
            )
        )

        self.assertEqual(result.sequence, "ACGT")
        self.assertEqual(result.metrics.overlap_length, 3)
        self.assertAlmostEqual(result.metrics.overlap_identity, 2 / 3)
        self.assertEqual(result.metrics.conflict_count, 1)
        self.assertEqual(result.metrics.resolved_conflict_count, 1)
        self.assertEqual(result.metrics.unresolved_base_count, 0)
        self.assertEqual(result.metrics.one_sided_coverage_count, 1)

    def test_scoring_validates_non_negative_thresholds(self):
        with self.assertRaisesRegex(ValueError, "minimum_usable_quality"):
            ConsensusScoring(minimum_usable_quality=-1)


if __name__ == "__main__":
    unittest.main()
