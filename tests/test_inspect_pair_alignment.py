import unittest

from core.assembly_models import AssemblyReadView, ReadOrientation
from core.pair_alignment import align_pair
from tools.inspect_pair_alignment import (
    aligned_text,
    format_alignment,
    format_coordinate,
    summarize_alignment,
)


def make_view(sequence, orientation, raw_start):
    length = len(sequence)
    order = range(length) if orientation is ReadOrientation.FORWARD else range(length - 1, -1, -1)
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


class PairAlignmentInspectionTests(unittest.TestCase):
    def setUp(self):
        self.alignment = align_pair(
            make_view("AACCGGTT", ReadOrientation.FORWARD, 10),
            make_view("AACGGTT", ReadOrientation.REVERSE, 30),
        )

    def test_summary_distinguishes_overlap_gaps_and_terminal_overhang(self):
        summary = summarize_alignment(self.alignment)

        self.assertEqual(summary["alignment_length"], 8)
        self.assertEqual(summary["overlap_length"], 7)
        self.assertEqual(summary["unambiguous_match_count"], 7)
        self.assertEqual(summary["mismatch_count"], 0)
        self.assertEqual(summary["internal_gap_count"], 1)
        self.assertEqual(summary["forward_terminal_overhang_length"], 0)
        self.assertEqual(summary["reverse_terminal_overhang_length"], 0)
        self.assertEqual(summary["overlap_identity"], 100.0)

    def test_aligned_text_and_coordinate_output_are_human_readable(self):
        forward, marker, reverse = aligned_text(self.alignment)
        text = format_alignment(self.alignment, width=4)
        coordinate_text = format_coordinate(self.alignment, 2)

        self.assertEqual(forward, "AACCGGTT")
        self.assertEqual(reverse, "AA-CGGTT")
        self.assertEqual(marker, "|| |||||")
        self.assertIn("column     0-3", text)
        self.assertIn("Alignment column: 2", coordinate_text)
        self.assertIn("Forward: assembly index=2, raw index=12", coordinate_text)
        self.assertEqual(coordinate_text.splitlines()[2], "Reverse: gap")


if __name__ == "__main__":
    unittest.main()
