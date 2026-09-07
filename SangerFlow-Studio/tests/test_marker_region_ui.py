"""Focused Alignment Editor coverage for MarkerRegion management."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from export.partition_export import create_partition_definition
from persistence.project_bundle import load_project_bundle, save_project_bundle
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from views.project_view import ProjectView
from widgets.marker_regions_dialog import MarkerRegionEditDialog, marker_regions_overlap
from widgets.viewers.alignment_viewer import AlignmentViewer


def _alignment(*, marker_regions: tuple[MarkerRegion, ...] = ()) -> AlignmentDataset:
    return AlignmentDataset(
        alignment_id="coi-alignment",
        name="COI Alignment",
        parent_dataset_id="coi-source",
        records=(
            AlignmentRecord("C2", "C2", "ATG-CGTA"),
            AlignmentRecord("C3", "C3", "ATGTCGTA"),
        ),
        marker_regions=marker_regions,
    )


class MarkerRegionUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_add_uses_one_based_inclusive_coordinates_and_undo_redo_dirty_state(self) -> None:
        viewer = AlignmentViewer(_alignment())

        self.assertTrue(viewer.add_marker_region("COI", 2, 5))
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 2, 5),))
        self.assertTrue(viewer.is_dirty)
        self.assertIn("Marker regions: 1", viewer._summary.text())

        self.assertTrue(viewer.undo())
        self.assertEqual(viewer.marker_regions, ())
        self.assertFalse(viewer.is_dirty)
        self.assertTrue(viewer.redo())
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 2, 5),))

    def test_ruler_selection_is_converted_to_one_based_inclusive_region_coordinates(self) -> None:
        viewer = AlignmentViewer(_alignment())
        viewer._grid.select_column_range(1, 4)
        with patch("widgets.viewers.alignment_viewer.MarkerRegionEditDialog") as dialog_type:
            dialog = dialog_type.return_value
            dialog.DialogCode = QDialog.DialogCode
            dialog.exec.return_value = QDialog.DialogCode.Accepted
            dialog.marker_region.return_value = MarkerRegion("COI", 2, 5)
            self.assertTrue(viewer.request_add_marker_region())
        self.assertEqual(dialog_type.call_args.kwargs["initial"], MarkerRegion("New region", 2, 5))
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 2, 5),))

    def test_duplicate_and_out_of_range_regions_are_rejected(self) -> None:
        viewer = AlignmentViewer(_alignment())
        self.assertTrue(viewer.add_marker_region("COI", 1, 4))
        with self.assertRaisesRegex(ValueError, "already exists"):
            viewer.add_marker_region("COI", 5, 8)
        with self.assertRaisesRegex(ValueError, "outside the alignment length"):
            viewer.add_marker_region("16S", 5, 9)
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 1, 4),))

    def test_overlap_is_allowed_but_warned_and_partition_export_remains_protected(self) -> None:
        viewer = AlignmentViewer(_alignment())
        self.assertTrue(viewer.replace_marker_regions((
            MarkerRegion("COI", 1, 5),
            MarkerRegion("16S", 5, 8),
        )))
        self.assertTrue(marker_regions_overlap(viewer.marker_regions))
        self.assertIn("overlapping", viewer._status.text().lower())
        with self.assertRaisesRegex(ValueError, "must not overlap"):
            create_partition_definition(viewer.create_edited_alignment_dataset(
                alignment_id="edited", name="Edited"
            ))

        dialog = MarkerRegionEditDialog(
            alignment_length=8,
            existing_regions=(MarkerRegion("COI", 1, 5),),
            initial=MarkerRegion("16S", 5, 8),
        )
        self.assertIn("overlapping", dialog.warning.text().lower())

    def test_manage_replacement_supports_edit_and_delete_as_one_undoable_change(self) -> None:
        viewer = AlignmentViewer(_alignment(marker_regions=(MarkerRegion("COI", 1, 4),)))
        self.assertTrue(viewer.replace_marker_regions((MarkerRegion("COI-5prime", 2, 5),)))
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI-5prime", 2, 5),))
        self.assertTrue(viewer.undo())
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 1, 4),))
        self.assertTrue(viewer.replace_marker_regions(()))
        self.assertEqual(viewer.marker_regions, ())

    def test_column_deletion_invalidates_regions_and_undo_restores_both(self) -> None:
        regions = (MarkerRegion("COI", 1, 4),)
        viewer = AlignmentViewer(_alignment(marker_regions=regions))
        viewer._grid.select_column(2)

        self.assertTrue(viewer.delete_selected_columns())
        self.assertEqual(viewer.current_alignment_length, 7)
        self.assertEqual(viewer.marker_regions, ())
        self.assertTrue(viewer.create_edited_alignment_dataset(
            alignment_id="edited", name="Edited"
        ).metadata["marker_regions_invalidated_by_deleted_columns"])

        self.assertTrue(viewer.undo())
        self.assertEqual(viewer.current_alignment_length, 8)
        self.assertEqual(viewer.marker_regions, regions)

    def test_column_delete_warning_explains_marker_invalidation(self) -> None:
        viewer = AlignmentViewer(_alignment(marker_regions=(MarkerRegion("COI", 1, 4),)))
        viewer._grid.select_column(2)
        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.question",
            return_value=QMessageBox.StandardButton.No,
        ) as question:
            self.assertFalse(viewer.request_delete_selected_columns())
        self.assertIn("marker regions", question.call_args.args[2].lower())
        self.assertIn("undo restores both", question.call_args.args[2].lower())
        self.assertEqual(viewer.marker_regions, (MarkerRegion("COI", 1, 4),))

    def test_save_reopen_persists_marker_regions_and_existing_partition_export(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-source", "COI Source", SourceType.IMPORTED_FASTA,
            (("C2", "ATGCGTA"), ("C3", "ATGTCGTA")),
        )
        alignment = _alignment()
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(
            Project.create("project-1", "Project 1")
            .add_dataset(source)
            .add_dataset(alignment, parent_dataset_id=source.dataset_id)
        )
        viewer = AlignmentViewer(alignment, context=view.viewer_context)
        self.assertTrue(viewer.add_marker_region("COI", 1, 8))
        saved = viewer.save_edited_alignment()
        self.assertEqual(saved.marker_regions, (MarkerRegion("COI", 1, 8),))
        self.assertEqual(create_partition_definition(saved).iqtree, "COI = 1-8")

        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, bundle)
            loaded = load_project_bundle(bundle)
            try:
                reloaded = loaded.project.get_dataset(saved.alignment_id)
                self.assertEqual(reloaded.marker_regions, (MarkerRegion("COI", 1, 8),))
            finally:
                loaded.cleanup()
        view.close()

    def test_manage_action_is_in_align_menu_without_a_toolbar_button(self) -> None:
        viewer = AlignmentViewer(_alignment())
        actions = {action.action_id: action for action in viewer.action_providers[0].actions_for(viewer)}
        self.assertEqual(actions["alignment.manage_marker_regions"].menu_group, "Align")
        self.assertFalse(actions["alignment.manage_marker_regions"].toolbar)


if __name__ == "__main__":
    unittest.main()
