from types import SimpleNamespace
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus import build_pair_consensus
from tools.inspect_pair_consensus import (
    format_decision,
    format_pair_consensus_inspection,
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
    forward_view = make_view(ReadOrientation.FORWARD, "AC", [30, 40], "forward.ab1")
    reverse_view = make_view(ReadOrientation.REVERSE, "AG", [30, 20], "reverse.ab1")
    alignment = PairAlignment(
        forward_view=forward_view,
        reverse_view=reverse_view,
        columns=[
            AlignmentColumn(0, forward_view.coordinate_at(0), reverse_view.coordinate_at(0)),
            AlignmentColumn(1, forward_view.coordinate_at(1), reverse_view.coordinate_at(1)),
        ],
    )
    reads = (
        SimpleNamespace(filename="forward.ab1", sequence="AAC", trimmed_sequence="AC"),
        SimpleNamespace(filename="reverse.ab1", sequence="AAG", trimmed_sequence="AG"),
    )
    return reads, alignment, build_pair_consensus(alignment)


class PairConsensusInspectionTests(unittest.TestCase):
    def test_summary_includes_pair_alignment_and_consensus_metrics(self):
        (forward_read, reverse_read), alignment, consensus = make_fixture()

        text = format_pair_consensus_inspection(
            forward_read, reverse_read, alignment, consensus
        )

        self.assertIn("Pair Summary", text)
        self.assertIn("filename: forward.ab1", text)
        self.assertIn("alignment length: 2", text)
        self.assertIn("overlap length: 2", text)
        self.assertIn("identity: 50.00%", text)
        self.assertIn("conflict count: 1", text)
        self.assertIn("resolved conflicts: 1", text)
        self.assertIn("BOTH_AGREE: 1", text)
        self.assertIn("HIGHER_QUALITY_FORWARD: 1", text)
        self.assertIn("UNRESOLVED_CONFLICT: 0", text)

    def test_show_decisions_displays_all_evidence(self):
        (forward_read, reverse_read), alignment, consensus = make_fixture()

        text = format_pair_consensus_inspection(
            forward_read, reverse_read, alignment, consensus, show_decisions=True
        )

        self.assertIn("Column 0", text)
        self.assertIn("Column 1", text)
        self.assertIn("base=C", text)
        self.assertIn("Q=40", text)
        self.assertIn("HIGHER_QUALITY_FORWARD", text)

    def test_only_conflicts_excludes_both_agree_decisions(self):
        (forward_read, reverse_read), alignment, consensus = make_fixture()

        text = format_pair_consensus_inspection(
            forward_read, reverse_read, alignment, consensus, only_conflicts=True
        )

        self.assertNotIn("Column 0\n", text)
        self.assertIn("Column 1", text)
        self.assertIn("HIGHER_QUALITY_FORWARD", text)

    def test_individual_decision_formats_gap_as_explicit_gap(self):
        (forward_read, reverse_read), alignment, consensus = make_fixture()

        decision_text = format_decision(consensus.decisions[0])

        self.assertIn("Forward\nbase=A\nQ=30", decision_text)
        self.assertIn("Reverse\nbase=A\nQ=30", decision_text)
        self.assertIn("Consensus\nbase=A", decision_text)


if __name__ == "__main__":
    unittest.main()
