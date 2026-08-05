import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadOrientation,
)
from core.consensus_v2_1 import build_pair_consensus_v2_1
from gui.consensus_viewer import (
    _chromatogram_base_color,
    _ruler_positions,
    _review_site_group,
    _sequence_x_to_consensus_position,
    _wheel_delta_to_scroll_steps,
    build_single_consensus_view_model,
    dispatch_trace_jump,
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


def make_alignment():
    forward = make_view(ReadOrientation.FORWARD, "AC", [16, 35], "forward.ab1")
    reverse = make_view(ReadOrientation.REVERSE, "AC", [17, 35], "reverse.ab1")
    return PairAlignment(
        forward,
        reverse,
        [
            AlignmentColumn(0, forward.coordinate_at(0), reverse.coordinate_at(0)),
            AlignmentColumn(1, forward.coordinate_at(1), reverse.coordinate_at(1)),
        ],
    )


class SingleConsensusViewerAdapterTests(unittest.TestCase):
    def test_view_model_preserves_sequence_status_and_review_evidence(self):
        alignment = make_alignment()
        result = build_pair_consensus_v2_1(alignment)

        model = build_single_consensus_view_model(
            "sample-1", alignment, result, v1_bases=("N", "C")
        )

        first = model.column_at(0)
        self.assertEqual(model.consensus_sequence, "AC")
        self.assertEqual(first.status, "TWO_SIDED_AGREEMENT")
        self.assertEqual(first.confidence_level, "MEDIUM")
        self.assertEqual(first.selected_source, "BOTH")
        self.assertEqual(first.review_evidence.v1_base, "N")
        self.assertEqual(first.review_evidence.forward_raw_index, 100)
        self.assertEqual(first.review_evidence.reverse_raw_trace_position, 1000)

    def test_trace_jump_dispatches_only_for_existing_target(self):
        alignment = make_alignment()
        model = build_single_consensus_view_model(
            "sample-1", alignment, build_pair_consensus_v2_1(alignment)
        )
        received = []

        jumped = dispatch_trace_jump(
            lambda read_identifier, trace_position: received.append(
                (read_identifier, trace_position)
            ),
            model.column_at(0).review_evidence.forward_jump_target,
        )

        self.assertTrue(jumped)
        self.assertEqual(received, [("forward.ab1", 1000)])
        self.assertFalse(dispatch_trace_jump(None, model.column_at(0).review_evidence.forward_jump_target))
        self.assertFalse(dispatch_trace_jump(lambda *_args: None, None))

    def test_canvas_click_coordinate_maps_to_the_alignment_column(self):
        character_width = 10
        self.assertEqual(
            _sequence_x_to_consensus_position(12, 3, character_width=character_width),
            0,
        )
        self.assertEqual(
            _sequence_x_to_consensus_position(21.9, 3, character_width=character_width),
            0,
        )
        self.assertEqual(
            _sequence_x_to_consensus_position(22, 3, character_width=character_width),
            1,
        )
        self.assertEqual(
            _sequence_x_to_consensus_position(35, 3, character_width=character_width),
            2,
        )
        self.assertIsNone(
            _sequence_x_to_consensus_position(11.9, 3, character_width=character_width)
        )
        self.assertIsNone(
            _sequence_x_to_consensus_position(42, 3, character_width=character_width)
        )

    def test_ruler_starts_at_one_and_uses_ten_base_intervals(self):
        self.assertEqual(_ruler_positions(1), (0,))
        self.assertEqual(_ruler_positions(10), (0, 9))
        self.assertEqual(_ruler_positions(25), (0, 9, 19))

    def test_trackpad_wheel_delta_maps_to_canvas_horizontal_steps(self):
        self.assertEqual(_wheel_delta_to_scroll_steps(0), 0)
        self.assertEqual(_wheel_delta_to_scroll_steps(1), -1)
        self.assertEqual(_wheel_delta_to_scroll_steps(-1), 1)
        self.assertEqual(_wheel_delta_to_scroll_steps(120), -1)
        self.assertEqual(_wheel_delta_to_scroll_steps(-240), 2)

    def test_base_colours_match_existing_chromatogram_conventions(self):
        self.assertEqual(_chromatogram_base_color("A"), "#E06666")
        self.assertEqual(_chromatogram_base_color("C"), "#7BC67B")
        self.assertEqual(_chromatogram_base_color("G"), "#F6E15A")
        self.assertEqual(_chromatogram_base_color("T"), "#6FA8DC")
        self.assertEqual(_chromatogram_base_color("N"), "#B7B7B7")

    def test_review_sites_are_prioritised_without_using_review_engine_status(self):
        self.assertEqual(_review_site_group("N", "LOW_QUALITY"), "needs-attention")
        self.assertEqual(
            _review_site_group("A", "HIGHER_QUALITY_FORWARD"),
            "conflict-resolved",
        )
        self.assertEqual(_review_site_group("A", "LOW_QUALITY"), "low-quality")
        self.assertEqual(
            _review_site_group("A", "ONE_SIDED_REVERSE"),
            "terminal-one-sided",
        )
        self.assertIsNone(_review_site_group("A", "TWO_SIDED_AGREEMENT"))


if __name__ == "__main__":
    unittest.main()
