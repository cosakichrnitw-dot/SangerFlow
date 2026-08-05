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
from tools.compare_consensus_v1_v2 import ConsensusComparison
from tools.summarize_consensus_benchmark import (
    _OUTPUT_COLUMNS,
    build_benchmark_records,
    classify_region,
    format_summary,
    summarize_records,
    write_summary_csv,
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


def make_comparison():
    forward = make_view(ReadOrientation.FORWARD, "AA", [18, 40])
    reverse = make_view(ReadOrientation.REVERSE, "AG", [17, 39])
    alignment = PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), reverse.coordinate_at(1)),
        ],
    )
    return ConsensusComparison(
        "IK345_COl-1", alignment, build_pair_consensus(alignment), build_pair_consensus_v2(alignment)
    )


class ConsensusBenchmarkSummaryTests(unittest.TestCase):
    def test_summary_counts_types_and_undefined_recall(self):
        comparison = make_comparison()
        rows = (
            {
                "sample_id": "IK345_COl-1", "alignment_column": "0",
                "v1_base": "N", "v2_base": "A", "v1_reason": "LOW_QUALITY",
                "v2_reason": "TWO_SIDED_AGREEMENT", "human_decision": "ACCEPT",
                "human_comment": "",
            },
            {
                "sample_id": "IK345_COl-1", "alignment_column": "1",
                "v1_base": "N", "v2_base": "A", "v1_reason": "UNRESOLVED_CONFLICT",
                "v2_reason": "HIGHER_QUALITY_FORWARD", "human_decision": "KEEP_N",
                "human_comment": "",
            },
        )

        records = build_benchmark_records(rows, [comparison])
        summary = summarize_records(records)

        self.assertEqual(summary["total_v2_changes"], 2)
        self.assertEqual(summary["ACCEPT"], 1)
        self.assertEqual(summary["KEEP_N"], 1)
        self.assertEqual(summary["precision"], 0.5)
        self.assertIsNone(summary["recall"])
        self.assertEqual(summary["N_TO_BASE"], 2)
        self.assertEqual(summary["by_reason"]["TWO_SIDED_AGREEMENT"]["ACCEPT"], 1)
        self.assertEqual(summary["by_reason"]["HIGHER_QUALITY_FORWARD"]["KEEP_N"], 1)
        self.assertIn("recall: not calculable", format_summary(summary))
        self.assertEqual(records[0]["region_type"], "OVERLAP")
        self.assertEqual(records[0]["quality_difference"], 1.0)
        self.assertGreater(records[0]["evidence_margin"], 0)

    def test_region_classifies_terminal_and_internal_one_sided_columns(self):
        forward = make_view(ReadOrientation.FORWARD, "ABC", [30, 30, 30])
        reverse = make_view(ReadOrientation.REVERSE, "A", [30])
        terminal_alignment = PairAlignment(
            forward,
            reverse,
            [
                AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
                AlignmentColumn(1, forward.coordinate_at(1), None),
                AlignmentColumn(2, forward.coordinate_at(2), None),
            ],
        )
        comparison = type("Comparison", (), {"alignment": terminal_alignment})()

        self.assertEqual(classify_region(comparison, 1), "TERMINAL_ONE_SIDED_FORWARD")

        reverse_internal = make_view(ReadOrientation.REVERSE, "AC", [30, 30])
        internal_alignment = PairAlignment(
            forward,
            reverse_internal,
            [
                AlignmentColumn(0, forward.coordinate_at(0), reverse_internal.coordinate_at(0)),
                AlignmentColumn(1, forward.coordinate_at(1), None),
                AlignmentColumn(2, forward.coordinate_at(2), reverse_internal.coordinate_at(1)),
            ],
        )
        internal_comparison = type("Comparison", (), {"alignment": internal_alignment})()

        self.assertEqual(classify_region(internal_comparison, 1), "INTERNAL_GAP_FORWARD")

    def test_summary_csv_contains_quality_evidence_and_region_columns(self):
        comparison = make_comparison()
        rows = (
            {
                "sample_id": "IK345_COl-1", "alignment_column": "0",
                "v1_base": "N", "v2_base": "A", "v1_reason": "LOW_QUALITY",
                "v2_reason": "TWO_SIDED_AGREEMENT", "human_decision": "ACCEPT",
                "human_comment": "",
            },
        )
        records = build_benchmark_records(rows, [comparison])

        with TemporaryDirectory() as directory:
            output = Path(directory) / "benchmark_summary.csv"
            count = write_summary_csv(output, records)
            with output.open(newline="") as handle:
                written = list(csv.DictReader(handle))

        self.assertEqual(count, 1)
        self.assertEqual(tuple(written[0]), _OUTPUT_COLUMNS)
        self.assertEqual(written[0]["accept_or_keep"], "ACCEPT")
        self.assertEqual(written[0]["region_type"], "OVERLAP")


if __name__ == "__main__":
    unittest.main()
