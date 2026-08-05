from types import SimpleNamespace
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from core.consensus_alignment import (
    AlignedConsensusSequence,
    AlignedConsensusSet,
    build_consensus_position_mapping,
)
from core.consensus_review_session import ConsensusReviewSession
from core.human_review import DecisionType
from gui.multiple_consensus_viewer import (
    MultipleConsensusAlignmentWindow,
    _EDITED_CELL_BACKGROUND,
    _base_color,
    _format_review_summary,
    _format_variable_sites,
    _horizontal_fraction_for_column,
    _linear_cell_selection,
    _matrix_content_height,
    _matrix_coordinate_to_cell,
    _row_center_y,
    _row_top_y,
    _sample_label_text,
    _selected_site_summary,
    _editing_status_text,
    _wheel_delta_to_scroll_steps,
    build_variable_sites,
    build_edited_cells,
    build_multiple_alignment_view_model,
    create_matrix_edit_decision,
    current_alignment_records,
    reviewed_consensus_records,
    write_fasta_records,
)


def make_aligned_sequence(sample_id, original_sequence, aligned_sequence):
    return AlignedConsensusSequence(
        sample_id=sample_id,
        original_sequence=original_sequence,
        aligned_sequence=aligned_sequence,
        consensus_position_mapping=build_consensus_position_mapping(
            original_sequence,
            aligned_sequence,
        ),
    )


def make_aligned_consensus_set():
    sequences = (
        make_aligned_sequence("IK345", "ATGCN", "ATG-CN"),
        make_aligned_sequence("IK346", "ATGTAN", "ATGTAN"),
        make_aligned_sequence("IK347", "ATGTGN", "ATGTGN"),
    )
    gap_count = sum(sequence.aligned_sequence.count("-") for sequence in sequences)
    return AlignedConsensusSet(
        sequences=sequences,
        alignment_length=6,
        gap_count=gap_count,
        gap_percentage=(gap_count / (6 * len(sequences))) * 100.0,
        alignment_id="test-mafft-result",
    )


def make_internal_and_terminal_gap_set():
    sequences = (
        make_aligned_sequence("IK345", "ATGCCAA", "ATGC-CAA"),
        make_aligned_sequence("IK346", "ATGTCAA", "ATGTCAA-"),
    )
    gap_count = sum(sequence.aligned_sequence.count("-") for sequence in sequences)
    return AlignedConsensusSet(
        sequences=sequences,
        alignment_length=8,
        gap_count=gap_count,
        gap_percentage=(gap_count / (8 * len(sequences))) * 100.0,
    )


