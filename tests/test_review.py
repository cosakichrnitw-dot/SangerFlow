from dataclasses import FrozenInstanceError
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import ConsensusResult, build_pair_consensus
from core.review import (
    ReviewCriteria,
    ReviewReason,
    ReviewStatus,
    evaluate_pair_consensus,
)


def make_view(orientation, sequence, quality, name):
    length = len(sequence)
    return AssemblyReadView(
        source_filename=name,
        orientation=orientation,
        sequence=sequence,
        quality=quality,
        assembly_to_trimmed_index=range(length),
        assembly_to_raw_index=range(100, 100 + length),
        assembly_to_raw_trace_position=range(1000, 1000 + length),
        assembly_to_trimmed_trace_position=range(10, 10 * (length + 1), 10),
    )


def make_pair(forward_sequence, reverse_sequence, columns, forward_quality=None, reverse_quality=None):
    forward_quality = forward_quality or [35] * len(forward_sequence)
    reverse_quality = reverse_quality or [35] * len(reverse_sequence)
    forward = make_view(ReadOrientation.FORWARD, forward_sequence, forward_quality, "F.ab1")
    reverse = make_view(ReadOrientation.REVERSE, reverse_sequence, reverse_quality, "R.ab1")
    alignment = PairAlignment(
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
    return alignment, build_pair_consensus(alignment)


def permissive_criteria(**changes):
    values = dict(
        minimum_overlap_length=1,
        minimum_overlap_length_before_fail=0,
        minimum_overlap_identity=0.0,
        minimum_overlap_identity_before_fail=0.0,
        maximum_conflict_count_for_pass=100,
        maximum_conflict_count_before_fail=200,
        maximum_unresolved_base_count_for_pass=100,
        maximum_unresolved_base_count_before_fail=200,
        maximum_internal_gap_count_for_pass=100,
        maximum_internal_gap_count_before_fail=200,
        maximum_one_sided_coverage_fraction_for_pass=1.0,
        maximum_one_sided_coverage_fraction_before_fail=1.0,
        review_if_any_unresolved_base=False,
        review_if_any_internal_gap=False,
        review_if_resolved_conflicts_present=False,
        review_if_low_quality_consensus_bases_present=False,
    )
    values.update(changes)
    return ReviewCriteria(**values)


class ReviewEngineTests(unittest.TestCase):
    def test_perfect_match_passes(self):
        alignment, consensus = make_pair("ACGT", "ACGT", [(0, 0), (1, 1), (2, 2), (3, 3)])
        result = evaluate_pair_consensus(alignment, consensus, permissive_criteria(minimum_overlap_length=4))
        self.assertEqual(result.status, ReviewStatus.PASS)
        self.assertEqual(result.reasons, ())

    def test_sufficient_high_identity_overlap_passes(self):
        alignment, consensus = make_pair("ACGT", "ACGT", [(0, 0), (1, 1), (2, 2), (3, 3)])
        result = evaluate_pair_consensus(alignment, consensus, permissive_criteria(minimum_overlap_identity=1.0))
        self.assertEqual(result.status, ReviewStatus.PASS)

    def test_short_overlap_reviews_and_extremely_short_overlap_fails(self):
        alignment, consensus = make_pair("AC", "AC", [(0, 0), (1, 1)])
        review = evaluate_pair_consensus(alignment, consensus, permissive_criteria(minimum_overlap_length=3))
        failure = evaluate_pair_consensus(
            alignment,
            consensus,
            permissive_criteria(minimum_overlap_length=3, minimum_overlap_length_before_fail=3),
        )
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.OVERLAP_TOO_SHORT, review.reasons)
        self.assertEqual(failure.status, ReviewStatus.FAIL)

    def test_low_identity_reviews_and_very_low_identity_fails(self):
        alignment, consensus = make_pair("ACGT", "AGGT", [(0, 0), (1, 1), (2, 2), (3, 3)], [35] * 4, [35, 10, 35, 35])
        review = evaluate_pair_consensus(
            alignment, consensus, permissive_criteria(minimum_overlap_identity=0.80)
        )
        failure = evaluate_pair_consensus(
            alignment,
            consensus,
            permissive_criteria(minimum_overlap_identity=0.80, minimum_overlap_identity_before_fail=0.80),
        )
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.IDENTITY_TOO_LOW, review.reasons)
        self.assertEqual(failure.status, ReviewStatus.FAIL)

    def test_resolved_conflict_can_be_reviewed_or_allowed_by_criteria(self):
        alignment, consensus = make_pair("A", "G", [(0, 0)], [40], [20])
        review = evaluate_pair_consensus(alignment, consensus, permissive_criteria(maximum_conflict_count_for_pass=0))
        passed = evaluate_pair_consensus(alignment, consensus, permissive_criteria())
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.TOO_MANY_CONFLICTS, review.reasons)
        self.assertEqual(passed.status, ReviewStatus.PASS)

    def test_unresolved_base_reviews_and_many_unresolved_bases_fail(self):
        one_alignment, one_consensus = make_pair("A", "G", [(0, 0)], [30], [25])
        many_alignment, many_consensus = make_pair("AAA", "GGG", [(0, 0), (1, 1), (2, 2)], [30] * 3, [25] * 3)
        review = evaluate_pair_consensus(one_alignment, one_consensus, permissive_criteria(maximum_unresolved_base_count_for_pass=0))
        failure = evaluate_pair_consensus(
            many_alignment,
            many_consensus,
            permissive_criteria(maximum_unresolved_base_count_for_pass=0, maximum_unresolved_base_count_before_fail=2),
        )
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.UNRESOLVED_BASES_PRESENT, review.reasons)
        self.assertEqual(failure.status, ReviewStatus.FAIL)
        self.assertIn(ReviewReason.TOO_MANY_UNRESOLVED_BASES, failure.reasons)

    def test_one_internal_gap_reviews_and_multiple_events_fail(self):
        one_alignment, one_consensus = make_pair("ACGT", "AGT", [(0, 0), (1, None), (2, 1), (3, 2)])
        many_alignment, many_consensus = make_pair(
            "ACGTACG", "AGTAG", [(0, 0), (1, None), (2, 1), (3, 2), (4, None), (5, 3), (6, 4)]
        )
        review = evaluate_pair_consensus(one_alignment, one_consensus, permissive_criteria(maximum_internal_gap_count_for_pass=0))
        failure = evaluate_pair_consensus(
            many_alignment,
            many_consensus,
            permissive_criteria(maximum_internal_gap_count_for_pass=0, maximum_internal_gap_count_before_fail=1),
        )
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.INTERNAL_GAP_PRESENT, review.reasons)
        self.assertEqual(failure.status, ReviewStatus.FAIL)
        self.assertIn(ReviewReason.TOO_MANY_INTERNAL_GAPS, failure.reasons)
        self.assertEqual(failure.metrics.internal_gap_column_count, 2)
        self.assertEqual(failure.metrics.internal_gap_event_count, 2)

    def test_high_one_sided_coverage_reviews_and_extreme_fraction_fails(self):
        alignment, consensus = make_pair("ACGT", "AC", [(0, 0), (1, 1), (2, None), (3, None)])
        review = evaluate_pair_consensus(
            alignment,
            consensus,
            permissive_criteria(maximum_one_sided_coverage_fraction_for_pass=0.25),
        )
        failure = evaluate_pair_consensus(
            alignment,
            consensus,
            permissive_criteria(
                maximum_one_sided_coverage_fraction_for_pass=0.25,
                maximum_one_sided_coverage_fraction_before_fail=0.25,
            ),
        )
        self.assertEqual(review.status, ReviewStatus.REVIEW)
        self.assertIn(ReviewReason.ONE_SIDED_COVERAGE_HIGH, review.reasons)
        self.assertEqual(failure.status, ReviewStatus.FAIL)
        self.assertAlmostEqual(failure.metrics.one_sided_coverage_fraction, 0.5)

    def test_multiple_reasons_are_retained_and_fail_precedence_wins(self):
        alignment, consensus = make_pair("AC", "GG", [(0, 0), (1, 1)], [30, 30], [25, 25])
        result = evaluate_pair_consensus(
            alignment,
            consensus,
            permissive_criteria(
                minimum_overlap_length=3,
                minimum_overlap_length_before_fail=3,
                maximum_unresolved_base_count_for_pass=0,
            ),
        )
        self.assertEqual(result.status, ReviewStatus.FAIL)
        self.assertIn(ReviewReason.OVERLAP_TOO_SHORT, result.reasons)
        self.assertIn(ReviewReason.UNRESOLVED_BASES_PRESENT, result.reasons)

    def test_criteria_change_changes_deterministic_result(self):
        alignment, consensus = make_pair("AC", "AC", [(0, 0), (1, 1)])
        passed = evaluate_pair_consensus(alignment, consensus, permissive_criteria(minimum_overlap_length=2))
        reviewed = evaluate_pair_consensus(alignment, consensus, permissive_criteria(minimum_overlap_length=3))
        self.assertEqual(passed.status, ReviewStatus.PASS)
        self.assertEqual(reviewed.status, ReviewStatus.REVIEW)

    def test_rejects_empty_or_mismatched_consensus_input(self):
        alignment, consensus = make_pair("A", "A", [(0, 0)])
        empty = ConsensusResult("", (), consensus.metrics)
        mismatched = ConsensusResult("A", consensus.decisions, consensus.metrics)
        object.__setattr__(mismatched, "decisions", ())
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            evaluate_pair_consensus(alignment, empty, permissive_criteria())
        with self.assertRaisesRegex(ValueError, "lengths differ"):
            evaluate_pair_consensus(alignment, mismatched, permissive_criteria())

    def test_rejects_decision_evidence_from_a_different_alignment(self):
        alignment, consensus = make_pair("A", "A", [(0, 0)])
        other_alignment, other_consensus = make_pair("G", "G", [(0, 0)])
        with self.assertRaisesRegex(ValueError, "does not match"):
            evaluate_pair_consensus(alignment, other_consensus, permissive_criteria())

    def test_inputs_are_immutable_and_results_are_deterministic(self):
        alignment, consensus = make_pair("AC", "AC", [(0, 0), (1, 1)])
        criteria = permissive_criteria()
        first = evaluate_pair_consensus(alignment, consensus, criteria)
        second = evaluate_pair_consensus(alignment, consensus, criteria)
        self.assertEqual(first, second)
        with self.assertRaises(FrozenInstanceError):
            alignment.columns = ()
        with self.assertRaises(FrozenInstanceError):
            consensus.sequence = "N"


if __name__ == "__main__":
    unittest.main()
