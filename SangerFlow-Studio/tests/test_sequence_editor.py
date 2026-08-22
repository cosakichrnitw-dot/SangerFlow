"""Focused tests for the Studio-only unaligned Sequence Editor."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins
configure_qt_plugins()
from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from controllers.project_controller import ProjectController, _gapless_mafft_input
from core.project import Project, RevisionState
from core.sequence_dataset import SequenceDataset, SourceType
from persistence.project_bundle import load_project_bundle, save_project_bundle
from widgets.viewers.sequence_editor import SequenceEditor
from widgets.viewers.dataset_viewer import DatasetViewer
from views.project_view import ProjectView
from PySide6.QtWidgets import QToolBar


def _dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi", "COI", SourceType.IMPORTED_FASTA,
        (("C1", "ATGC"), ("C2", "ATGCAA")),
    )


class SequenceEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_edit_iupac_rename_delete_undo_and_conservative_paste(self) -> None:
        editor = SequenceEditor(_dataset())
        self.assertTrue(editor.set_base("C1", 1, "R"))
        self.assertEqual(editor.document.sequence("C1"), "ARGC")
        editor._grid.select_row("C1")
        self.assertTrue(editor.rename_selected_row("C1_COI"))
        self.assertTrue(editor.delete_selected_rows())
        self.assertIn("C1", editor.document.deleted_row_ids)
        self.assertTrue(editor.undo())
        self.assertNotIn("C1", editor.document.deleted_row_ids)
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.label("C1"), "C1")
        editor._grid.select_cell("C2", 4)
        self.assertFalse(editor.paste_selection("AAA"))
        self.assertIn("cannot extend", editor._status.text())

    def test_context_base_operation_applies_to_the_selected_rectangle(self) -> None:
        editor = SequenceEditor(_dataset())
        editor._grid.select_rectangle(0, 0, 1, 1)

        self.assertTrue(editor._set_selected_bases("N"))
        self.assertEqual(editor.document.sequence("C1")[:2], "NN")
        self.assertEqual(editor.document.sequence("C2")[:2], "NN")

    def test_fasta_source_evidence_action_is_disabled_even_with_a_controller(self) -> None:
        dataset = _dataset()
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        editor = SequenceEditor(dataset, context=view.viewer_context)
        editor._grid.select_cell("C1", 0)

        actions = {action.action_id: action for action in editor.action_providers[0].actions_for(editor)}
        self.assertFalse(actions["sequence_editor.review_evidence"].enabled)

    def test_inline_row_rename_uses_staged_document_operation(self) -> None:
        editor = SequenceEditor(_dataset())

        self.assertTrue(editor._commit_inline_row_rename("C1", "C1_RENAMED"))
        self.assertEqual(editor.document.label("C1"), "C1_RENAMED")
        self.assertTrue(editor.undo())
        self.assertEqual(editor.document.label("C1"), "C1")

    def test_save_creates_next_current_sequence_revision_without_mutating_original(self) -> None:
        dataset = _dataset()
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        editor = SequenceEditor(dataset)
        self.assertTrue(editor.set_base("C1", 0, "G"))
        derived = controller.register_edited_sequence_dataset_from_viewer(editor)

        self.assertEqual(dataset.get_record("C1").sequence, "ATGC")
        self.assertEqual(derived.get_record("C1").sequence, "GTGC")
        project = state.current_project
        self.assertEqual(project.get_entry("coi").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(project.get_entry(derived.dataset_id).revision_state, RevisionState.CURRENT)
        self.assertEqual(project.get_entry(derived.dataset_id).logical_id, "coi")

    def test_stale_and_archived_revisions_are_not_editable(self) -> None:
        dataset = _dataset()
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        first = SequenceEditor(dataset)
        first.set_base("C1", 0, "G")
        derived = controller.register_edited_sequence_dataset_from_viewer(first)
        self.assertIsNotNone(SequenceEditor(dataset, context=type("Context", (), {"app_state": state})())._editability_error())
        state.replace_project(state.current_project.archive_logical_dataset("coi"))
        self.assertIsNotNone(SequenceEditor(derived, context=type("Context", (), {"app_state": state})())._editability_error())

    def test_saved_sequence_edit_revision_round_trips_through_bundle(self) -> None:
        dataset = _dataset()
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        editor = SequenceEditor(dataset)
        editor.set_base("C1", 0, "G")
        derived = controller.register_edited_sequence_dataset_from_viewer(editor)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, path)
            loaded = load_project_bundle(path).project
        self.assertEqual(loaded.get_entry("coi").revision_state, RevisionState.SUPERSEDED)
        self.assertEqual(loaded.get_dataset(derived.dataset_id).get_record("C1").sequence, "GTGC")

    def test_dataset_viewer_handoff_exposes_and_opens_unaligned_editor(self) -> None:
        dataset = _dataset()
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        viewer = DatasetViewer(dataset, view.viewer_context)
        state.set_active_viewer(viewer)
        self.application.processEvents()
        action = view.action_manager.action("dataset.edit_sequences")
        self.assertIsNotNone(action)
        action.trigger()
        self.application.processEvents()
        self.assertIn("Sequence Editor — Unaligned: COI", [
            view._workspace_tabs.tabText(index)
            for index in range(view._workspace_tabs.count())
        ])
        view.close()

    def test_gap_containing_unaligned_dataset_uses_explicit_gapless_mafft_input(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "gapped", "Gapped source", SourceType.IMPORTED_FASTA,
            (("C1", "AT-GC"), ("C2", "ATG-C")),
        )
        prepared = _gapless_mafft_input(dataset)
        self.assertEqual(dataset.get_record("C1").sequence, "AT-GC")
        self.assertEqual(prepared.get_record("C1").sequence, "ATGC")
        self.assertFalse(prepared.has_gaps)
        self.assertEqual(prepared.metadata["gap_handling"], "removed_existing_gap_symbols")


if __name__ == "__main__":
    unittest.main()
