import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import build_pair_consensus
from core.consensus_v2 import build_pair_consensus_v2
from tools.compare_consensus_v1_v2 import (
    _CSV_COLUMNS,
    ConsensusComparison,
    comparison_rows,
    format_column,
    format_comparison,
    write_comparison_csv,
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


def make_comparison(forward_sequence, forward_quality, reverse_sequence, reverse_quality):
    forward = make_view(ReadOrientation.FORWARD, forward_sequence, forward_quality, "F.ab1")
    reverse = make_view(ReadOrientation.REVERSE, reverse_sequence, reverse_quality, "R.ab1")
    alignment = PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(index, forward.coordinate_at(index), reverse.coordinate_at(index))
            for index in range(len(forward_sequence))
        ],
    )
    return ConsensusComparison(
        "test-sample", alignment, build_pair_consensus(alignment), build_pair_consensus_v2(alignment)
    )


class CompareConsensusV1V2Tests(unittest.TestCase):
    def test_default_output_omits_unchanged_columns(self):
        comparison = make_comparison("A", [35], "A", [35])

        text = format_comparison(comparison)

        self.assertIn("Displayed columns: 0", text)
        self.assertIn("None", text)
        self.assertEqual(comparison_rows(comparison), [])

    def test_n_to_base_difference_includes_coordinates(self):
        comparison = make_comparison("A", [18], "A", [17])

        text = format_comparison(comparison)
        row = comparison_rows(comparison)[0]

        self.assertIn("column 0", text)
        self.assertIn("base = N", text)
        self.assertIn("base = A", text)
        self.assertIn("raw index 100", text)
        self.assertIn("trace position 1000", text)
        self.assertEqual(row["v1_base"], "N")
        self.assertEqual(row["v2_base"], "A")
        self.assertEqual(row["forward_raw_index"], 100)
        self.assertEqual(row["reverse_trace_position"], 1000)

    def test_conflict_adoption_is_visible_as_a_difference(self):
        comparison = make_comparison("A", [40], "G", [39])

        text = format_column(comparison, 0)

        self.assertEqual(comparison.v1_result.sequence, "N")
        self.assertEqual(comparison.v2_result.sequence, "A")
        self.assertIn("reason = UNRESOLVED_CONFLICT", text)
        self.assertIn("reason = HIGHER_QUALITY_FORWARD", text)

    def test_all_mode_and_csv_export(self):
        comparison = make_comparison("AA", [35, 18], "AA", [35, 17])

        self.assertEqual(len(comparison_rows(comparison, include_all=True)), 2)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "comparison.csv"
            row_count = write_comparison_csv(output, [comparison], include_all=True)
            with output.open(newline="") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(row_count, 2)
        self.assertEqual(tuple(rows[0]), _CSV_COLUMNS)
        self.assertEqual(rows[1]["v1_base"], "N")
        self.assertEqual(rows[1]["v2_base"], "A")


if __name__ == "__main__":
    unittest.main()
