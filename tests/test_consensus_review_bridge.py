from pathlib import Path
import unittest

from core.ab1_reader import read_ab1
from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from core.consensus_review_bridge import create_review_evidence
from core.consensus_v2_1 import build_pair_consensus_v2_1
from core.pair_alignment import align_pair
from core.trimming import trim_sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


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


def make_terminal_gap_alignment():
    forward = make_view(ReadOrientation.FORWARD, "AC", [35, 35], "forward.ab1")
    reverse = make_view(ReadOrientation.REVERSE, "A", [35], "reverse.ab1")
    return PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), None),
        ],
    )


class ConsensusReviewBridgeTests(unittest.TestCase):
    def test_known_validation_pair_preserves_both_trace_coordinates(self):
        forward_read = read_ab1(
            REPOSITORY_ROOT / "validation_data" / "IK345_COl-1_F.ab1"
        )
        reverse_read = read_ab1(
            REPOSITORY_ROOT / "validation_data" / "IK345_COl-1_R.ab1"
        )
        trim_sequence(forward_read)
        trim_sequence(reverse_read)
        alignment = align_pair(
            build_forward_assembly_view(forward_read),
            build_reverse_assembly_view(reverse_read),
        )
        result = build_pair_consensus_v2_1(alignment)
        decision = result.decisions[628]
        column = alignment.column_at(628)

        evidence = create_review_evidence(
            decision, alignment, sample_identifier="IK345_COl-1", v1_base="N"
        )

        self.assertEqual(evidence.sample_identifier, "IK345_COl-1")
        self.assertEqual(evidence.forward_read_identifier, "IK345_COl-1_F.ab1")
        self.assertEqual(evidence.reverse_read_identifier, "IK345_COl-1_R.ab1")
        self.assertEqual(evidence.forward_raw_index, column.forward.raw_index)
        self.assertEqual(evidence.reverse_raw_index, column.reverse.raw_index)
        self.assertEqual(
            evidence.forward_raw_trace_position, column.forward.raw_trace_position
        )
        self.assertEqual(
            evidence.reverse_raw_trace_position, column.reverse.raw_trace_position
        )
        self.assertEqual(
            evidence.forward_jump_target.raw_trace_position,
            column.forward.raw_trace_position,
        )
        self.assertEqual(
            evidence.reverse_jump_target.raw_trace_position,
            column.reverse.raw_trace_position,
        )
        self.assertEqual(evidence.v1_base, "N")

    def test_gap_side_has_no_coordinates_or_jump_target(self):
        alignment = make_terminal_gap_alignment()
        decision = build_pair_consensus_v2_1(alignment).decisions[1]

        evidence = create_review_evidence(decision, alignment)

        self.assertEqual(evidence.forward_raw_trace_position, 1001)
        self.assertIsNotNone(evidence.forward_jump_target)
        self.assertIsNone(evidence.reverse_base)
        self.assertIsNone(evidence.reverse_quality)
        self.assertIsNone(evidence.reverse_raw_index)
        self.assertIsNone(evidence.reverse_trimmed_index)
        self.assertIsNone(evidence.reverse_raw_trace_position)
        self.assertIsNone(evidence.reverse_trimmed_trace_position)
        self.assertIsNone(evidence.reverse_jump_target)

    def test_rejects_decision_evidence_that_does_not_match_alignment(self):
        alignment = make_terminal_gap_alignment()
        decision = build_pair_consensus_v2_1(alignment).decisions[0]
        other_forward = make_view(ReadOrientation.FORWARD, "G", [35], "other_f.ab1")
        other_reverse = make_view(ReadOrientation.REVERSE, "G", [35], "other_r.ab1")
        other_alignment = PairAlignment(
            other_forward,
            other_reverse,
            [
                AlignmentColumn(
                    0,
                    other_forward.coordinate_at(0),
                    other_reverse.coordinate_at(0),
                )
            ],
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            create_review_evidence(decision, other_alignment)


if __name__ == "__main__":
    unittest.main()
