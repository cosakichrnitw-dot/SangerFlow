from types import SimpleNamespace
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import build_pair_consensus
from core.consensus_experimental import build_pair_consensus_v2_candidate
from tools.compare_consensus import (
    _BENCHMARK_COLUMNS,
    _benchmark_rows_for_candidate,
    _select_decisions,
    _transition_counts,
    format_comparison_decision,
    format_consensus_comparison,
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


def make_fixture():
    forward = make_view(ReadOrientation.FORWARD, "AG", [16, 30], "forward.ab1")
    reverse = make_view(ReadOrientation.REVERSE, "AG", [17, 30], "reverse.ab1")
    alignment = PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), reverse.coordinate_at(1)),
        ],
    )
    reads = (
        SimpleNamespace(filename="forward.ab1", sequence="AAG", trimmed_sequence="AG"),
        SimpleNamespace(filename="reverse.ab1", sequence="AAG", trimmed_sequence="AG"),
    )
    v1 = build_pair_consensus(alignment)
    candidate = build_pair_consensus_v2_candidate(alignment)
    return reads, alignment, v1, candidate


def make_gap_fixture():
    forward = make_view(ReadOrientation.FORWARD, "AG", [30, 30], "forward.ab1")
    reverse = make_view(ReadOrientation.REVERSE, "A", [30], "reverse.ab1")
    alignment = PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), None),
        ],
    )
    return alignment, build_pair_consensus_v2_candidate(alignment)


class ConsensusComparisonTests(unittest.TestCase):
    def test_default_summary_shows_proposals_without_shadow_changes(self):
        (forward_read, reverse_read), alignment, v1, candidate = make_fixture()

        text = format_consensus_comparison(
            forward_read, reverse_read, alignment, v1, candidate
        )

        self.assertIn("v1 N count: 1", text)
        self.assertIn("v2 two-sided agreement proposals: 1", text)
        self.assertIn("shadow sequence changes: 0", text)
        self.assertIn("N -> Base: 0", text)
        self.assertIn("Alignment column: 0", text)
        self.assertIn("proposed base=A", text)
        self.assertIn("winner=A", text)

    def test_selection_modes_distinguish_proposals_changes_all_and_columns(self):
        _, _, _, candidate = make_fixture()

        self.assertEqual(len(_select_decisions(candidate, "proposals", None)), 1)
        self.assertEqual(len(_select_decisions(candidate, "changes", None)), 0)
        self.assertEqual(len(_select_decisions(candidate, "all", None)), 2)
        self.assertEqual(
            [decision.alignment_index for decision in _select_decisions(candidate, "columns", [1])],
            [1],
        )

    def test_transition_summary_is_general_for_unchanged_shadow_result(self):
        _, _, _, candidate = make_fixture()

        transitions = _transition_counts(candidate)

        self.assertEqual(transitions["N_TO_BASE"], 0)
        self.assertEqual(transitions["BASE_TO_N"], 0)
        self.assertEqual(transitions["BASE_TO_DIFFERENT_BASE"], 0)
        self.assertEqual(transitions["N_TO_N"], 1)
        self.assertEqual(transitions["BASE_TO_BASE"], 1)

    def test_decision_format_marks_out_of_scope_evidence_unavailable(self):
        _, _, _, candidate = make_fixture()

        text = format_comparison_decision(candidate.decisions[1])

        self.assertIn("Alignment column: 1", text)
        self.assertIn("winner=unavailable", text)
        self.assertIn("changed_from_v1=False", text)

    def test_proposal_display_includes_traceable_coordinates(self):
        _, alignment, _, candidate = make_fixture()

        text = format_comparison_decision(candidate.decisions[0], alignment)

        self.assertIn("assembly index=0", text)
        self.assertIn("trimmed index=0", text)
        self.assertIn("raw index=100", text)
        self.assertIn("raw trace position=1000", text)

    def test_benchmark_rows_are_editable_and_use_raw_coordinates(self):
        _, alignment, _, candidate = make_fixture()

        rows = _benchmark_rows_for_candidate("known-sample", alignment, candidate)

        self.assertEqual(len(rows), 1)
        self.assertEqual(tuple(rows[0]), _BENCHMARK_COLUMNS)
        self.assertEqual(rows[0]["sample_id"], "known-sample")
        self.assertEqual(rows[0]["alignment_column"], 0)
        self.assertEqual(rows[0]["legacy_base"], "N")
        self.assertEqual(rows[0]["proposed_base"], "A")
        self.assertEqual(rows[0]["forward_raw_index"], 100)
        self.assertEqual(rows[0]["forward_raw_trace_position"], 1000)
        self.assertEqual(rows[0]["reverse_raw_index"], 100)
        self.assertEqual(rows[0]["reverse_raw_trace_position"], 1000)
        self.assertEqual(rows[0]["human_decision"], "")
        self.assertEqual(rows[0]["human_comment"], "")

    def test_gap_side_displays_none_coordinates(self):
        alignment, candidate = make_gap_fixture()

        text = format_comparison_decision(candidate.decisions[1], alignment)

        self.assertIn("Reverse: base=none, Q=-", text)
        self.assertIn("assembly index=None, trimmed index=None, raw index=None", text)


if __name__ == "__main__":
    unittest.main()