class MultipleConsensusViewerAdapterTests(unittest.TestCase):
    def test_builds_rows_from_aligned_consensus_set_with_gap_aware_mapping(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())

        self.assertEqual(model.alignment_length, 6)
        self.assertEqual(model.alignment_id, "test-mafft-result")
        self.assertEqual(model.row_at(0).sample_id, "IK345")
        self.assertEqual(
            model.row_at(0).consensus_position_by_column,
            (0, 1, 2, None, 3, 4),
        )
        self.assertEqual(model.row_at(1).consensus_position_at(5), 5)

    def test_preserves_internal_and_terminal_gaps_from_aligned_consensus_set(self):
        model = build_multiple_alignment_view_model(make_internal_and_terminal_gap_set())

        self.assertEqual(model.row_at(0).aligned_sequence, "ATGC-CAA")
        self.assertEqual(model.row_at(1).aligned_sequence, "ATGTCAA-")
        self.assertEqual(model.alignment_length, 8)
        self.assertIsNone(model.row_at(0).consensus_position_at(4))
        self.assertEqual(model.row_at(0).consensus_position_at(5), 4)
        self.assertIsNone(model.row_at(1).consensus_position_at(7))

    def test_variable_columns_are_display_only_summaries(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())

        self.assertFalse(model.column_at(0).is_variable)
        self.assertTrue(model.column_at(3).is_variable)
        self.assertTrue(model.column_at(4).is_variable)
        self.assertEqual(model.column_at(4).base_counts, (("A", 1), ("C", 1), ("G", 1)))

    def test_variable_site_panel_entries_keep_base_and_gap_aware_positions(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())
        sites = build_variable_sites(model)

        self.assertEqual([site.alignment_column for site in sites], [3, 4])
        self.assertEqual(sites[0].samples[0].sample_id, "IK345")
        self.assertEqual(sites[0].samples[0].base, "-")
        self.assertIsNone(sites[0].samples[0].consensus_position)
        self.assertEqual(sites[1].samples[0].base, "C")
        self.assertEqual(sites[1].samples[0].consensus_position, 3)
        self.assertIn("Column 3 (0-based)", _format_variable_sites(sites))
        self.assertIn("IK345: -  consensus position: None", _format_variable_sites(sites))

    def test_variable_site_column_scrolls_only_when_outside_the_viewport(self):
        self.assertIsNone(
            _horizontal_fraction_for_column(
                5,
                alignment_length=100,
                viewport_width=180,
                current_xview=(0.0, 0.1),
            )
        )
        self.assertEqual(
            _horizontal_fraction_for_column(
                90,
                alignment_length=100,
                viewport_width=180,
                current_xview=(0.0, 0.1),
            ),
            0.855,
        )

    def test_long_aligned_sequences_are_retained_for_horizontal_rendering(self):
        sequence = "A" * 700
        aligned_sequences = (
            make_aligned_sequence("IK345", sequence, sequence),
            make_aligned_sequence("IK346", sequence, sequence),
        )
        model = build_multiple_alignment_view_model(
            AlignedConsensusSet(
                sequences=aligned_sequences,
                alignment_length=700,
                gap_count=0,
                gap_percentage=0.0,
            )
        )

        self.assertEqual(model.alignment_length, 700)
        self.assertEqual(model.row_at(0).consensus_position_at(699), 699)

    def test_base_colours_follow_mega_mesquite_style(self):
        self.assertEqual(_base_color("A"), "#E06666")
        self.assertEqual(_base_color("T"), "#6FA8DC")
        self.assertEqual(_base_color("G"), "#F6E15A")
        self.assertEqual(_base_color("C"), "#7BC67B")
        self.assertEqual(_base_color("N"), "#B7B7B7")
        self.assertEqual(_base_color("R"), "#B7B7B7")
        self.assertEqual(_base_color("-"), "#D9D9D9")
        self.assertEqual(_EDITED_CELL_BACKGROUND, "#DCEEFF")

    def test_canvas_click_coordinates_map_to_row_and_alignment_column(self):
        self.assertEqual(
            _matrix_coordinate_to_cell(
                37,
                46 + 22 + 3,
                row_count=3,
                alignment_length=10,
            ),
            (1, 2),
        )
        self.assertIsNone(
            _matrix_coordinate_to_cell(1, 20, row_count=3, alignment_length=10)
        )
        self.assertIsNone(
            _matrix_coordinate_to_cell(190, 50, row_count=3, alignment_length=10)
        )

    def test_shift_selection_is_limited_to_one_continuous_row_or_column(self):
        self.assertEqual(
            _linear_cell_selection((2, 4), (2, 6)),
            ((2, 4), (2, 5), (2, 6)),
        )
        self.assertEqual(
            _linear_cell_selection((1, 3), (3, 3)),
            ((1, 3), (2, 3), (3, 3)),
        )
        self.assertIsNone(_linear_cell_selection((1, 3), (3, 5)))

    def test_editing_status_uses_alignment_columns_and_escape_instruction(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())
        text = _editing_status_text(model, ((0, 1), (0, 2), (0, 3)))

        self.assertIn("Editing:", text)
        self.assertIn("Sample: IK345", text)
        self.assertIn("Alignment column: 1–3 (3 cells)", text)
        self.assertIn("ESC: cancel", text)

    def test_labels_and_matrix_rows_share_the_same_six_row_layout(self):
        # The label text centre and matrix base text centre use the same
        # geometry. Row 0 and row 5 cover the first and last validation rows.
        self.assertEqual(_row_top_y(0), 46)
        self.assertEqual(_row_center_y(0), 57)
        self.assertEqual(_row_top_y(5), 156)
        self.assertEqual(_row_center_y(5), 167)
        self.assertEqual(_matrix_content_height(6), 178)

    def test_selected_site_summary_keeps_gap_position_unavailable(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())
        gap_row = model.row_at(0)
        gap_summary = _selected_site_summary(
            gap_row.sample_id,
            3,
            gap_row.consensus_position_at(3),
            gap_row.aligned_sequence[3],
        )
        base_summary = _selected_site_summary("IK346", 3, 3, "T")

        self.assertIn("Consensus position: None (gap)", gap_summary)
        self.assertIn("Alignment column: 4 (1-based; internal 3)", base_summary)
        self.assertIn("Consensus position: 4 (1-based)", base_summary)

    def test_wheel_delta_has_deterministic_scroll_direction(self):
        self.assertEqual(_wheel_delta_to_scroll_steps(0), 0)
        self.assertEqual(_wheel_delta_to_scroll_steps(1), -1)
        self.assertEqual(_wheel_delta_to_scroll_steps(-1), 1)
        self.assertEqual(_wheel_delta_to_scroll_steps(120), -1)

    def test_shared_vertical_scroll_command_mirrors_matrix_fraction_to_labels(self):
        class MatrixCanvas:
            def __init__(self):
                self.yview_calls = []
                self.fraction = 0.0

            def yview(self, *args):
                if not args:
                    return self.fraction, self.fraction + 0.25
                self.yview_calls.append(args)
                if args[0] == "moveto":
                    self.fraction = float(args[1])
                elif args[0] == "scroll":
                    self.fraction = 0.375

        class LabelCanvas:
            def __init__(self):
                self.moveto_calls = []

            def yview_moveto(self, fraction):
                self.moveto_calls.append(fraction)

        class Scrollbar:
            def __init__(self):
                self.set_calls = []

            def set(self, first, last):
                self.set_calls.append((first, last))

        window = object.__new__(MultipleConsensusAlignmentWindow)
        matrix_canvas = MatrixCanvas()
        label_canvas = LabelCanvas()
        scrollbar = Scrollbar()
        window._matrix_canvas = matrix_canvas
        window._label_canvas = label_canvas
        window._vertical_scrollbar = scrollbar

        window._scroll_y("moveto", "0.5")
        window._scroll_y("scroll", -2, "units")

        expected_calls = [("moveto", "0.5"), ("scroll", -2, "units")]
        self.assertEqual(matrix_canvas.yview_calls, expected_calls)
        self.assertEqual(label_canvas.moveto_calls, [0.5, 0.375])
        self.assertEqual(scrollbar.set_calls, [(0.5, 0.75), (0.375, 0.625)])

    def test_initial_pane_sash_prefers_an_80_percent_matrix_without_overriding_user_resize(self):
        class Panes:
            def __init__(self):
                self.sash_calls = []

            def winfo_width(self):
                return 1600

            def sash_place(self, index, x, y):
                self.sash_calls.append((index, x, y))

        window = object.__new__(MultipleConsensusAlignmentWindow)
        window._workspace_panes = Panes()
        window._initial_sash_placed = False

        window._place_initial_sash()
        window._place_initial_sash()

        self.assertEqual(window._workspace_panes.sash_calls, [(0, 1280, 0)])
        self.assertTrue(window._initial_sash_placed)

    def test_sample_labels_include_the_one_based_alignment_row_number(self):
        self.assertEqual(_sample_label_text(0, "IK345_COl-1"), "1  IK345_COl-1")
        self.assertEqual(_sample_label_text(5, "IK350_COl-1"), "6  IK350_COl-1")

    def test_review_summary_is_empty_until_a_viewer_decision_exists(self):
        self.assertEqual(_format_review_summary(()), "No reviewed decisions.")

        summary = _format_review_summary(
            (
                SimpleNamespace(decision_type=DecisionType.CHANGE),
                SimpleNamespace(decision_type=DecisionType.CHANGE),
                SimpleNamespace(decision_type=DecisionType.ACCEPT),
            )
        )

        self.assertIn("Reviewed decisions:", summary)
        self.assertIn("CHANGE: 2", summary)
        self.assertIn("ACCEPT: 1", summary)

    def test_matrix_edit_records_a_change_in_a_sample_review_session(self):
        decision = create_matrix_edit_decision(
            sample_id="IK345",
            consensus_position=3,
            original_base="C",
            proposed_base="G",
            evidence_reference=None,
        )
        session = ConsensusReviewSession(
            sample_id="IK345",
            candidate_reference=object(),
        )
        session.add_decision(decision)

        self.assertIs(decision.decision_type, DecisionType.CHANGE)
        self.assertEqual(decision.reason, "")
        self.assertEqual(decision.reviewed_base, "G")
        self.assertTrue(session.has_changes())
        self.assertIn("CHANGE: 1", _format_review_summary(session.get_decisions()))

    def test_matrix_edit_accepts_iupac_and_visual_gap_symbols(self):
        ambiguous = create_matrix_edit_decision(
            sample_id="IK345",
            consensus_position=1,
            original_base="A",
            proposed_base="R",
            evidence_reference=None,
        )
        gap = create_matrix_edit_decision(
            sample_id="IK345",
            consensus_position=2,
            original_base="T",
            proposed_base="-",
            evidence_reference=None,
        )

        self.assertIs(ambiguous.decision_type, DecisionType.AMBIGUOUS)
        self.assertEqual(ambiguous.reviewed_base, "R")
        self.assertIs(gap.decision_type, DecisionType.CHANGE)
        self.assertEqual(gap.reviewed_base, "-")

    def test_edited_cell_and_export_records_keep_original_alignment_immutable(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())
        overlay = {(1, 0): "C"}
        entries = build_edited_cells(model, overlay)

        self.assertEqual(entries[0].sample_id, "IK346")
        self.assertEqual((entries[0].original_base, entries[0].edited_base), ("A", "C"))
        self.assertEqual(current_alignment_records(model, overlay)[1][1], "CTGTAN")
        self.assertEqual(reviewed_consensus_records(model, overlay)[1], ("IK346", "CTGTAN"))
        self.assertEqual(model.row_at(1).aligned_sequence, "ATGTAN")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "original.fasta"
            write_fasta_records(path, (("IK346", "ATGTAN"),))
            self.assertEqual(path.read_text(encoding="utf-8"), ">IK346\nATGTAN\n")

    def test_human_review_change_uses_the_same_matrix_edit_overlay(self):
        model = build_multiple_alignment_view_model(make_aligned_consensus_set())
        window = object.__new__(MultipleConsensusAlignmentWindow)
        window.view_model = model
        window._matrix_cell_edits = {}
        repainted = []
        window._repaint_matrix_cell = lambda row, column, base: repainted.append(
            (row, column, base)
        )
        decision = create_matrix_edit_decision(
            sample_id="IK346",
            consensus_position=0,
            original_base="A",
            proposed_base="C",
            evidence_reference=None,
        )

        self.assertTrue(window._apply_human_review_overlay(decision))
        self.assertEqual(window._matrix_cell_edits, {(1, 0): "C"})
        self.assertEqual(repainted, [(1, 0, "C")])
        self.assertEqual(model.row_at(1).aligned_sequence[0], "A")

    def test_legacy_sequence_list_path_remains_display_only_compatible(self):
        with self.assertRaisesRegex(ValueError, "same alignment length"):
            build_multiple_alignment_view_model(
                (
                    {"sample_id": "IK345", "sequence": "ATGC"},
                    {"sample_id": "IK346", "sequence": "ATG"},
                )
            )
        with self.assertRaisesRegex(ValueError, "unsupported"):
            build_multiple_alignment_view_model(
                ({"sample_id": "IK345", "sequence": "ATGZ"},)
            )


if __name__ == "__main__":
    unittest.main()
