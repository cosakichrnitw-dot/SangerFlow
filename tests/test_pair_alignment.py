import copy
import unittest
import warnings

from core.assembly_models import AssemblyReadView, ReadOrientation
from core.pair_alignment import (
    AlignmentScoring,
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)


def make_view(sequence, orientation, raw_start):
    length = len(sequence)
    if orientation is ReadOrientation.FORWARD:
        order = list(range(length))
    else:
        order = list(range(length - 1, -1, -1))
    return AssemblyReadView(
        source_filename=f"{orientation.value}_{raw_start}.ab1",
        orientation=orientation,
        sequence=sequence,
        quality=[30] * length,
        assembly_to_trimmed_index=order,
        assembly_to_raw_index=[raw_start + index for index in order],
        assembly_to_raw_trace_position=[1000 + raw_start + index for index in order],
        assembly_to_trimmed_trace_position=[10 * index for index in order],
    )


def aligned_indexes(alignment):
    return [
        (column.forward_index, column.reverse_index)
        for column in alignment.columns
    ]


def paired_columns(alignment):
    return [
        column
        for column in alignment.columns
        if column.forward is not None and column.reverse is not None
    ]


class PairAlignmentTests(unittest.TestCase):
    def align(self, forward_sequence, reverse_sequence):
        return align_pair(
            make_view(forward_sequence, ReadOrientation.FORWARD, 10),
            make_view(reverse_sequence, ReadOrientation.REVERSE, 30),
        )

    def assert_complete_view_coverage(self, alignment):
        self.assertEqual(
            [column.forward_index for column in alignment.columns if column.forward],
            list(range(alignment.forward_view.length)),
        )
        self.assertEqual(
            [column.reverse_index for column in alignment.columns if column.reverse],
            list(range(alignment.reverse_view.length)),
        )

    def test_complete_match_preserves_coordinate_mapping(self):
        alignment = self.align("ACGT", "ACGT")

        self.assertEqual(aligned_indexes(alignment), [(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(alignment.columns[0].forward.raw_index, 10)
        self.assertEqual(alignment.columns[0].reverse.raw_index, 33)
        self.assertEqual(alignment.columns[0].reverse.raw_trace_position, 1033)
        self.assert_complete_view_coverage(alignment)

    def test_reverse_left_terminal_overhang_is_preserved(self):
        alignment = self.align("ACGT", "TTACGT")

        self.assertEqual(aligned_indexes(alignment)[:2], [(None, 0), (None, 1)])
        self.assertEqual(aligned_indexes(alignment)[2:], [(0, 2), (1, 3), (2, 4), (3, 5)])
        self.assert_complete_view_coverage(alignment)

    def test_forward_left_terminal_overhang_is_preserved(self):
        alignment = self.align("TTACGT", "ACGT")

        self.assertEqual(aligned_indexes(alignment)[:2], [(0, None), (1, None)])
        self.assertEqual(aligned_indexes(alignment)[2:], [(2, 0), (3, 1), (4, 2), (5, 3)])
        self.assert_complete_view_coverage(alignment)

    def test_forward_right_terminal_overhang_is_preserved(self):
        alignment = self.align("ACGTTT", "ACGT")

        self.assertEqual(aligned_indexes(alignment)[:4], [(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(aligned_indexes(alignment)[4:], [(4, None), (5, None)])
        self.assert_complete_view_coverage(alignment)

    def test_reverse_right_terminal_overhang_is_preserved(self):
        alignment = self.align("ACGT", "ACGTTT")

        self.assertEqual(aligned_indexes(alignment)[:4], [(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(aligned_indexes(alignment)[4:], [(None, 4), (None, 5)])
        self.assert_complete_view_coverage(alignment)

    def test_overlap_with_both_sides_terminal_regions(self):
        alignment = self.align("TTACGTAA", "GGACGTCC")

        self.assertEqual(
            [(column.forward_index, column.reverse_index) for column in paired_columns(alignment)],
            [(2, 2), (3, 3), (4, 4), (5, 5)],
        )
        self.assert_complete_view_coverage(alignment)

    def test_one_mismatch_remains_a_paired_alignment_column(self):
        alignment = self.align("ACGT", "ATGT")

        self.assertEqual(aligned_indexes(alignment), [(0, 0), (1, 1), (2, 2), (3, 3)])
        self.assertEqual(
            alignment.forward_view.sequence[alignment.columns[1].forward_index], "C"
        )
        self.assertEqual(
            alignment.reverse_view.sequence[alignment.columns[1].reverse_index], "T"
        )

    def test_single_internal_gap_is_retained_between_paired_columns(self):
        alignment = self.align("AACCGGTT", "AACGGTT")

        gap_indexes = [
            index
            for index, column in enumerate(alignment.columns)
            if column.forward is not None and column.reverse is None
        ]
        self.assertEqual(len(gap_indexes), 1)
        gap_index = gap_indexes[0]
        self.assertTrue(alignment.columns[gap_index - 1].forward and alignment.columns[gap_index - 1].reverse)
        self.assertTrue(alignment.columns[gap_index + 1].forward and alignment.columns[gap_index + 1].reverse)

    def test_consecutive_internal_gaps_are_retained(self):
        alignment = self.align("AACCCGGTT", "AACGGTT")

        gap_indexes = [
            index
            for index, column in enumerate(alignment.columns)
            if column.forward is not None and column.reverse is None
        ]
        self.assertEqual(len(gap_indexes), 2)
        self.assertEqual(gap_indexes, list(range(gap_indexes[0], gap_indexes[0] + 2)))
        self.assertTrue(alignment.columns[gap_indexes[0] - 1].reverse is not None)
        self.assertTrue(alignment.columns[gap_indexes[-1] + 1].reverse is not None)

    def test_repeated_sequence_tie_is_deterministic_and_warns(self):
        forward = make_view("ACAC", ReadOrientation.FORWARD, 10)
        reverse = make_view("AC", ReadOrientation.REVERSE, 30)

        with warnings.catch_warnings(record=True) as first_warnings:
            warnings.simplefilter("always")
            first = align_pair(forward, reverse)
        with warnings.catch_warnings(record=True) as second_warnings:
            warnings.simplefilter("always")
            second = align_pair(forward, reverse)

        self.assertEqual(aligned_indexes(first), aligned_indexes(second))
        self.assertTrue(
            any(issubclass(item.category, AmbiguousAlignmentWarning) for item in first_warnings)
        )
        self.assertTrue(
            any(issubclass(item.category, AmbiguousAlignmentWarning) for item in second_warnings)
        )

    def test_no_overlap_raises_dedicated_exception(self):
        with self.assertRaises(NoCredibleOverlapError):
            self.align("AAAA", "CCCC")

    def test_configured_minimum_overlap_rejects_an_extremely_short_match(self):
        forward = make_view("A", ReadOrientation.FORWARD, 10)
        reverse = make_view("A", ReadOrientation.REVERSE, 30)

        with self.assertRaises(NoCredibleOverlapError):
            align_pair(forward, reverse, AlignmentScoring(min_overlap_bases=2))

    def test_single_base_match_succeeds(self):
        alignment = self.align("A", "A")

        self.assertEqual(aligned_indexes(alignment), [(0, 0)])

    def test_single_base_mismatch_has_no_credible_overlap(self):
        with self.assertRaises(NoCredibleOverlapError):
            self.align("A", "G")

    def test_ambiguity_codes_are_valid_but_do_not_supply_match_evidence(self):
        alignment = self.align("NACG", "RACG")

        self.assert_complete_view_coverage(alignment)
        unambiguous_matches = [
            column
            for column in paired_columns(alignment)
            if (
                alignment.forward_view.sequence[column.forward_index] in "ACGT"
                and alignment.reverse_view.sequence[column.reverse_index] in "ACGT"
                and alignment.forward_view.sequence[column.forward_index]
                == alignment.reverse_view.sequence[column.reverse_index]
            )
        ]
        self.assertEqual(len(unambiguous_matches), 3)

    def test_invalid_orientation_is_rejected(self):
        forward = make_view("ACG", ReadOrientation.REVERSE, 10)
        reverse = make_view("ACG", ReadOrientation.REVERSE, 30)

        with self.assertRaisesRegex(ValueError, "forward_view orientation"):
            align_pair(forward, reverse)

    def test_invalid_base_is_rejected(self):
        forward = make_view("ACZ", ReadOrientation.FORWARD, 10)
        reverse = make_view("ACG", ReadOrientation.REVERSE, 30)

        with self.assertRaisesRegex(ValueError, "unsupported base"):
            align_pair(forward, reverse)

    def test_same_view_cannot_be_used_for_both_sides(self):
        view = make_view("ACG", ReadOrientation.FORWARD, 10)

        with self.assertRaisesRegex(ValueError, "same AssemblyReadView"):
            align_pair(view, view)

    def test_views_are_not_modified(self):
        forward = make_view("ACGT", ReadOrientation.FORWARD, 10)
        reverse = make_view("ACGT", ReadOrientation.REVERSE, 30)
        forward_before = copy.deepcopy(forward)
        reverse_before = copy.deepcopy(reverse)

        align_pair(forward, reverse)

        self.assertEqual(forward, forward_before)
        self.assertEqual(reverse, reverse_before)

    def test_gap_columns_keep_source_raw_coordinates(self):
        alignment = self.align("AACCGGTT", "AACGGTT")
        gap_column = next(
            column
            for column in alignment.columns
            if column.forward is not None and column.reverse is None
        )

        expected = alignment.forward_view.coordinate_at(
            gap_column.forward.assembly_index
        )
        self.assertEqual(gap_column.forward, expected)
        self.assertEqual(
            gap_column.forward.raw_trace_position,
            1000 + gap_column.forward.raw_index,
        )
        self.assert_complete_view_coverage(alignment)


if __name__ == "__main__":
    unittest.main()
