"""Tests for the Studio F/R Consensus workflow route."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.models import SangerRead
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import load_project_bundle, save_project_bundle
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QToolBar
from views.project_view import ProjectView
from widgets.consensus_settings_dialog import ConsensusSettingsDialog
from widgets.viewers.chromatogram_viewer import ChromatogramViewer
from widgets.viewers.sequence_editor import SequenceEditor
from widgets.viewers.fr_consensus_review import (
    ConsensusReviewManagerViewer,
    MultipleConsensusReviewViewer,
    SingleConsensusReviewViewer,
    build_consensus_sample_rows,
)
from widgets.viewers.pair_consensus_chromatogram import PairConsensusChromatogramPanel


def _read(filename: str, sequence: str) -> SangerRead:
    trace_length = max(20, len(sequence) * 4)
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[30] * len(sequence),
        traces={
            "A": [0] * trace_length,
            "C": [0] * trace_length,
            "G": [0] * trace_length,
            "T": [0] * trace_length,
        },
        base_positions=list(range(len(sequence))),
        trim_start=0,
        trim_end=len(sequence),
        trimmed_sequence=sequence,
        trimmed_quality=[30] * len(sequence),
        trimmed_base_positions=list(range(len(sequence))),
        trimmed_traces={
            "A": [0] * trace_length,
            "C": [0] * trace_length,
            "G": [0] * trace_length,
            "T": [0] * trace_length,
        },
    )


def _dataset(reads: tuple[SangerRead, ...]) -> SequenceDataset:
    return SequenceDataset(
        dataset_id="ab1-reads",
        name="AB1 reads",
        source_type=SourceType.AB1_TRIMMED,
        records=tuple(
            SequenceRecord(
                sequence_id=read.filename,
                sequence=read.trimmed_sequence,
                source_reference=read,
            )
            for read in reads
        ),
    )


class FRConsensusWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_pair_detection_rows_include_ready_and_incomplete_samples(self) -> None:
        rows = build_consensus_sample_rows(
            (
                _read("IK345_F.ab1", "ATGC"),
                _read("IK345_R.ab1", "GCAT"),
                _read("IK346_F.ab1", "ATGC"),
            )
        )

        self.assertEqual(tuple(row.sample_id for row in rows), ("IK345", "IK346"))
        self.assertTrue(rows[0].is_ready)
        self.assertEqual(rows[0].consensus_length, 4)
        self.assertEqual(rows[1].status, "Incomplete — Forward only")
        self.assertFalse(rows[1].is_ready)

    def test_consensus_settings_only_expose_existing_quality_threshold(self) -> None:
        dialog = ConsensusSettingsDialog(read_count=2)
        dialog._minimum_quality.setValue(27.5)
        settings = dialog.settings()

        self.assertEqual(settings.minimum_base_quality, 27.5)
        self.assertEqual(settings.scoring().legacy_minimum_usable_quality, 27.5)
        self.assertEqual(settings.metadata()["minimum_base_quality"], 27.5)
        dialog.close()

    def test_chromatogram_consensus_action_opens_manager_then_single_review(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        dataset = _dataset(reads)
        project = Project.create("project", "Project").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(project)
        viewer = ChromatogramViewer(
            reads,
            title="Chromatograms",
            source_object_id=dataset.dataset_id,
            context=view.viewer_context,
            source_dataset=dataset,
        )

        with patch(
            "controllers.project_controller.ConsensusSettingsDialog.exec",
            return_value=QDialog.DialogCode.Accepted,
        ):
            viewer.request_consensus()
        self.application.processEvents()

        manager = state.active_viewer
        self.assertIsInstance(manager, ConsensusReviewManagerViewer)
        self.assertEqual(len(manager.ready_rows), 1)

        manager.review_selected()
        self.application.processEvents()

        single = state.active_viewer
        self.assertIsInstance(single, SingleConsensusReviewViewer)
        self.assertEqual(single.sample_id, "IK345")
        self.assertEqual(single.original_consensus, "ATGC")
        self.assertEqual(single._grid.row_label(0), "Forward")
        self.assertEqual(single._grid.row_label(3), "Reviewed Consensus")
        self.assertNotIn("single_consensus.set_a", single.supported_actions)
        self.assertEqual(single.settings_metadata["minimum_base_quality"], 20.0)

    def test_single_review_registers_reviewed_consensus_dataset_in_project(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        rows = build_consensus_sample_rows(reads)
        single = SingleConsensusReviewViewer(
            rows[0],
            context=view.viewer_context,
            source_dataset=dataset,
        )

        single.set_base(1, "N")
        registered = single.create_and_register_reviewed_dataset()

        self.assertEqual(registered.source_type, SourceType.REVIEWED_CONSENSUS)
        self.assertEqual(registered.records[0].sequence, "ANGC")
        self.assertTrue(state.is_dirty)
        self.assertEqual(
            state.current_project.dataset_ids,
            ("ab1-reads", "ab1-reads_IK345_reviewed_consensus"),
        )
        entry = state.current_project.get_entry("ab1-reads_IK345_reviewed_consensus")
        self.assertEqual(entry.parent_dataset_id, "ab1-reads")
        self.assertEqual(entry.display_name, "Reviewed Consensus")
        self.assertEqual(
            registered.metadata["review_decisions"][1]["reviewed_base"],
            "N",
        )
        self.assertIn("consensus_settings", registered.metadata)

    def test_single_review_grid_edits_reviewed_row_and_highlights_changes(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        rows = build_consensus_sample_rows(reads)
        single = SingleConsensusReviewViewer(rows[0])

        self.assertTrue(single._grid.select_cell("reviewed", 1))
        single._grid.cell_edited.emit("reviewed", 1, "N")

        self.assertEqual(single.reviewed_consensus, "ANGC")
        self.assertIn(("reviewed", 1), single._grid.edited_cells)
        self.assertEqual(single.selected_evidence.alignment_column, 1)

        single._grid.select_rectangle(2, 0, 3, 2)
        self.assertIn("Multiple positions selected", single._detail_label.text())

    def test_single_review_bulk_selection_edit_is_one_undo_operation(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        rows = build_consensus_sample_rows(reads)
        single = SingleConsensusReviewViewer(rows[0])

        single._grid.select_rectangle(0, 0, 3, 2)
        self.assertTrue(single.set_selection_to_n())

        self.assertEqual(single.reviewed_consensus, "NNNC")
        self.assertIn(("reviewed", 0), single._grid.edited_cells)
        self.assertIn("single_consensus.set_selection_n", single.supported_actions)

        self.assertTrue(single.undo())
        self.assertEqual(single.reviewed_consensus, "ATGC")

        self.assertTrue(single.redo())
        self.assertEqual(single.reviewed_consensus, "NNNC")

    def test_single_review_exposes_trace_jump_targets(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        rows = build_consensus_sample_rows(reads)
        single = SingleConsensusReviewViewer(rows[0])
        emitted = []
        single.open_related_requested.connect(emitted.append)

        self.assertIn(
            "single_consensus.jump_forward",
            single.supported_actions,
        )
        self.assertTrue(single.jump_to_forward_trace())

        self.assertEqual(emitted[0]["action"], "TRACE_JUMP")
        self.assertEqual(emitted[0]["sample_id"], "IK345")
        self.assertEqual(emitted[0]["read_id"], "IK345_F.ab1")
        self.assertIsInstance(emitted[0]["raw_trace_position"], int)

    def test_pair_chromatograms_share_pair_alignment_columns_with_grid(self) -> None:
        """Grid selection and the embedded F/R evidence use one column index."""

        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        single = SingleConsensusReviewViewer(build_consensus_sample_rows(reads)[0])

        single.select_position(2)
        evidence = single.selected_evidence

        self.assertEqual(single._grid.selection.active_column, 2)
        self.assertEqual(single._pair_chromatogram.selected_column, 2)
        self.assertEqual(
            single._pair_chromatogram.forward_mapping[3],
            evidence.forward_raw_trace_position,
        )
        self.assertEqual(
            single._pair_chromatogram.reverse_mapping[3],
            evidence.reverse_raw_trace_position,
        )

    def test_pair_chromatogram_click_reverse_syncs_grid_selection(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        single = SingleConsensusReviewViewer(build_consensus_sample_rows(reads)[0])

        canvas = single._pair_chromatogram._canvas
        canvas.show()
        self.application.processEvents()
        QTest.mouseClick(
            canvas,
            Qt.MouseButton.LeftButton,
            pos=QPoint(118 + 18 + 2, 30 + 8),
        )
        self.application.processEvents()

        self.assertEqual(single.selected_position, 1)
        self.assertEqual(single._grid.selection.active_column, 1)
        self.assertEqual(single._pair_chromatogram.selected_column, 1)

    def test_pair_chromatogram_preserves_reverse_complement_evidence_mapping(self) -> None:
        """Reverse is displayed from ReviewEvidence, never re-reversed by the UI."""

        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        single = SingleConsensusReviewViewer(build_consensus_sample_rows(reads)[0])
        evidence = single._view_model.columns[0].review_evidence

        self.assertEqual(evidence.reverse_base, "A")
        self.assertEqual(evidence.reverse_raw_trace_position, 3)
        self.assertEqual(single._pair_chromatogram.reverse_mapping[1], 3)
        # The original raw reverse base at index 3 is T.  The shown aligned
        # base must remain the core-provided reverse-complement evidence A.
        self.assertNotEqual(reads[1].sequence[3], evidence.reverse_base)

    def test_pair_chromatogram_empty_selection_is_safe_during_repaint_and_source_switch(self) -> None:
        """A MAFFT/sample switch may legitimately leave no PairAlignment cell selected."""

        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        columns = build_consensus_sample_rows(reads)[0].view_model.columns
        panel = PairConsensusChromatogramPanel(reads[0], reads[1], columns)
        canvas = panel._canvas

        self.assertIsNone(panel.selected_column)
        self.assertIsNone(panel.evidence_for(None))
        self.assertIsNone(panel.evidence_for(-1))
        self.assertIsNone(panel.evidence_for(len(columns)))

        # Rendering must treat the empty selection as display state, not pass it
        # through to int(None) while a native QPainter is active.
        pixmap = QPixmap(canvas.size())
        canvas.render(pixmap)
        panel.set_evidence_source(reads[0], reads[1], columns)
        self.assertIsNone(panel.selected_column)
        canvas.render(QPixmap(canvas.size()))

        self.assertTrue(panel.select_column(1, center=False))
        self.assertEqual(panel.selected_column, 1)
        self.assertFalse(panel.select_column(None))
        self.assertEqual(panel.selected_column, 1)
        panel.clear_selection()
        self.assertIsNone(panel.selected_column)
        canvas.render(QPixmap(canvas.size()))

    def test_pair_chromatogram_handles_forward_only_reverse_only_and_gap_columns(self) -> None:
        forward_only = SingleConsensusReviewViewer(
            build_consensus_sample_rows(
                (_read("F_F.ab1", "AAAAAA"), _read("F_R.ab1", "TTTT"))
            )[0]
        )
        reverse_only = SingleConsensusReviewViewer(
            build_consensus_sample_rows(
                (_read("R_F.ab1", "TTTT"), _read("R_R.ab1", "AAAAAA"))
            )[0]
        )

        forward_gap = next(
            index
            for index, column in enumerate(forward_only._view_model.columns)
            if column.review_evidence.reverse_raw_trace_position is None
        )
        reverse_gap = next(
            index
            for index, column in enumerate(reverse_only._view_model.columns)
            if column.review_evidence.forward_raw_trace_position is None
        )
        forward_only.select_position(forward_gap)
        reverse_only.select_position(reverse_gap)

        self.assertIsNone(forward_only.selected_evidence.reverse_raw_trace_position)
        self.assertIsNone(reverse_only.selected_evidence.forward_raw_trace_position)
        self.assertIsNone(forward_only._pair_chromatogram.reverse_mapping[forward_gap + 1])
        self.assertIsNone(reverse_only._pair_chromatogram.forward_mapping[reverse_gap + 1])
        self.assertEqual(forward_only._pair_chromatogram.selected_column, forward_gap)
        self.assertEqual(reverse_only._pair_chromatogram.selected_column, reverse_gap)

    def test_previous_next_conflict_syncs_grid_detail_and_pair_chromatograms(self) -> None:
        reads = (_read("IK345_F.ab1", "AAAA"), _read("IK345_R.ab1", "TTCT"))
        single = SingleConsensusReviewViewer(build_consensus_sample_rows(reads)[0])

        self.assertEqual(single.conflict_positions, (1,))
        self.assertTrue(single.next_conflict())
        self.assertEqual(single.selected_position, 1)
        self.assertEqual(single._grid.selection.active_column, 1)
        self.assertEqual(single._pair_chromatogram.selected_column, 1)
        self.assertIn("UNRESOLVED_CONFLICT", single._detail_label.text())
        self.assertTrue(single.previous_conflict())
        self.assertEqual(single.selected_position, 1)

    def test_single_review_trace_jump_returns_to_chromatogram_viewer(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        chromatogram = ChromatogramViewer(
            reads,
            title="Chromatograms",
            source_object_id=dataset.dataset_id,
            context=view.viewer_context,
            source_dataset=dataset,
        )
        view.tab_manager.open_viewer(chromatogram, resource_key=f"chromatogram:{dataset.dataset_id}")
        rows = build_consensus_sample_rows(reads)
        controller.open_single_fr_consensus_review(rows[0], source_dataset=dataset)
        single = state.active_viewer

        self.assertIsInstance(single, SingleConsensusReviewViewer)
        self.assertTrue(single.jump_to_forward_trace())
        self.application.processEvents()

        self.assertIs(state.active_viewer, chromatogram)
        self.assertEqual(chromatogram.selected_read_id, "IK345_F.ab1")
        self.assertIsNotNone(chromatogram.selected_base)

    def test_multiple_consensus_review_registers_multi_record_dataset(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"),
            _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATGA"),
            _read("IK346_R.ab1", "TCAT"),
        )
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        rows = build_consensus_sample_rows(reads)

        controller.open_multiple_fr_consensus_review(rows, source_dataset=dataset)
        multiple = state.active_viewer

        self.assertIsInstance(multiple, MultipleConsensusReviewViewer)
        self.assertIn("multiple_consensus.create_dataset", multiple.supported_actions)
        self.assertNotIn("multiple_consensus.set_a", multiple.supported_actions)
        self.assertEqual(multiple._grid.row_label(0), "IK345")
        self.assertEqual(multiple._grid.row_label(1), "IK346")
        multiple.set_base("IK345", 1, "N")
        multiple._grid.select_rectangle(0, 0, 1, 2)
        self.assertIn("Multiple positions selected", multiple._detail_label.text())
        registered = multiple.create_and_register_reviewed_dataset()

        self.assertEqual(registered.source_type, SourceType.REVIEWED_CONSENSUS)
        self.assertEqual(registered.sequence_count, 2)
        self.assertEqual(registered.get_record("IK345").sequence, "ANGC")
        self.assertIn(("IK345", 1), multiple._grid.edited_cells)
        self.assertTrue(state.current_project.has_dataset(registered.dataset_id))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, path)
            loaded = load_project_bundle(path)
            try:
                reloaded = loaded.project.get_dataset(registered.dataset_id)
                self.assertEqual(reloaded.get_record("IK345").sequence, "ANGC")
                self.assertEqual(reloaded.metadata["workflow"], "F/R Multiple Consensus Review")
            finally:
                loaded.cleanup()

    def test_multiple_review_bulk_selection_edit_is_one_undo_operation(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"),
            _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATGA"),
            _read("IK346_R.ab1", "TCAT"),
        )
        rows = build_consensus_sample_rows(reads)
        multiple = MultipleConsensusReviewViewer(rows)

        multiple._grid.select_rectangle(0, 1, 1, 2)
        self.assertTrue(multiple.set_selection_to_gap())

        self.assertEqual(multiple.reviewed_sequences["IK345"], "A--C")
        self.assertEqual(multiple.reviewed_sequences["IK346"], "A--A")
        self.assertIn("multiple_consensus.set_selection_gap", multiple.supported_actions)

        self.assertTrue(multiple.undo())
        self.assertEqual(multiple.reviewed_sequences["IK345"], "ATGC")
        self.assertEqual(multiple.reviewed_sequences["IK346"], "ATGA")

        self.assertTrue(multiple.redo())
        self.assertEqual(multiple.reviewed_sequences["IK345"], "A--C")
        self.assertEqual(multiple.reviewed_sequences["IK346"], "A--A")

    def test_multiple_review_hiding_and_output_exclusion_are_separate(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATGA"), _read("IK346_R.ab1", "TCAT"),
        )
        multiple = MultipleConsensusReviewViewer(build_consensus_sample_rows(reads))
        multiple._grid.select_row("IK345")
        self.assertTrue(multiple.hide_selected_rows())
        self.assertEqual(multiple.hidden_sample_ids, frozenset({"IK345"}))
        self.assertEqual(multiple.output_excluded_sample_ids, frozenset())
        multiple.show_all_rows()
        multiple._grid.select_row("IK346")
        self.assertTrue(multiple.exclude_selected_rows_from_output())
        self.assertEqual(multiple.hidden_sample_ids, frozenset())
        self.assertEqual(multiple.output_excluded_sample_ids, frozenset({"IK346"}))
        created = multiple.create_reviewed_consensus_dataset(dataset_id="reviewed", name="Reviewed")
        self.assertEqual(tuple(record.sequence_id for record in created.records), ("IK345",))

    def test_multiple_review_delete_rows_is_undoable_and_distinct_from_hide(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATGA"), _read("IK346_R.ab1", "TCAT"),
        )
        multiple = MultipleConsensusReviewViewer(build_consensus_sample_rows(reads))
        multiple._grid.select_row("IK345")
        self.assertTrue(multiple.hide_selected_rows())
        self.assertFalse(multiple.has_pending_scientific_changes)
        multiple.show_all_rows()

        multiple._grid.select_row("IK345")
        self.assertTrue(multiple.delete_selected_rows())
        self.assertEqual(multiple.pending_deleted_row_ids, frozenset({"IK345"}))
        self.assertNotIn("IK345", tuple(row.row_id for row in multiple._grid.rows))
        created = multiple.create_reviewed_consensus_dataset(dataset_id="reviewed", name="Reviewed")
        self.assertEqual(tuple(record.sequence_id for record in created.records), ("IK346",))

        self.assertTrue(multiple.undo())
        self.assertEqual(multiple.pending_deleted_row_ids, frozenset())
        self.assertIn("IK345", tuple(row.row_id for row in multiple._grid.rows))
        self.assertTrue(multiple.redo())

    def test_multiple_review_strict_substitution_paste_is_undoable(self) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATGA"), _read("IK346_R.ab1", "TCAT"),
        )
        multiple = MultipleConsensusReviewViewer(build_consensus_sample_rows(reads))
        multiple._grid.select_rectangle(0, 1, 1, 2)
        with patch(
            "widgets.viewers.fr_consensus_review.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            self.assertTrue(multiple.paste_selection("NN\n--"))
        self.assertEqual(multiple.reviewed_sequences["IK345"], "ANNC")
        self.assertEqual(multiple.reviewed_sequences["IK346"], "A--A")
        self.assertTrue(multiple.undo())
        self.assertEqual(multiple.reviewed_sequences["IK345"], "ATGC")
        self.assertTrue(multiple.redo())
        self.assertFalse(multiple.paste_selection("AAA"))

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_multiple_review_temporary_mafft_maps_gap_grid_to_pair_evidence(self, _which) -> None:
        reads = (
            _read("IK345_F.ab1", "ATGC"),
            _read("IK345_R.ab1", "GCAT"),
            _read("IK346_F.ab1", "ATAGC"),
            _read("IK346_R.ab1", "GCTAT"),
        )
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        multiple = MultipleConsensusReviewViewer(
            build_consensus_sample_rows(reads),
            context=view.viewer_context,
            source_dataset=dataset,
        )

        def runner(_command, **_kwargs):
            return SimpleNamespace(
                returncode=0,
                stdout=">IK345\nAT-GC\n>IK346\nATAGC\n",
                stderr="",
            )

        project_ids_before = state.current_project.dataset_ids
        controller.align_multiple_consensus_review(multiple, runner=runner)

        self.assertEqual(state.current_project.dataset_ids, project_ids_before)
        self.assertEqual(multiple.temporary_alignment.length, 5)
        self.assertIsNone(
            multiple.temporary_alignment.row_for("IK345").consensus_position_for_column(2)
        )
        self.assertTrue(multiple._grid.select_cell("IK345", 2))
        self.assertIsNone(multiple._pair_chromatogram.selected_column)
        self.assertIn("Base: GAP", multiple._detail_label.text())

        self.assertTrue(multiple._grid.select_cell("IK346", 2))
        evidence = multiple._rows[1].view_model.columns[2].review_evidence
        self.assertEqual(multiple._pair_chromatogram.selected_column, 2)
        self.assertEqual(
            multiple._pair_chromatogram.forward_mapping[3],
            evidence.forward_raw_trace_position,
        )

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_multiple_review_mafft_sync_edit_conflict_and_realign(self, _which) -> None:
        reads = (
            _read("IK345_F.ab1", "AAAA"),
            _read("IK345_R.ab1", "TTCT"),
            _read("IK346_F.ab1", "ATGA"),
            _read("IK346_R.ab1", "TCAT"),
        )
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        multiple = MultipleConsensusReviewViewer(
            build_consensus_sample_rows(reads), context=view.viewer_context, source_dataset=dataset
        )

        initial_sequences = multiple.alignment_input_sequences()

        def first_runner(_command, **_kwargs):
            stdout = "".join(
                f">{sample_id}\n{sequence[:1]}-{sequence[1:]}\n"
                for sample_id, sequence in initial_sequences.items()
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        controller.align_multiple_consensus_review(multiple, runner=first_runner)
        self.assertTrue(multiple.next_conflict())
        self.assertEqual(multiple._pair_chromatogram.selected_column, multiple._selected_position)
        selected_base = multiple.reviewed_sequences["IK345"][multiple._selected_position]
        replacement = "A" if selected_base != "A" else "C"
        self.assertTrue(multiple.set_base("IK345", multiple._selected_position, replacement))
        self.assertTrue(multiple.undo())
        self.assertTrue(multiple.redo())
        with self.assertRaisesRegex(ValueError, "Gap edits"):
            multiple.set_base("IK345", 0, "-")

        multiple._pair_chromatogram.select_from_canvas(0)
        self.assertEqual(multiple._grid.selection.active_column, 0)

        def second_runner(_command, **_kwargs):
            stdout = "".join(
                f">{sample_id}\n{sequence}\n"
                for sample_id, sequence in multiple.alignment_input_sequences().items()
            )
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

        controller.align_multiple_consensus_review(multiple, runner=second_runner)
        self.assertEqual(
            multiple.temporary_alignment.row_for("IK345").aligned_sequence,
            multiple.reviewed_sequences["IK345"],
        )
        self.assertEqual(multiple._grid.column_count, 4)

    def test_fr_reviewed_consensus_metadata_survives_project_bundle_reload(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        rows = build_consensus_sample_rows(reads)
        single = SingleConsensusReviewViewer(
            rows[0],
            context=view.viewer_context,
            source_dataset=dataset,
        )
        single.set_base(1, "N")
        registered = single.create_and_register_reviewed_dataset()

        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, path)
            loaded = load_project_bundle(path)
            try:
                loaded_dataset = loaded.project.get_dataset(registered.dataset_id)
                self.assertEqual(loaded_dataset.metadata["original_consensus"], "ATGC")
                self.assertEqual(loaded_dataset.metadata["reviewed_consensus"], "ANGC")
                self.assertEqual(
                    loaded_dataset.metadata["review_decisions"][1]["decision_type"],
                    "AMBIGUOUS",
                )
            finally:
                loaded.cleanup()

    def test_reviewed_consensus_editor_resolves_parent_fr_evidence_without_session_reference(self) -> None:
        """Reviewed datasets use persisted parent/sample identity, not a live object."""

        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        source = _dataset(reads)
        reviewed = SequenceDataset(
            dataset_id="reviewed-consensus",
            name="Reviewed Consensus: IK345",
            source_type=SourceType.REVIEWED_CONSENSUS,
            records=(
                SequenceRecord(
                    sequence_id="IK345",
                    sequence="ANGC",
                    metadata={"source": "Reviewed Consensus"},
                ),
            ),
            metadata={
                "parent_dataset_id": source.dataset_id,
                "source_sample_id": "IK345",
                "workflow": "F/R Consensus Review",
            },
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(
            Project.create("project", "Project")
            .add_dataset(source)
            .add_dataset(reviewed, parent_dataset_id=source.dataset_id)
        )

        editor = SequenceEditor(reviewed, context=view.viewer_context)
        self.assertTrue(controller.open_source_chromatogram_for_sequence_editor(editor, "IK345", 1))
        self.application.processEvents()

        viewer = state.active_viewer
        self.assertIsInstance(viewer, SingleConsensusReviewViewer)
        self.assertEqual(viewer.sample_id, "IK345")
        self.assertEqual(viewer.selected_position, 1)

    def test_reviewed_consensus_reports_unavailable_parent_evidence(self) -> None:
        """Missing source AB1 evidence is reported instead of being fabricated."""

        reviewed = SequenceDataset(
            dataset_id="reviewed-consensus",
            name="Reviewed Consensus: IK345",
            source_type=SourceType.REVIEWED_CONSENSUS,
            records=(SequenceRecord(sequence_id="IK345", sequence="ATGC"),),
            metadata={
                "parent_dataset_id": "missing-ab1-reads",
                "source_sample_id": "IK345",
            },
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(reviewed))
        editor = SequenceEditor(reviewed, context=view.viewer_context)
        messages: list[str] = []
        editor.status_message_changed.connect(messages.append)

        self.assertFalse(
            controller.open_source_chromatogram_for_sequence_editor(editor, "IK345", 0)
        )
        self.assertIn("source evidence is unavailable", messages[-1].lower())

    def test_reloaded_reviewed_consensus_resolves_reattached_parent_ab1_evidence(self) -> None:
        """Bundle reload uses persisted AB1 locations, not a session object."""

        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            paths = tuple(folder / read.filename for read in reads)
            for path in paths:
                path.write_bytes(b"AB1 fixture placeholder")
            source = SequenceDataset(
                dataset_id="ab1-reads",
                name="AB1 reads",
                source_type=SourceType.AB1_TRIMMED,
                records=tuple(
                    SequenceRecord(
                        sequence_id=read.filename,
                        sequence=read.trimmed_sequence,
                        source_reference=read,
                        metadata={
                            "source_filepath": str(path),
                            "source_filename": read.filename,
                        },
                    )
                    for read, path in zip(reads, paths)
                ),
            )
            state = AppState()
            controller = ProjectController(state)
            view = ProjectView(state, controller)
            controller.open_project(Project.create("project", "Project").add_dataset(source))
            row = build_consensus_sample_rows(reads)[0]
            single = SingleConsensusReviewViewer(
                row, context=view.viewer_context, source_dataset=source
            )
            reviewed = single.create_and_register_reviewed_dataset()
            bundle_path = folder / "project.sangerflow"
            save_project_bundle(state.current_project, bundle_path)

            reloaded_state = AppState()
            reloaded_controller = ProjectController(reloaded_state)
            reloaded_view = ProjectView(reloaded_state, reloaded_controller)
            read_by_path = {str(path): read for path, read in zip(paths, reads)}
            with patch(
                "controllers.project_controller.read_ab1",
                side_effect=lambda path: read_by_path[str(Path(path))],
            ), patch(
                "controllers.project_controller.trim_sequence",
                side_effect=lambda read: read,
            ):
                reloaded_controller.open_project_bundle(str(bundle_path))

            reloaded = reloaded_state.current_project.get_dataset(reviewed.dataset_id)
            editor = SequenceEditor(reloaded, context=reloaded_view.viewer_context)
            self.assertTrue(
                reloaded_controller.open_source_chromatogram_for_sequence_editor(
                    editor, "IK345", 2
                )
            )
            self.application.processEvents()
            review = reloaded_state.active_viewer
            self.assertIsInstance(review, SingleConsensusReviewViewer)
            self.assertEqual(review.sample_id, "IK345")
            self.assertEqual(review.selected_position, 2)

    def test_consensus_action_is_exposed_in_active_toolbar(self) -> None:
        reads = (_read("IK345_F.ab1", "ATGC"), _read("IK345_R.ab1", "GCAT"))
        dataset = _dataset(reads)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        viewer = ChromatogramViewer(
            reads,
            source_object_id=dataset.dataset_id,
            context=view.viewer_context,
            source_dataset=dataset,
        )

        state.set_active_viewer(viewer)
        self.application.processEvents()

        self.assertIn("chromatogram.build_consensus", view.action_manager.action_ids())
        self.assertEqual(
            view.action_manager.action("chromatogram.build_consensus").text(),
            "Consensus",
        )


if __name__ == "__main__":
    unittest.main()
