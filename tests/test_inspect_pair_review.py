from types import SimpleNamespace
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import build_pair_consensus
from core.review import ReviewCriteria, evaluate_pair_consensus
from tools.inspect_pair_review import format_pair_review_inspection


def make_view(orientation, sequence, filename):
    length = len(sequence)
    return AssemblyReadView(
        source_filename=filename,
        orientation=orientation,
        sequence=sequence,
        quality=[35] * length,
        assembly_to_trimmed_index=range(length),
        assembly_to_raw_index=range(100, 100 + length),
        assembly_to_raw_trace_position=range(1000, 1000 + length),
        assembly_to_trimmed_trace_position=range(10, 10 * (length + 1), 10),
    )


def make_review_result():
    forward = make_view(ReadOrientation.FORWARD, "AC", "forward.ab1")
    reverse = make_view(ReadOrientation.REVERSE, "AC", "reverse.ab1")
    alignment = PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), reverse.coordinate_at(1)),
        ],
    )
    consensus = build_pair_consensus(alignment)
    criteria = ReviewCriteria(
        minimum_overlap_length=3,
        minimum_overlap_length_before_fail=0,
        minimum_overlap_identity=0.95,
        minimum_overlap_identity_before_fail=0.80,
    )
    reads = (
        SimpleNamespace(filename="forward.ab1", sequence="AAC", trimmed_sequence="AC"),
        SimpleNamespace(filename="reverse.ab1", sequence="AAC", trimmed_sequence="AC"),
    )
    return reads, evaluate_pair_consensus(alignment, consensus, criteria)


class PairReviewInspectionTests(unittest.TestCase):
    def test_summary_shows_status_reasons_metrics_and_criteria(self):
        (forward_read, reverse_read), result = make_review_result()

        text = format_pair_review_inspection(forward_read, reverse_read, result)

        self.assertIn("Pair Review Summary", text)
        self.assertIn("status: REVIEW", text)
        self.assertIn("reasons: OVERLAP_TOO_SHORT", text)
        self.assertIn("consensus length: 2", text)
        self.assertIn("overlap identity: 100.00%", text)
        self.assertIn("minimum overlap length: 3", text)
        self.assertIn("evaluation source: AUTOMATED", text)

    def test_summary_marks_runtime_ambiguity_as_not_used_by_review_engine(self):
        (forward_read, reverse_read), result = make_review_result()

        text = format_pair_review_inspection(
            forward_read, reverse_read, result, ambiguity_warning=True
        )

        self.assertIn("alignment ambiguity warning during this run: yes", text)
        self.assertIn("not persisted or used by the current Review Engine", text)


if __name__ == "__main__":
    unittest.main()
