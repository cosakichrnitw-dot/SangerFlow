"""Phase 1C working/history/navigation and metadata-record regression coverage."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(studio_root), str(studio_root.parent))

from app.qt_runtime import configure_qt_plugins
configure_qt_plugins()
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.project import Project, RevisionOperation, RevisionState
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_json import load_project, save_project
from widgets.batch_rename_dialog import BatchRenameDialog
from widgets.project_explorer import ProjectExplorer
from widgets.project_summary_graph import ProjectSummaryGraph
from widgets.viewers.dataset_viewer import DatasetViewer
from widgets.viewers.project_records_viewer import ProjectRecordsViewer
from widgets.viewers.viewer_context import ViewerContext


def _dataset(identifier: str, records: tuple[tuple[str, str, dict[str, str]], ...]) -> SequenceDataset:
    return SequenceDataset(
        identifier,
        "Wedgefish COI",
        SourceType.IMPORTED_FASTA,
        tuple(SequenceRecord(record_id, sequence, metadata=metadata) for record_id, sequence, metadata in records),
    )


def _revision_project() -> Project:
    r1 = _dataset("coi_r1", (("C1", "ATGC", {"Species": "A", "Location": "X"}),))
    r2 = _dataset("coi_r2", (("C1_CO1", "ATGC", {"Species": "A", "Location": "X"}),))
    r3 = _dataset(
        "coi_r3",
        (
            ("C1_CO1", "ATGC", {"Species": "A", "Location": "X", "Country": "Indonesia"}),
            ("C2", "ATGT", {"Species": "A", "Location": "Y"}),
            ("C3", "ATGA", {"Species": "B", "Location": "X"}),
        ),
    )
    return (
        Project.create("project", "Project")
        .add_dataset(r1, display_name="Wedgefish COI")
        .add_dataset_revision("coi_r1", r2, operation=RevisionOperation.BATCH_RENAME, display_name="Wedgefish COI")
        .add_dataset_revision("coi_r2", r3, operation=RevisionOperation.METADATA_MERGE, display_name="Wedgefish COI")
    )


def _find(parent, label: str):
    for index in range(parent.childCount()):
        child = parent.child(index)
        if child.text(0) == label:
            return child
    return None


class RevisionWorkingViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.state = AppState()
        self.controller = ProjectController(self.state)
        self.project = _revision_project()
        self.controller.open_project(self.project)
        self.explorer = ProjectExplorer(self.state, self.controller)
        self.records = ProjectRecordsViewer(self.project, ViewerContext(self.state, self.controller))

    def tearDown(self) -> None:
        self.records.close_viewer()
        self.records.deleteLater()
        self.explorer.deleteLater()

    def test_working_history_archive_restore_sections(self) -> None:
        root = self.explorer.topLevelItem(0)
        working, _alignments, _results, history, archived = (root.child(index) for index in range(5))
        self.assertEqual(working.childCount(), 1)
        self.assertEqual(working.child(0).text(0), "Wedgefish COI")
        family = history.child(0)
        self.assertEqual(tuple(family.child(index).text(0) for index in range(family.childCount())), (
            "r1 — Imported (Superseded)",
            "r2 — Batch Rename (Superseded)",
            "r3 — Metadata Merge (Current)",
        ))
        self.controller.archive_logical_dataset("coi_r1")
        self.application.processEvents()
        root = self.explorer.topLevelItem(0)
        working, _alignments, _results, history, archived = (root.child(index) for index in range(5))
        self.assertEqual(working.childCount(), 0)
        self.assertEqual(archived.childCount(), 1)
        self.controller.restore_logical_dataset("coi_r1")
        self.application.processEvents()
        root = self.explorer.topLevelItem(0)
        working, _alignments, _results, history, archived = (root.child(index) for index in range(5))
        self.assertEqual(working.childCount(), 1)
        self.assertEqual(archived.childCount(), 0)

    def test_records_default_to_current_but_can_include_previous_and_archived(self) -> None:
        self.assertEqual(tuple(row.dataset_id for row in self.records.table_model.visible_rows), ("coi_r3", "coi_r3", "coi_r3"))
        self.records._include_previous.setChecked(True)
        self.assertEqual(self.records.table_model.rowCount(), 5)
        self.controller.archive_logical_dataset("coi_r1")
        self.application.processEvents()
        self.assertEqual(self.records.table_model.rowCount(), 2)
        self.records._include_archived.setChecked(True)
        self.assertEqual(self.records.table_model.rowCount(), 5)

    def test_metadata_and_filtered_selection_are_anded_and_identity_is_retained(self) -> None:
        self.records._metadata_field_one.setCurrentIndex(self.records._metadata_field_one.findData("Species"))
        self.records._metadata_value_one.setText("A")
        self.records._metadata_field_two.setCurrentIndex(self.records._metadata_field_two.findData("Location"))
        self.records._metadata_value_two.setText("X")
        self.assertEqual(self.records.table_model.rowCount(), 1)
        self.records.select_visible()
        self.assertEqual(tuple(ref.dataset_id for ref in self.records.selected_record_refs), ("coi_r3",))
        self.assertEqual(tuple(ref.sequence_id for ref in self.records.selected_record_refs), ("C1_CO1",))
        self.records._search.setText("C2")
        self.assertEqual(len(self.records.selected_record_refs), 1)

    def test_batch_rename_dialog_preview_and_validation(self) -> None:
        dialog = BatchRenameDialog(("C1", "C2"))
        self.assertFalse(dialog.is_valid_transform)
        dialog.suffix_edit.setText("_COI")
        self.assertTrue(dialog.is_valid_transform)
        self.assertEqual(dialog.rename_by_id, {"C1": "C1_COI", "C2": "C2_COI"})
        dialog.find_replace_mode.setChecked(True)
        dialog.find_edit.setText("C")
        dialog.replace_edit.setText("X")
        self.assertEqual(dialog.rename_by_id, {"C1": "X1", "C2": "X2"})
        dialog.prefix_suffix_mode.setChecked(True)
        dialog.prefix_edit.setText("")
        dialog.suffix_edit.setText("")
        self.assertFalse(dialog.is_valid_transform)
        collision = BatchRenameDialog(("C1",), existing_record_ids=("C1", "C2"))
        collision.find_replace_mode.setChecked(True)
        collision.find_edit.setText("C1")
        collision.replace_edit.setText("C2")
        self.assertFalse(collision.is_valid_transform)

    def test_apply_emits_accepted_and_creates_one_batch_rename_revision(self) -> None:
        current = self.state.current_project.current_dataset_entry("coi_r1").dataset

        class _FindReplaceDialog(BatchRenameDialog):
            def exec(self) -> int:  # noqa: D401 - deterministic modal test shim
                self.find_replace_mode.setChecked(True)
                self.find_edit.setText("CO")
                self.replace_edit.setText("COI")
                self._apply_button.click()
                self._apply_button.click()
                return self.result()

        viewer = DatasetViewer(current, ViewerContext(self.state, self.controller))
        with patch("widgets.viewers.dataset_viewer.BatchRenameDialog", _FindReplaceDialog):
            derived = viewer.request_batch_rename()
        self.assertIsNotNone(derived)
        self.assertIn("C1_COI1", derived.sequence_ids)
        project = self.state.current_project
        self.assertEqual(project.get_entry("coi_r3").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(project.current_dataset_entry("coi_r1").dataset.dataset_id, derived.dataset_id)
        self.assertEqual(project.dataset_revision_history("coi_r1")[-1].revision_operation, RevisionOperation.BATCH_RENAME)
        self.assertEqual(len(project.dataset_revision_history("coi_r1")), 4)
        self.application.processEvents()
        self.assertEqual(tuple(row.dataset_id for row in self.records.table_model.visible_rows), (derived.dataset_id,) * 3)

    def test_prefix_suffix_and_advanced_apply_complete_the_dialog(self) -> None:
        prefix = BatchRenameDialog(("C1", "C2"))
        prefix.suffix_edit.setText("_COI")
        prefix._apply_button.click()
        self.assertEqual(prefix.result(), prefix.DialogCode.Accepted)
        advanced = BatchRenameDialog(("C1_F",))
        advanced.advanced_mode.setChecked(True)
        advanced.find_edit.setText("_F")
        advanced.replace_edit.setText("_R")
        advanced.prefix_edit.setText("sample_")
        advanced._apply_button.click()
        self.assertEqual(advanced.result(), advanced.DialogCode.Accepted)

    def test_stale_archived_and_cancel_do_not_mutate_project(self) -> None:
        old = self.project.get_dataset("coi_r3")
        current = self.state.current_project.current_dataset_entry("coi_r1").dataset
        replacement = _dataset("coi_r4", (("C1", "ATGC", {}),))
        self.state.replace_project(
            self.state.current_project.add_dataset_revision(
                current.dataset_id, replacement, operation=RevisionOperation.BATCH_RENAME
            )
        )
        with self.assertRaisesRegex(ValueError, "no longer current"):
            self.controller.create_dataset_revision_with_record_renames(
                current, {"C1_CO1": "C1_again"}, operation=RevisionOperation.BATCH_RENAME
            )
        self.state.replace_project(self.state.current_project.archive_logical_dataset("coi_r1"))
        with self.assertRaisesRegex(ValueError, "archived"):
            self.controller.create_dataset_revision_with_record_renames(
                replacement, {"C1": "C1_again"}, operation=RevisionOperation.BATCH_RENAME
            )
        dialog = BatchRenameDialog(("C1",))
        dialog.reject()
        self.assertEqual(dialog.result(), dialog.DialogCode.Rejected)
        self.assertEqual(old.dataset_id, "coi_r3")

    def test_excel_metadata_fields_are_dynamic_defaulted_and_filterable(self) -> None:
        from openpyxl import Workbook

        source = self.state.current_project.current_dataset_entry("coi_r1").dataset
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("Sample_ID", "Location", "Sampling_Date", "Voucher_ID"))
            sheet.append(("C1_CO1", "Cirebon", "2026-08-01", "V-1"))
            sheet.append(("C2", "Jakarta", "2026-08-02", "V-2"))
            sheet.append(("C3", "Cirebon", "2026-08-03", "V-3"))
            workbook.save(path)
            derived = self.controller.import_sample_metadata_for_dataset(source, str(path))
        self.application.processEvents()
        record = derived.get_record("C1_CO1")
        self.assertEqual(record.metadata["location"], "Cirebon")
        self.assertEqual(record.metadata["sampling_date"], "2026-08-01")
        self.assertGreaterEqual(self.records._metadata_field_one.findText("Location"), 0)
        self.assertGreaterEqual(self.records._metadata_field_one.findText("Sampling Date"), 0)
        self.assertTrue(any(field.casefold() == "location" for field in self.records.table_model.metadata_columns))
        self.assertTrue(any(field.casefold() == "species" for field in self.records.table_model.metadata_columns))
        location_index = next(
            index
            for index in range(self.records._metadata_field_one.count())
            if str(self.records._metadata_field_one.itemData(index) or "").casefold() == "location"
        )
        self.records._metadata_field_one.setCurrentIndex(location_index)
        self.records._metadata_value_one.setText("Cirebon")
        self.assertEqual(tuple(row.record_id for row in self.records.table_model.visible_rows), ("C1_CO1", "C3"))
        self.assertTrue(all(row.dataset_id == derived.dataset_id for row in self.records.table_model.visible_rows))

    def test_graph_archive_uses_same_project_state_as_explorer(self) -> None:
        graph = ProjectSummaryGraph(self.state, self.controller)
        try:
            entry = self.state.current_project.current_dataset_entry("coi_r1")
            graph._archive_dataset_entry(entry)
            self.application.processEvents()
            self.assertEqual(self.state.current_project.archived_dataset_entries()[0].logical_id, "coi_r1")
            root = self.explorer.topLevelItem(0)
            self.assertEqual(root.child(0).childCount(), 0)
            self.assertEqual(root.child(4).childCount(), 1)
        finally:
            graph.close()

    def test_graph_restore_uses_current_entry_logical_id_not_dataset_or_display_id(self) -> None:
        """A graph node's revision ID must resolve to its canonical logical family."""

        archived = self.state.current_project.archive_logical_dataset("coi_r1")
        self.state.replace_project(archived)
        graph = ProjectSummaryGraph(self.state, self.controller)
        try:
            entry = self.state.current_project.get_entry("coi_r3")
            self.assertEqual(entry.display_name, "Wedgefish COI")
            self.assertEqual(entry.dataset.dataset_id, "coi_r3")
            self.assertEqual(entry.logical_id, "coi_r1")

            graph._restore_dataset_entry(entry)

            restored = self.state.current_project.current_dataset_entry("coi_r1")
            self.assertEqual(restored.dataset.dataset_id, "coi_r3")
            self.assertEqual(restored.logical_id, "coi_r1")
        finally:
            graph.close()

    def test_graph_restores_archived_derived_dataset(self) -> None:
        derived = _dataset("0713_selection", (("Derived", "ATGC", {}),))
        project = self.state.current_project.add_dataset(derived, display_name="0713 selection")
        self.state.replace_project(project.archive_logical_dataset("0713_selection"))
        graph = ProjectSummaryGraph(self.state, self.controller)
        try:
            entry = self.state.current_project.get_entry("0713_selection")
            graph._restore_dataset_entry(entry)
            self.assertEqual(
                self.state.current_project.current_dataset_entry("0713_selection").dataset.dataset_id,
                "0713_selection",
            )
        finally:
            graph.close()

    def test_graph_restore_after_save_reload_preserves_canonical_logical_id(self) -> None:
        archived = self.state.current_project.archive_logical_dataset("coi_r1")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(archived, path)
            reloaded = load_project(path)
        self.state.replace_project(reloaded)
        graph = ProjectSummaryGraph(self.state, self.controller)
        try:
            graph._restore_dataset_entry(self.state.current_project.get_entry("coi_r3"))
            restored = self.state.current_project.current_dataset_entry("coi_r1")
            self.assertEqual(restored.dataset.dataset_id, "coi_r3")
            self.assertEqual(restored.logical_id, "coi_r1")
        finally:
            graph.close()

    def test_graph_delete_cancel_leaves_leaf_dataset_unchanged(self) -> None:
        leaf = _dataset("leaf", (("L1", "ATGC", {}),))
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("leaf-project", "Leaf").add_dataset(leaf))
        graph = ProjectSummaryGraph(state, controller)
        try:
            entry = state.current_project.get_entry("leaf")
            with patch(
                "widgets.project_summary_graph.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Cancel,
            ) as question:
                graph._delete_dataset_entry(entry)
            self.assertTrue(state.current_project.has_dataset("leaf"))
            buttons = question.call_args.args[3]
            self.assertEqual(
                buttons,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
        finally:
            graph.close()

    def test_graph_delete_confirm_removes_safe_leaf_dataset(self) -> None:
        leaf = _dataset("leaf", (("L1", "ATGC", {}),))
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("leaf-project", "Leaf").add_dataset(leaf))
        graph = ProjectSummaryGraph(state, controller)
        try:
            with patch(
                "widgets.project_summary_graph.QMessageBox.question",
                return_value=QMessageBox.StandardButton.Yes,
            ):
                graph._delete_dataset_entry(state.current_project.get_entry("leaf"))
            self.assertFalse(state.current_project.has_dataset("leaf"))
        finally:
            graph.close()

    def test_graph_stale_dataset_entry_is_a_safe_no_op(self) -> None:
        stale = self.state.current_project.get_entry("coi_r3")
        self.state.replace_project(Project.create("replacement", "Replacement"))
        graph = ProjectSummaryGraph(self.state, self.controller)
        try:
            with patch("widgets.project_summary_graph.QMessageBox.question") as question:
                graph._archive_dataset_entry(stale)
                graph._restore_dataset_entry(stale)
                graph._delete_dataset_entry(stale)
            self.assertEqual(self.state.current_project.dataset_count, 0)
            question.assert_not_called()
        finally:
            graph.close()

    def test_controller_refuses_delete_when_later_revision_exists(self) -> None:
        with self.assertRaisesRegex(ValueError, "later immutable revision"):
            self.controller.remove_dataset("coi_r1")

    def test_save_reload_preserves_working_archive_and_record_defaults(self) -> None:
        archived = self.project.archive_logical_dataset("coi_r1")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(archived, path)
            restored = load_project(path)
        self.assertEqual(restored.archived_dataset_entries()[0].logical_id, "coi_r1")
        reloaded = ProjectRecordsViewer(restored, ViewerContext(AppState(), self.controller))
        try:
            self.assertEqual(reloaded.table_model.rowCount(), 0)
            reloaded._include_archived.setChecked(True)
            self.assertEqual(reloaded.table_model.rowCount(), 3)
        finally:
            reloaded.close_viewer()
            reloaded.deleteLater()


if __name__ == "__main__":
    unittest.main()
