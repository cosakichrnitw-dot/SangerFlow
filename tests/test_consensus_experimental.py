from dataclasses import FrozenInstanceError
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import build_pair_consensus
from core.consensus_experimental import (
    ExperimentalConsensusParameters,
    ExperimentalDecisionReason,
    ExperimentalPromotionPolicy,
    build_pair_consensus_v2_candidate,
    evaluate_two_sided_agreement_candidate,
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


def make_alignment(forward_sequence, reverse_sequence, forward_quality, reverse_quality, columns):
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


class ExperimentalConsensusTests(unittest.TestCase):
    def test_combined_evidence_ranks_the_shared_base_first(self):
        evidence = evaluate_two_sided_agreement_candidate("A", 16, "A", 17)

        self.assertEqual(evidence.winner_base, "A")
        self.assertNotEqual(evidence.runner_up_base, "A")
        self.assertGreater(evidence.evidence_margin, 0)
        self.assertGreater(
            evidence.scores_by_base["A"], evidence.scores_by_base["C"]
        )

    def test_evidence_rejects_conflicts_iupac_and_invalid_quality(self):
        with self.assertRaisesRegex(ValueError, "equal"):
            evaluate_two_sided_agreement_candidate("A", 16, "G", 17)
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            evaluate_two_sided_agreement_candidate("R", 16, "R", 17)
        with self.assertRaisesRegex(ValueError, "greater than or equal"):
            evaluate_two_sided_agreement_candidate("A", -1, "A", 17)

    def test_default_shadow_keeps_v1_sequence_but_exposes_proposed_base(self):
        alignment = make_alignment("A", "A", [16], [17], [(0, 0)])
        v1 = build_pair_consensus(alignment)
        shadow = build_pair_consensus_v2_candidate(alignment)

        self.assertEqual(v1.sequence, "N")
        self.assertEqual(shadow.v1_result, v1)
        self.assertEqual(shadow.candidate_sequence, "N")
        self.assertEqual(shadow.decisions[0].proposed_base, "A")
        self.assertEqual(
            shadow.decisions[0].reason,
            ExperimentalDecisionReason.TWO_SIDED_AGREEMENT_COMBINED,
        )
        self.assertEqual(shadow.changed_positions, ())

    def test_explicit_benchmark_policy_can_promote_an_eligible_shadow_base(self):
        alignment = make_alignment("A", "A", [16], [17], [(0, 0)])
        parameters = ExperimentalConsensusParameters(
            promotion_policy=ExperimentalPromotionPolicy(
                minimum_individual_quality=10,
                minimum_evidence_margin=1,
            )
        )

        shadow = build_pair_consensus_v2_candidate(alignment, parameters)

        self.assertEqual(shadow.v1_result.sequence, "N")
        self.assertEqual(shadow.candidate_sequence, "A")
        self.assertEqual(shadow.changed_positions, (0,))

    def test_out_of_scope_columns_are_identical_to_v1(self):
        alignment = make_alignment("AG", "AG", [30, 16], [30, 17], [(0, 0), (1, 1)])
        shadow = build_pair_consensus_v2_candidate(alignment)

        self.assertEqual(shadow.candidate_sequence, shadow.v1_result.sequence)
        self.assertEqual(shadow.decisions[0].proposed_base, None)
        self.assertEqual(
            shadow.decisions[0].reason,
            ExperimentalDecisionReason.OUT_OF_SCOPE_V1_UNCHANGED,
        )
        self.assertEqual(shadow.decisions[1].proposed_base, "G")

    def test_inputs_and_shadow_results_are_immutable_and_deterministic(self):
        alignment = make_alignment("A", "A", [16], [17], [(0, 0)])
        first = build_pair_consensus_v2_candidate(alignment)
        second = build_pair_consensus_v2_candidate(alignment)

        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            first.candidate_sequence = "A"
        self.assertEqual(build_pair_consensus(alignment).sequence, "N")


if __name__ == "__main__":
    unittest.main()
