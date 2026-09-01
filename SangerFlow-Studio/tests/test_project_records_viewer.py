"""Project Records Viewer model, filtering, selection, and controller tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QLabel

from app.app_state import AppState
from app.main_window import MainWindow
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.lineage import RecordRef
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from widgets.viewers.project_records_viewer import (
    ProjectRecordsViewer,
    _CreateDatasetScopeDialog,
    _ResolveRecordIdCollisionsDialog,
)
from widgets.viewers.viewer_context import ViewerContext
from views.project_view import ProjectView


def _project() -> Project:
    raw_read = SimpleNamespace(quality=(40, 39, 41, 40))
    first = SequenceDataset(
        "Run_A",
        "Run A display",
        SourceType.AB1_TRIMMED,
        (
            SequenceRecord(
                "C1", "ATGC", description="Northern sample", source_reference=raw_read,
                metadata={
                    "blast_scientific_name": "Rhynchobatus springeri",
                    "blast_best_hit": "Rhynchobatus springeri mitochondrion, complete genome",
                    "blast_accession": "ACC-C1",
                    "blast_identity": 99.1,
                    "blast_query_coverage": 100.0,
                    "blast_evalue": 1e-80,
                    "blast_identification_status": "accepted",
                    "Location": "Cirebon",
                    "Sampling_Date": "2026-01-15",
                    "Depth": 12.5,
                    "source_batch": "Cirebon",
                },
            ),
            SequenceRecord(
                "C2", "ATGT", description="Southern sample",
                metadata={
                    "blast_scientific_name": "Glaucostegus typus",
                    "blast_best_hit": "Glaucostegus typus cytochrome oxidase subunit I",
                    "blast_accession": "ACC-C2",
                    "blast_identity": 96.5,
                    "blast_query_coverage": 97.0,
                    "blast_evalue": 0.002,
                    "blast_identification_status": "accepted",
                    "Location": "Jakarta",
                    "Sampling_Date": "2026-01-16",
                    "Depth": 8.0,
                    "source_batch": "Cirebon",
                },
            ),
        ),
    )
    second = SequenceDataset(
        "Run_B",
        "Run B display",
        SourceType.REVIEWED_CONSENSUS,
        (
            SequenceRecord(
                "C1", "TTTT", description="Duplicate record ID",
                metadata={
                    "blast_scientific_name": "Glaucostegus typus",
                    "blast_best_hit": "Glaucostegus typus voucher sequence",
                    "Location": "Bali",
                    "Sampling_Date": "2026-02-01",
                    "source_batch": "Rembang",
                },
            ),
            SequenceRecord(
                "C4", "TTTA", description="Island sample",
                metadata={
                    "blast_scientific_name": "Rhynchobatus springeri",
                    "blast_best_hit": "Rhynchobatus springeri mitochondrial genome",
                    "blast_accession": "ACC-C4",
                    "blast_identity": 98.7,
                    "blast_query_coverage": 99.0,
                    "blast_evalue": 1e-60,
                    "Location": "Cirebon",
                    "Sampling_Date": "2026-02-03",
                    "source_batch": "Rembang",
                },
            ),
        ),
    )
    alignment = AlignmentDataset(
        alignment_id="aligned",
        name="Aligned rows",
        parent_dataset_id="Run_A",
        records=(AlignmentRecord("C1", "C1", "AT-GC"),),
    )
    return (
        Project.create("project", "Project")
        .add_dataset(first)
        .add_dataset(second)
        .add_dataset(alignment, parent_dataset_id="Run_A")
    )


class _TabRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    def open_viewer(self, viewer: object, *, resource_key: str) -> str:
        self.calls.append((viewer, resource_key))
        return getattr(viewer, "viewer_id")


class ProjectRecordsViewerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.state = AppState()
        self.controller = ProjectController(self.state)
        self.project = _project()
        self.controller.open_project(self.project)
        self.context = ViewerContext(self.state, self.controller)
        self.viewer = ProjectRecordsViewer(self.project, self.context)

    def tearDown(self) -> None:
        if self.viewer is not None:
            self.viewer.deleteLater()

    def test_closed_viewer_receives_no_later_project_state_callback(self) -> None:
        self.assertTrue(self.viewer.close_viewer())
        self.viewer.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.viewer = None

        self.state.set_project(_project())
        self.application.processEvents()

    def _set_checked(self, record_ref: RecordRef) -> None:
        for row in range(self.viewer.table_model.rowCount()):
            index = self.viewer.table_model.index(row, 0)
            if self.viewer.table_model.data(index, Qt.ItemDataRole.UserRole) == record_ref:
                self.viewer.table_model.setData(index, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
                return
        self.fail(f"missing visible row: {record_ref}")

    def test_collects_sequence_records_excludes_alignment_and_preserves_recordref_identity(self) -> None:
        rows = self.viewer.table_model.all_rows
        self.assertEqual(len(rows), 4)
        self.assertEqual(
            tuple(row.record_ref for row in rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_A", "C2"), RecordRef("Run_B", "C1"), RecordRef("Run_B", "C4")),
        )
        self.assertEqual(rows[0].hq_percent, "75.0%")
        self.assertEqual(rows[1].hq_percent, "—")

    def test_search_filters_and_checkbox_selection_persists_across_filter_changes(self) -> None:
        self._set_checked(RecordRef("Run_A", "C1"))
        self._set_checked(RecordRef("Run_B", "C4"))
        self.assertEqual(self.viewer.selected_record_refs, (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")))
        self.assertEqual(self.viewer._selection_summary.text(), "2 selected · 2 visible · 0 hidden")

        self.viewer._search.setText("island")
        self.assertEqual(self.viewer.table_model.rowCount(), 1)
        self.viewer._search.setText("Run B display")
        self.assertEqual(self.viewer.table_model.rowCount(), 2)
        self.viewer._search.setText("C2")
        self.assertEqual(self.viewer.table_model.rowCount(), 1)
        self.viewer._search.clear()
        self.assertEqual(self.viewer.selected_record_refs, (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")))

        self.viewer._dataset_filter.setCurrentIndex(self.viewer._dataset_filter.findData("Run_A"))
        self.assertEqual(self.viewer.table_model.rowCount(), 2)
        self.viewer._dataset_filter.setCurrentIndex(0)
        self.viewer._source_type_filter.setCurrentIndex(
            self.viewer._source_type_filter.findData(SourceType.REVIEWED_CONSENSUS.value)
        )
        self.assertEqual(self.viewer.table_model.rowCount(), 2)

    def test_empty_high_identity_filter_rejects_derived_dataset_safely(self) -> None:
        """E2E regression: a valid filter with no rows never builds an empty Dataset."""
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_scientific_name")
        )
        self.viewer._metadata_operator_one.setCurrentText("contains")
        self.viewer._metadata_value_one.setEditText("Rhynchobatus")
        self.viewer._metadata_field_two.setCurrentIndex(
            self.viewer._metadata_field_two.findData("blast_identity")
        )
        self.viewer._metadata_operator_two.setCurrentText(">=")
        self.viewer._metadata_value_two.setEditText("100")
        self.assertEqual(self.viewer.table_model.rowCount(), 0)
        with self.assertRaisesRegex(ValueError, "record selection must not be empty"):
            self.controller.create_dataset_from_project_record_refs(
                self.viewer.selected_record_refs, name="empty", dataset_id="empty"
            )

    def test_metadata_value_dropdown_is_dynamic_cross_dataset_and_scope_aware(self) -> None:
        fields = {
            self.viewer._metadata_field_one.itemData(index)
            for index in range(self.viewer._metadata_field_one.count())
        }
        self.assertTrue({
            "blast_scientific_name", "blast_accession", "blast_identity",
            "blast_query_coverage", "blast_evalue", "Sampling_Date", "Depth",
        }.issubset(fields))
        field = "blast_scientific_name"
        self.viewer._metadata_field_one.setCurrentIndex(self.viewer._metadata_field_one.findData(field))
        candidates = tuple(
            self.viewer._metadata_value_one.itemText(index)
            for index in range(self.viewer._metadata_value_one.count())
        )
        self.assertEqual(candidates, ("Glaucostegus typus", "Rhynchobatus springeri"))
        self.assertEqual(
            tuple(self.viewer._metadata_operator_one.itemText(index)
                  for index in range(self.viewer._metadata_operator_one.count())),
            ("contains", "does not contain", "is", "is not"),
        )

        self.viewer._metadata_operator_one.setCurrentText("is")
        self.viewer._metadata_value_one.setEditText("Rhynchobatus springeri")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")),
        )

        self.viewer._dataset_filter.setCurrentIndex(self.viewer._dataset_filter.findData("Run_A"))
        scoped_candidates = tuple(
            self.viewer._metadata_value_one.itemText(index)
            for index in range(self.viewer._metadata_value_one.count())
        )
        self.assertEqual(scoped_candidates, ("Glaucostegus typus", "Rhynchobatus springeri"))

    def test_scientific_name_contains_and_location_is_combine_as_metadata_and_filter(self) -> None:
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_scientific_name")
        )
        self.viewer._metadata_operator_one.setCurrentText("contains")
        self.viewer._metadata_value_one.setEditText("Rhynchobatus")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")),
        )
        self.viewer._metadata_field_two.setCurrentIndex(
            self.viewer._metadata_field_two.findData("Location")
        )
        self.viewer._metadata_operator_two.setCurrentText("is")
        self.viewer._metadata_value_two.setEditText("Cirebon")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")),
        )

    def test_imported_arbitrary_metadata_is_filterable_and_available_as_a_column(self) -> None:
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("Sampling_Date")
        )
        self.viewer._metadata_operator_one.setCurrentText("is")
        self.viewer._metadata_value_one.setEditText("2026-01-15")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"),),
        )
        self.viewer._toggle_metadata_column("Sampling_Date", True)
        self.assertIn("Sampling_Date", self.viewer.table_model.metadata_columns)
        self.assertIn("Sampling Date", self.viewer.table_model.columns)

    def test_source_batch_is_visible_filterable_and_distinguishes_same_record_name(self) -> None:
        self.assertIn("source_batch", self.viewer.table_model.metadata_columns)
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("source_batch")
        )
        candidates = tuple(
            self.viewer._metadata_value_one.itemText(index)
            for index in range(self.viewer._metadata_value_one.count())
        )
        self.assertEqual(candidates, ("Cirebon", "Rembang"))
        self.assertEqual(
            tuple(self.viewer._metadata_operator_one.itemText(index)
                  for index in range(self.viewer._metadata_operator_one.count())),
            ("is", "is not"),
        )
        self.viewer._metadata_value_one.setEditText("Cirebon")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_A", "C2")),
        )

    def test_free_text_metadata_and_numeric_quality_filters_offer_field_specific_operators(self) -> None:
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_best_hit")
        )
        self.assertEqual(
            tuple(self.viewer._metadata_operator_one.itemText(index)
                  for index in range(self.viewer._metadata_operator_one.count())),
            ("contains", "does not contain", "is", "is not"),
        )
        self.viewer._metadata_operator_one.setCurrentText("contains")
        self.viewer._metadata_value_one.setEditText("complete genome")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"),),
        )
        self.assertEqual(
            tuple(self.viewer._length_operator.itemText(index)
                  for index in range(self.viewer._length_operator.count())),
            ("=", ">", ">=", "<", "<="),
        )
        self.assertEqual(
            tuple(self.viewer._hq_operator.itemText(index)
                  for index in range(self.viewer._hq_operator.count())),
            ("=", ">", ">=", "<", "<="),
        )

        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_identification_status")
        )
        self.assertEqual(
            tuple(self.viewer._metadata_operator_one.itemText(index)
                  for index in range(self.viewer._metadata_operator_one.count())),
            ("is", "is not"),
        )

    def test_explicit_source_batch_collision_resolution_renames_output_only(self) -> None:
        refs = (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C1"))
        dialog = _ResolveRecordIdCollisionsDialog(
            self.viewer,
            collisions={"C1": refs},
            source_batches={refs[0]: "Cirebon", refs[1]: "Rembang"},
        )
        try:
            self.assertEqual(
                dialog.output_record_ids,
                {refs[0]: "Cirebon_C1", refs[1]: "Rembang_C1"},
            )
        finally:
            dialog.deleteLater()

        derived = self.controller.create_dataset_from_project_record_refs(
            refs,
            dataset_id="resolved_collision",
            name="Resolved collision",
            output_record_ids={refs[0]: "Cirebon_C1", refs[1]: "Rembang_C1"},
        )
        self.assertEqual(derived.sequence_ids, ("Cirebon_C1", "Rembang_C1"))
        self.assertEqual(derived.get_record("Cirebon_C1").metadata["original_record_id"], "C1")
        self.assertEqual(derived.get_record("Cirebon_C1").metadata["source_batch"], "Cirebon")
        self.assertEqual(
            derived.get_record("Rembang_C1").provenance.source_records,
            (RecordRef("Run_B", "C1"),),
        )
        self.assertEqual(self.project.get_dataset("Run_A").sequence_ids, ("C1", "C2"))

    def test_same_source_batch_collision_resolution_generates_unique_output_only_ids(self) -> None:
        refs = (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C1"))
        dialog = _ResolveRecordIdCollisionsDialog(
            self.viewer,
            collisions={"C1": refs},
            source_batches={refs[0]: "0713", refs[1]: "0713"},
            existing_output_ids={refs[0]: "C1", refs[1]: "C1"},
        )
        try:
            self.assertEqual(
                dialog.output_record_ids,
                {refs[0]: "0713_C1", refs[1]: "0713_C1_2"},
            )
        finally:
            dialog.deleteLater()

        derived = self.controller.create_dataset_from_project_record_refs(
            refs,
            dataset_id="same_batch_collision",
            name="Same batch collision",
            output_record_ids={refs[0]: "0713_C1", refs[1]: "0713_C1_2"},
        )
        self.assertEqual(derived.sequence_ids, ("0713_C1", "0713_C1_2"))
        self.assertEqual(derived.get_record("0713_C1_2").metadata["original_record_id"], "C1")
        self.assertEqual(
            derived.get_record("0713_C1_2").provenance.source_records,
            (RecordRef("Run_B", "C1"),),
        )
        self.assertEqual(self.project.get_dataset("Run_A").sequence_ids, ("C1", "C2"))

    def test_project_records_description_is_optional_not_default(self) -> None:
        self.assertNotIn("Description", self.viewer.table_model.columns)
        self.viewer._toggle_optional_base_column("Description", True)
        self.assertIn("Description", self.viewer.table_model.columns)
        description_column = self.viewer.table_model.columns.index("Description")
        self.assertEqual(
            self.viewer.table_model.data(
                self.viewer.table_model.index(0, description_column),
                Qt.ItemDataRole.DisplayRole,
            ),
            "Northern sample",
        )

    def test_hidden_selection_summary_and_scope_dialog_identify_hidden_records(self) -> None:
        visible_ref = RecordRef("Run_A", "C1")
        hidden_ref = RecordRef("Run_B", "C4")
        self._set_checked(visible_ref)
        self._set_checked(hidden_ref)
        self.viewer._search.setText("C1")
        self.assertEqual(self.viewer._selection_summary.text(), "2 selected · 1 visible · 1 hidden")

        dialog = _CreateDatasetScopeDialog(
            self.viewer,
            visible_count=1,
            total_count=2,
            hidden_records=(("C4", "Run B display"),),
        )
        try:
            labels = "\n".join(label.text() for label in dialog.findChildren(QLabel))
            self.assertIn("1 selected record is currently visible.", labels)
            self.assertIn("1 additional selected record is hidden", labels)
            self.assertIn("C4 — Run B display", labels)
            self.assertTrue(dialog.use_visible_selection)
        finally:
            dialog.deleteLater()

    def test_create_dataset_flow_requires_explicit_batch_prefix_for_collision(self) -> None:
        refs = (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C1"))
        self._set_checked(refs[0])
        self._set_checked(refs[1])

        class _CollisionDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.output_record_ids = {refs[0]: "Cirebon_C1", refs[1]: "Rembang_C1"}

            def exec(self) -> int:
                return 1

        class _CreateDialog:
            dataset_id = "resolved_from_ui"
            dataset_name = "Resolved from UI"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with (
            patch("widgets.viewers.project_records_viewer._ResolveRecordIdCollisionsDialog", _CollisionDialog),
            patch("widgets.viewers.project_records_viewer._CreateDatasetDialog", _CreateDialog),
        ):
            derived = self.viewer.request_create_dataset()
        self.assertIsNotNone(derived)
        assert derived is not None
        self.assertEqual(derived.sequence_ids, ("Cirebon_C1", "Rembang_C1"))

    def test_create_dataset_scope_uses_visible_selection_by_default_without_clearing_total_selection(self) -> None:
        refs = (RecordRef("Run_A", "C1"), RecordRef("Run_A", "C2"), RecordRef("Run_B", "C4"))
        for record_ref in refs:
            self._set_checked(record_ref)
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("source_batch")
        )
        self.viewer._metadata_value_one.setEditText("Cirebon")
        self.assertEqual(self.viewer.table_model.rowCount(), 2)
        self.assertEqual(self.viewer.selected_record_refs, refs)

        class _ScopeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.use_visible_selection = True

            def exec(self) -> int:
                return 1

        class _CreateDialog:
            dataset_id = "visible_only"
            dataset_name = "Visible only"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with (
            patch("widgets.viewers.project_records_viewer._CreateDatasetScopeDialog", _ScopeDialog),
            patch("widgets.viewers.project_records_viewer._CreateDatasetDialog", _CreateDialog),
        ):
            derived = self.viewer.request_create_dataset()
        self.assertEqual(derived.sequence_ids, ("C1", "C2"))
        self.assertEqual(self.viewer.selected_record_refs, refs)

    def test_create_dataset_scope_can_explicitly_include_all_hidden_selection(self) -> None:
        refs = (RecordRef("Run_A", "C1"), RecordRef("Run_A", "C2"), RecordRef("Run_B", "C4"))
        for record_ref in refs:
            self._set_checked(record_ref)
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("source_batch")
        )
        self.viewer._metadata_value_one.setEditText("Cirebon")

        class _ScopeDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                self.use_visible_selection = False

            def exec(self) -> int:
                return 1

        class _CreateDialog:
            dataset_id = "all_selected"
            dataset_name = "All selected"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with (
            patch("widgets.viewers.project_records_viewer._CreateDatasetScopeDialog", _ScopeDialog),
            patch("widgets.viewers.project_records_viewer._CreateDatasetDialog", _CreateDialog),
        ):
            derived = self.viewer.request_create_dataset()
        self.assertEqual(derived.sequence_ids, ("C1", "C2", "C4"))

    def test_numeric_blast_metadata_uses_numeric_operators_and_filters(self) -> None:
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_identity")
        )
        self.assertEqual(
            tuple(self.viewer._metadata_operator_one.itemText(index)
                  for index in range(self.viewer._metadata_operator_one.count())),
            ("=", ">", ">=", "<", "<="),
        )
        self.viewer._metadata_operator_one.setCurrentText(">=")
        self.viewer._metadata_value_one.setEditText("98")
        self.assertEqual(
            tuple(row.record_ref for row in self.viewer.table_model.visible_rows),
            (RecordRef("Run_A", "C1"), RecordRef("Run_B", "C4")),
        )

    def test_filtered_cross_dataset_build_retains_metadata_provenance_and_source_evidence(self) -> None:
        self.viewer._metadata_field_one.setCurrentIndex(
            self.viewer._metadata_field_one.findData("blast_scientific_name")
        )
        self.viewer._metadata_value_one.setEditText("Rhynchobatus springeri")
        self.viewer.select_visible()

        derived = self.viewer.create_dataset("Springeri", "Springeri subset")
        self.assertIsNotNone(derived)
        assert derived is not None
        self.assertEqual(derived.sequence_ids, ("C1", "C4"))
        first, second = derived.records
        self.assertEqual(first.metadata["blast_scientific_name"], "Rhynchobatus springeri")
        self.assertEqual(second.metadata["Location"], "Cirebon")
        self.assertIs(first.source_reference, self.project.get_dataset("Run_A").get_record("C1").source_reference)
        self.assertEqual(first.provenance.source_records, (RecordRef("Run_A", "C1"),))
        self.assertEqual(second.provenance.source_records, (RecordRef("Run_B", "C4"),))

    def test_creates_cross_dataset_and_refreshes_after_rename_remove_and_project_close(self) -> None:
        self._set_checked(RecordRef("Run_A", "C1"))
        self._set_checked(RecordRef("Run_B", "C4"))
        derived = self.viewer.create_dataset("Final_COI", "Final COI")
        self.assertIsNotNone(derived)
        self.assertTrue(self.state.current_project.has_dataset("Final_COI"))
        entry = self.state.current_project.get_entry("Final_COI")
        self.assertEqual(tuple(relation.source_id for relation in entry.lineage_relations), ("Run_A", "Run_B"))
        self.assertEqual(len(self.viewer.table_model.all_rows), 6)

        self.controller.rename_dataset("Run_A", "Renamed Run A")
        self.assertEqual(self.viewer.table_model.all_rows[0].dataset_name, "Renamed Run A")
        self.controller.remove_dataset("Final_COI")
        self.assertEqual(len(self.viewer.table_model.all_rows), 4)
        self.state.close_project()
        self.assertEqual(self.viewer.table_model.rowCount(), 0)

    def test_collision_uses_clear_gui_message_without_renaming(self) -> None:
        self._set_checked(RecordRef("Run_A", "C1"))
        self._set_checked(RecordRef("Run_B", "C1"))
        class _CancelCollisionDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 0

        with patch(
            "widgets.viewers.project_records_viewer._ResolveRecordIdCollisionsDialog",
            _CancelCollisionDialog,
        ):
            self.assertIsNone(self.viewer.request_create_dataset())
        self.assertFalse(self.state.current_project.has_dataset("derived_dataset"))

    def test_controller_opens_one_project_records_tab_through_tab_manager(self) -> None:
        tab_manager = _TabRecorder()
        context = ViewerContext(self.state, self.controller, tab_manager=tab_manager)
        self.controller.configure_viewer_framework(
            viewer_registry=Mock(), viewer_context=context, tab_manager=tab_manager
        )
        viewer = self.controller.open_project_records_viewer()
        self.assertEqual(tab_manager.calls[0][1], "project-records:project")
        self.assertEqual(viewer.viewer_title, "Project Records")

    def test_reopening_project_records_focuses_the_existing_workspace_tab(self) -> None:
        view = ProjectView(self.state, self.controller)
        try:
            first = self.controller.open_project_records_viewer()
            second = self.controller.open_project_records_viewer()
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(
                tuple(view.tab_manager.viewer_ids()),
                (first.viewer_id,),
            )
        finally:
            view.close()

    def test_project_menu_action_opens_project_records(self) -> None:
        window = MainWindow(self.state, self.controller)
        try:
            self.assertTrue(window._project_records_action.isEnabled())
            window._project_records_action.trigger()
            self.assertIsNotNone(
                window._project_view.tab_manager.viewer_for_resource_key("project-records:project")
            )
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
