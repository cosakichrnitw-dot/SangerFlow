"""Checks for Dataset Viewer routing and display."""

from __future__ import annotations

import os
import sys
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins
configure_qt_plugins()
from app.app_state import AppState
from app.tab_manager import TabManager
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.models import SangerRead
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import load_project_bundle, save_project_bundle
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QToolBar
from openpyxl import Workbook
from views.project_view import ProjectView
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers import ViewerContext
from widgets.viewers.alignment_viewer import (
    ALIGNMENT_BASE_COLUMN_WIDTH,
    ALIGNMENT_NAME_COLUMN_WIDTH,
    ALIGNMENT_ROW_HEIGHT,
    AlignmentViewer,
    create_alignment_viewer,
)
from widgets.viewers.dataset_viewer import DatasetViewer
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.viewer_registry import ViewerRegistry
from widgets.workspace_tabs import WorkspaceTabs


class DatasetViewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_sequence_dataset_viewer_displays_summary_and_records(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )

        viewer = DatasetViewer(dataset)

        self.assertEqual(viewer.viewer_title, "COI Imported")
        self.assertEqual(viewer.viewer_kind, "dataset")
        self.assertEqual(viewer._name_value.text(), "COI Imported")
        self.assertEqual(viewer._type_value.text(), "IMPORTED_FASTA")
        self.assertEqual(viewer._count_value.text(), "2")
        self.assertEqual(viewer._records_table.rowCount(), 2)
        self.assertEqual(viewer._records_table.item(0, 1).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 2).text(), "4")

    def test_dataset_viewer_discovers_metadata_columns_with_compact_research_defaults(self) -> None:
        dataset = SequenceDataset(
            dataset_id="coi-import",
            name="COI Imported",
            source_type=SourceType.IMPORTED_FASTA,
            records=(
                SequenceRecord("C2", "ATGC", metadata={"Species": "Rhynchobatus springeri", "Location": "Cirebon"}),
                SequenceRecord("C10", "ATGCA", metadata={"species": "Rhynchobatus australiae", "Voucher": "V-10"}),
            ),
        )
        viewer = DatasetViewer(dataset)
        column_keys = viewer._column_keys()

        self.assertEqual(viewer._records_table.horizontalHeaderItem(0).text(), "Selected")
        self.assertEqual(
            viewer._records_table.horizontalHeaderItem(0).toolTip(),
            "Select records for actions in this Dataset view.",
        )
        self.assertIn("Species", viewer._available_metadata_fields)
        self.assertIn("Location", viewer._available_metadata_fields)
        self.assertIn("Voucher", viewer._available_metadata_fields)
        self.assertTrue(viewer._records_table.isColumnHidden(column_keys.index("description_source")))
        self.assertFalse(viewer._records_table.isColumnHidden(column_keys.index("Species")))
        self.assertFalse(viewer._records_table.isColumnHidden(column_keys.index("Location")))
        self.assertTrue(viewer._records_table.isColumnHidden(column_keys.index("Voucher")))
        self.assertFalse(viewer._records_table.isColumnHidden(column_keys.index("sequence_preview")))

        viewer._set_column_visible("Species", True)
        self.assertFalse(viewer._records_table.isColumnHidden(viewer._column_keys().index("Species")))
        self.assertEqual(viewer._records_table.item(0, viewer._column_keys().index("Species")).text(), "Rhynchobatus springeri")
        viewer._set_column_visible("Species", False)
        self.assertTrue(viewer._records_table.isColumnHidden(viewer._column_keys().index("Species")))

    def test_metadata_revision_defaults_are_visible_after_import_and_project_reopen(self) -> None:
        source = SequenceDataset(
            dataset_id="ab1-reads",
            name="AB1 reads",
            source_type=SourceType.AB1_TRIMMED,
            records=(SequenceRecord("C2", "ATGC", metadata={"source_batch": "Cirebon"}),),
        )
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project", "Project").add_dataset(source))
        with TemporaryDirectory() as directory:
            metadata_path = Path(directory) / "metadata.csv"
            metadata_path.write_text(
                "Sample_ID,Species,Location,Population,Country\n"
                "C2,Rhynchobatus australiae,Cirebon,North Java,Indonesia\n",
                encoding="utf-8",
            )
            revised = controller.import_sample_metadata_for_dataset(source, str(metadata_path))
            viewer = DatasetViewer(revised)
            keys = viewer._column_keys()
            fields_by_folded = {
                field.casefold(): field for field in viewer._available_metadata_fields
            }
            for field in ("species", "location", "population", "country"):
                self.assertIn(field, fields_by_folded)
                self.assertFalse(
                    viewer._records_table.isColumnHidden(keys.index(fields_by_folded[field]))
                )
            self.assertEqual(
                viewer._records_table.item(0, keys.index(fields_by_folded["location"])).text(),
                "Cirebon",
            )

            bundle = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, bundle)
            loaded = load_project_bundle(bundle)
            try:
                reloaded = loaded.project.get_dataset(revised.dataset_id)
                reloaded_viewer = DatasetViewer(reloaded)
                self.assertEqual(
                    reloaded_viewer._records_table.item(
                        0,
                        reloaded_viewer._column_keys().index(
                            next(
                                field for field in reloaded_viewer._available_metadata_fields
                                if field.casefold() == "country"
                            )
                        ),
                    ).text(),
                    "Indonesia",
                )
            finally:
                loaded.cleanup()

    def test_dataset_viewer_search_sort_and_selection_are_display_only(self) -> None:
        dataset = SequenceDataset(
            dataset_id="coi-import",
            name="COI Imported",
            source_type=SourceType.IMPORTED_FASTA,
            records=(
                SequenceRecord(
                    "C10", "ATGCA", description="Taiwan collection",
                    source_reference=SimpleNamespace(quality=(40, 40)),
                    metadata={"Species": "Zebra ray", "Location": "Cirebon", "source_filename": "C10_FishF1.ab1"},
                ),
                SequenceRecord(
                    "C2", "ATGCAT",
                    source_reference=SimpleNamespace(quality=(0, 40)),
                    metadata={"Species": "Aquila ray", "Location": "Rembang"},
                ),
                SequenceRecord(
                    "C1", "ATGC",
                    source_reference=SimpleNamespace(quality=(0, 0)),
                    metadata={},
                ),
            ),
        )
        viewer = DatasetViewer(dataset)
        original_ids = dataset.sequence_ids
        original_metadata = tuple(record.metadata for record in dataset.records)

        # Natural Record ID, numeric Length/HQ%, and arbitrary metadata sorts
        # affect only the projection in the table.
        viewer._records_table.sortItems(1, Qt.SortOrder.AscendingOrder)
        self.assertEqual(
            tuple(viewer._records_table.item(index, 1).text() for index in range(3)),
            ("C1", "C2", "C10"),
        )
        viewer._records_table.sortItems(2, Qt.SortOrder.DescendingOrder)
        self.assertEqual(viewer._records_table.item(0, 1).text(), "C2")
        viewer._records_table.sortItems(3, Qt.SortOrder.DescendingOrder)
        self.assertEqual(viewer._records_table.item(0, 1).text(), "C10")
        viewer._set_column_visible("Species", True)
        viewer._records_table.sortItems(viewer._column_keys().index("Species"), Qt.SortOrder.AscendingOrder)
        self.assertEqual(viewer._records_table.item(0, 1).text(), "C2")

        # Check state is keyed by record identity rather than visible row.
        for index in range(viewer._records_table.rowCount()):
            if viewer._records_table.item(index, 1).text() == "C1":
                viewer._records_table.item(index, 0).setCheckState(Qt.CheckState.Unchecked)
        self.assertEqual(viewer.included_record_ids, frozenset({"C2", "C10"}))
        viewer._search.setText("cirebon")
        self.assertEqual(viewer._records_table.rowCount(), 1)
        self.assertEqual(viewer._records_table.item(0, 1).text(), "C10")
        self.assertEqual(viewer.included_record_ids, frozenset({"C2", "C10"}))
        viewer._search.setText("taiwan")
        self.assertEqual(viewer._records_table.rowCount(), 1)
        viewer._search.setText("fishf1")
        self.assertEqual(viewer._records_table.rowCount(), 1)

        self.assertEqual(dataset.sequence_ids, original_ids)
        self.assertEqual(tuple(record.metadata for record in dataset.records), original_metadata)

    def test_dataset_viewer_displays_metadata_after_selection_derivation(self) -> None:
        dataset = SequenceDataset(
            dataset_id="coi-import",
            name="COI Imported",
            source_type=SourceType.IMPORTED_FASTA,
            records=(
                SequenceRecord("C2", "ATGC", metadata={"Species": "Rhynchobatus springeri", "Location": "Cirebon"}),
                SequenceRecord("C3", "ATGT", metadata={"Species": "Rhynchobatus australiae", "Location": "Rembang"}),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project-1", "Project 1").add_dataset(dataset))
        viewer = DatasetViewer(dataset, ViewerContext(state, controller))
        viewer._included_record_ids = {"C2"}

        class _CreateDialog:
            dataset_id = "coi_subset"
            dataset_name = "COI subset"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with patch("widgets.viewers.dataset_viewer.CreateDatasetDialog", _CreateDialog):
            derived = viewer.create_dataset_from_selection()

        self.assertIsInstance(derived, SequenceDataset)
        self.assertEqual(derived.records[0].metadata["Species"], "Rhynchobatus springeri")
        derived_viewer = DatasetViewer(derived)
        self.assertIn("Species", derived_viewer._available_metadata_fields)
        derived_viewer._set_column_visible("Location", True)
        self.assertEqual(
            derived_viewer._records_table.item(0, derived_viewer._column_keys().index("Location")).text(),
            "Cirebon",
        )

    def test_long_metadata_and_source_text_do_not_force_a_huge_dataset_viewer_width(self) -> None:
        dataset = SequenceDataset(
            dataset_id="coi-import",
            name="COI Imported",
            source_type=SourceType.IMPORTED_FASTA,
            records=(SequenceRecord("IK345", "ATGC"),),
            metadata={"source_path": "/very/long/" + "nested-directory/" * 500},
        )
        viewer = DatasetViewer(dataset)
        viewer.resize(900, 600)
        viewer.show()
        self.application.processEvents()

        self.assertLess(viewer.minimumSizeHint().width(), 1200)
        self.assertLess(viewer.sizeHint().width(), 1400)
        viewer.close()

    def test_sequence_dataset_export_actions_write_fasta_nexus_and_phylip(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        viewer = DatasetViewer(dataset)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "widgets.viewers.dataset_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "coi_export"), "FASTA files (*.fasta *.fas *.fa *.fna)"),
            ):
                fasta_path = viewer.request_export_fasta()
            with patch(
                "widgets.viewers.dataset_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "coi_export"), "NEXUS files (*.nex *.nexus)"),
            ):
                nexus_path = viewer.request_export_nexus()
            with patch(
                "widgets.viewers.dataset_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "coi_export"), "PHYLIP files (*.phy *.phylip)"),
            ):
                phylip_path = viewer.request_export_phylip()

            self.assertEqual(Path(fasta_path).suffix, ".fasta")
            self.assertIn(">IK345\nATGC\n", Path(fasta_path).read_text(encoding="utf-8"))
            self.assertIn("BEGIN DATA;", Path(nexus_path).read_text(encoding="utf-8"))
            self.assertTrue(Path(phylip_path).read_text(encoding="utf-8").startswith("2 4"))

    def test_sequence_dataset_export_actions_are_exposed_on_active_viewer(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        viewer = DatasetViewer(dataset, view.viewer_context)

        state.set_active_viewer(viewer)
        self.application.processEvents()

        self.assertIsNotNone(view.action_manager.action("dataset.export_fasta"))
        self.assertIsNotNone(view.action_manager.action("dataset.export_nexus"))
        self.assertIsNotNone(view.action_manager.action("dataset.export_phylip"))
        self.assertIsNotNone(view.action_manager.action("dataset.import_sample_metadata"))
        view.close()

    def test_metadata_csv_import_creates_derived_project_dataset_without_mutating_source(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        viewer = DatasetViewer(dataset, view.viewer_context)

        with TemporaryDirectory() as directory:
            csv_path = Path(directory) / "metadata.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=("Sample_ID", "Country", "Species"))
                writer.writeheader()
                writer.writerow({"Sample_ID": "IK345", "Country": "Indonesia", "Species": "Rhynchobatus"})
            with patch(
                "widgets.viewers.dataset_viewer.QFileDialog.getOpenFileName",
                return_value=(str(csv_path), "Metadata files (*.csv *.xlsx)"),
            ):
                derived = viewer.request_import_sample_metadata()

        self.assertEqual(dataset.get_record("IK345").metadata, {})
        self.assertEqual(derived.get_record("IK345").metadata["country"], "Indonesia")
        self.assertEqual(derived.metadata["source_dataset_id"], "coi-import")
        self.assertTrue(state.current_project.has_dataset(derived.dataset_id))
        entry = state.current_project.get_entry(derived.dataset_id)
        self.assertIsNone(entry.parent_dataset_id)
        self.assertEqual(entry.metadata["derivation_detail"], "SAMPLE_METADATA_MERGE")
        self.assertEqual(entry.logical_id, "coi-import")
        self.assertEqual(entry.revision_number, 2)
        view.close()

    def test_dataset_record_include_selection_creates_immutable_derived_dataset(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT"), ("IK347", "ATGA")),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        viewer = DatasetViewer(dataset, view.viewer_context)
        viewer.deselect_all_records()
        viewer._included_record_ids.update({"IK345", "IK347"})
        viewer._populate_records()

        class _CreateDialog:
            dataset_id = "coi_subset"
            dataset_name = "COI subset"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with patch("widgets.viewers.dataset_viewer.CreateDatasetDialog", _CreateDialog):
            derived = viewer.create_dataset_from_selection()

        self.assertEqual(tuple(record.sequence_id for record in dataset.records), ("IK345", "IK346", "IK347"))
        self.assertEqual(tuple(record.sequence_id for record in derived.records), ("IK345", "IK347"))
        self.assertEqual(derived.metadata["derived_from"], "RECORD_SELECTION")
        self.assertEqual(state.current_project.get_entry(derived.dataset_id).parent_dataset_id, "coi-import")
        view.close()

    def test_dataset_selection_uses_shared_naming_dialog_and_cancel_is_non_destructive(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        state = AppState()
        controller = ProjectController(state)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))
        viewer = DatasetViewer(dataset, ViewerContext(state, controller))
        viewer._included_record_ids = {"IK345"}

        class _CancelDialog:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 0

        with patch("widgets.viewers.dataset_viewer.CreateDatasetDialog", _CancelDialog):
            self.assertIsNone(viewer.create_dataset_from_selection())
        self.assertEqual(len(state.current_project.dataset_entries), 1)

        class _CreateDialog:
            dataset_id = "reviewed_subset"
            dataset_name = "Reviewed COI subset"

            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def exec(self) -> int:
                return 1

        with patch("widgets.viewers.dataset_viewer.CreateDatasetDialog", _CreateDialog):
            derived = viewer.create_dataset_from_selection()
        self.assertIsNotNone(derived)
        assert derived is not None
        self.assertEqual(derived.dataset_id, "reviewed_subset")
        self.assertEqual(derived.name, "Reviewed COI subset")
        self.assertEqual(derived.sequence_ids, ("IK345",))
        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))

    def test_metadata_xlsx_import_and_validation_errors(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"),),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(Project.create("project", "Project").add_dataset(dataset))

        with TemporaryDirectory() as directory:
            valid_path = Path(directory) / "valid.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("Sample_ID", "Country"))
            sheet.append(("IK345", "Indonesia"))
            workbook.save(valid_path)
            derived = controller.import_sample_metadata_for_dataset(dataset, str(valid_path))
            self.assertEqual(derived.get_record("IK345").metadata["country"], "Indonesia")

            xlsx_path = Path(directory) / "bad.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("Sample_ID", "Country"))
            sheet.append(("MISSING", "Indonesia"))
            workbook.save(xlsx_path)
            with self.assertRaisesRegex(ValueError, "unmatched Sample_ID"):
                controller.import_sample_metadata_for_dataset(derived, str(xlsx_path))

            duplicate_path = Path(directory) / "duplicate.csv"
            duplicate_path.write_text(
                "Sample_ID,Country\nIK345,Indonesia\nIK345,Malaysia\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate Sample_ID"):
                controller.import_sample_metadata_for_dataset(derived, str(duplicate_path))

        self.assertEqual(state.current_project.dataset_ids, ("coi-import", "coi-import_metadata"))
        view.close()

    def test_controller_opens_single_ab1_through_existing_folder_dataset_workflow(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        read = SangerRead(
            filename="IK345_F.ab1",
            sequence="ATGC",
            quality=[30, 30, 30, 30],
            traces={base: [0] * 20 for base in "ACGT"},
            base_positions=[1, 5, 9, 13],
        )
        with TemporaryDirectory() as directory:
            filepath = Path(directory) / "IK345_F.ab1"
            filepath.touch()
            with patch("controllers.project_controller.read_ab1", return_value=read), patch(
                "controllers.project_controller.trim_sequence", side_effect=lambda value: value
            ):
                tab_name = controller.open_ab1_file(str(filepath))

        self.assertIsNotNone(tab_name)
        self.assertEqual(state.current_project.dataset_count, 1)
        dataset = state.current_project.get_dataset(state.current_project.dataset_ids[0])
        self.assertEqual(dataset.sequence_count, 1)
        self.assertEqual(dataset.records[0].sequence_id, "IK345_F")
        self.assertEqual(dataset.records[0].metadata["source_filename"], "IK345_F.ab1")
        with TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, bundle_path)
            loaded = load_project_bundle(bundle_path)
            try:
                self.assertEqual(
                    loaded.project.get_dataset(dataset.dataset_id).records[0].sequence_id,
                    "IK345_F",
                )
            finally:
                loaded.cleanup()
        view.close()

    def test_sequence_dataset_export_error_is_reported_with_message_box(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGTA")),
        )
        viewer = DatasetViewer(dataset)
        with TemporaryDirectory() as directory:
            with patch(
                "widgets.viewers.dataset_viewer.QFileDialog.getSaveFileName",
                return_value=(str(Path(directory) / "coi_export.nex"), "NEXUS files (*.nex *.nexus)"),
            ), patch("widgets.viewers.dataset_viewer.QMessageBox.warning") as warning:
                result = viewer.request_export_nexus()

        self.assertIsNone(result)
        warning.assert_called_once()
        self.assertIn("equal-length", warning.call_args.args[2])

    def test_alignment_dataset_viewer_displays_alignment_records(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )

        viewer = DatasetViewer(alignment)

        self.assertEqual(viewer.viewer_title, "COI Alignment")
        self.assertEqual(viewer._type_value.text(), "AlignmentDataset")
        self.assertEqual(viewer._count_value.text(), "2")
        self.assertEqual(viewer._records_table.item(0, 1).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 4).text(), "IK345")
        self.assertEqual(viewer._records_table.item(0, 5).text(), "ATG-C")

    def test_dataset_viewer_action_opens_alignment_viewer_for_alignment_dataset(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        tab_manager = TabManager(tabs, state)
        context = ViewerContext(state, controller, tab_manager=tab_manager)
        dataset_viewer = DatasetViewer(alignment, context)
        tab_manager.open_viewer(dataset_viewer, resource_key="dataset:coi-alignment")
        from app.action_manager import ActionManager

        action_manager = ActionManager(state)
        toolbar = QToolBar()
        action_manager.attach_toolbar(toolbar)
        state.set_active_viewer(dataset_viewer)
        self.application.processEvents()

        action = action_manager.action("dataset.open_alignment_viewer")
        self.assertIsNotNone(action)
        self.assertTrue(action.isEnabled())
        action.trigger()
        self.application.processEvents()

        self.assertIsInstance(tabs.widget(3), AlignmentViewer)
        action.trigger()
        self.application.processEvents()
        self.assertEqual(tabs.count(), 4)

    def test_project_explorer_selection_opens_dataset_viewer_tab(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        dataset_item = explorer.topLevelItem(0).child(0).child(0)

        explorer.setCurrentItem(dataset_item)
        self.application.processEvents()

        self.assertEqual(tabs.count(), 3)
        self.assertEqual(tabs.tabText(2), "COI Imported")
        self.assertIsInstance(tabs.widget(2), DatasetViewer)
        self.assertIs(state.active_viewer, tabs.widget(2))
        self.assertIs(state.selected_item.payload.dataset, dataset)
        self.assertEqual(view.tab_manager.viewer_ids(), ("dataset-viewer-coi-import",))

        self.assertTrue(view.tab_manager.close_viewer("dataset-viewer-coi-import"))
        self.assertEqual(tabs.count(), 2)

    def test_alignment_dataset_routes_to_alignment_viewer_by_default(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        registry = ViewerRegistry()
        registry.register_model_viewer(
            AlignmentDataset,
            viewer_key="alignment-dataset-viewer",
            label="Alignment Viewer",
            factory=create_alignment_viewer,
            default=True,
        )

        viewer = registry.create_viewer_for(alignment, ViewerContext(state, controller))

        self.assertIsInstance(viewer, AlignmentViewer)
        self.assertEqual(viewer.viewer_id, "alignment-viewer-coi-alignment")

    def test_project_explorer_opens_alignment_dataset_in_alignment_viewer(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
            ),
        )
        project = (
            Project.create("project-1", "Project 1")
            .add_dataset(source)
            .add_dataset(
                alignment,
                parent_dataset_id="coi-import",
            )
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        alignment_item = explorer.topLevelItem(0).child(1).child(0)

        explorer.setCurrentItem(alignment_item)
        self.application.processEvents()

        self.assertEqual(tabs.count(), 3)
        self.assertIsInstance(tabs.widget(2), AlignmentViewer)
        self.assertEqual(tabs.tabText(2), "Sequence Editor — Aligned: COI Alignment")

    def test_alignment_viewer_shows_gaps_and_selects_cell_and_column(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        viewer = AlignmentViewer(alignment)

        selected = viewer.select_alignment_cell(0, 3)
        viewer.select_column(2)

        self.assertEqual(viewer._grid.row_label(1), "IK345")
        self.assertEqual(viewer._grid.cell_base(1, 3), "-")
        self.assertEqual(selected, ("IK345", 4, "-"))
        self.assertEqual(viewer.selected_column, 3)
        self.assertEqual(viewer._grid.label_width, ALIGNMENT_NAME_COLUMN_WIDTH)
        self.assertEqual(viewer._grid.cell_width, ALIGNMENT_BASE_COLUMN_WIDTH)
        self.assertEqual(viewer._grid.row_height, ALIGNMENT_ROW_HEIGHT)
        viewer._grid.select_rectangle(1, 1, 2, 3)
        self.assertIn("2 rows × 3 columns", viewer._status.text())
        self.assertFalse(viewer._grid.edit_current_cell("N"))

    def test_alignment_viewer_edits_cells_and_saves_derived_alignment(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        project = (
            Project.create("project-1", "Project 1")
            .add_dataset(source)
            .add_dataset(alignment, parent_dataset_id="coi-import")
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(project)
        viewer = AlignmentViewer(alignment, context=view.viewer_context)

        self.assertTrue(viewer.set_base("IK345", 3, "N"))
        self.assertIn(("IK345", 3), viewer.edited_cells)
        self.assertEqual(viewer._grid.cell_base(1, 3), "N")
        self.assertTrue(viewer.undo())
        self.assertEqual(viewer._grid.cell_base(1, 3), "-")
        self.assertTrue(viewer.redo())
        viewer._grid.select_rectangle(1, 1, 2, 2)
        self.assertTrue(viewer.set_selection_to_n())
        self.assertEqual(viewer._grid.cell_base(1, 1), "N")
        self.assertEqual(viewer._grid.cell_base(2, 2), "N")
        self.assertTrue(viewer.undo())
        self.assertEqual(viewer._grid.cell_base(1, 1), "T")
        self.assertEqual(viewer._grid.cell_base(2, 2), "G")
        self.assertTrue(viewer.redo())
        self.assertEqual(viewer.selection_fasta_text(), ">IK345\nNN\n>IK346\nNN\n")
        viewer._grid.select_column_range(1, 2)
        self.assertTrue(viewer.exclude_selected_columns())
        viewer._grid.select_row("IK345")
        self.assertTrue(viewer.rename_selected_row("IK345 renamed"))
        self.assertTrue(viewer.undo())
        self.assertTrue(viewer.redo())
        registered = viewer.save_edited_alignment()

        self.assertIsInstance(registered, AlignmentDataset)
        self.assertEqual(registered.get_record("IK345 renamed").aligned_sequence, "ANNNC")
        self.assertEqual(registered.metadata["excluded_columns"], (1, 2))
        self.assertEqual(registered.metadata["renamed_rows"], {"IK345": "IK345 renamed"})
        self.assertTrue(state.current_project.has_dataset("coi-alignment_edited"))
        entry = state.current_project.get_entry("coi-alignment_edited")
        self.assertEqual(entry.parent_dataset_id, "coi-import")
        self.assertEqual(entry.metadata["derivation_detail"], "EDITED_ALIGNMENT")
        self.assertEqual(entry.logical_id, "coi-alignment")
        self.assertEqual(entry.revision_number, 2)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.sangerflow"
            save_project_bundle(state.current_project, path)
            loaded = load_project_bundle(path)
            try:
                reloaded = loaded.project.get_dataset("coi-alignment_edited")
                self.assertEqual(reloaded.get_record("IK345 renamed").aligned_sequence, "ANNNC")
                self.assertEqual(reloaded.metadata["source_alignment_id"], "coi-alignment")
                self.assertEqual(reloaded.metadata["excluded_columns"], [1, 2])
            finally:
                loaded.cleanup()
        view.close()

    def test_alignment_editor_feedback_tracks_working_copy_and_saved_revision(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGC"),
                AlignmentRecord("IK346", "IK346", "ATGT"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        controller.open_project(
            Project.create("project-1", "Project 1")
            .add_dataset(source)
            .add_dataset(alignment, parent_dataset_id="coi-import")
        )
        viewer = AlignmentViewer(alignment, context=view.viewer_context)

        self.assertIn("Editing working copy • No unsaved edits", viewer._summary.text())
        self.assertFalse(viewer._save_revision_button.isEnabled())
        self.assertTrue(viewer.set_base("IK345", 0, "G"))
        self.assertIn("Editing working copy • Unsaved edits", viewer._summary.text())
        self.assertTrue(viewer._save_revision_button.isEnabled())
        self.assertFalse(viewer._manual_edit_legend.isHidden())
        self.assertTrue(viewer.undo())
        self.assertIn("Editing working copy • No unsaved edits", viewer._summary.text())
        self.assertTrue(viewer.set_base("IK345", 0, "G"))

        viewer._save_revision_button.click()

        self.assertIsInstance(state.active_viewer, AlignmentViewer)
        self.assertIn("Saved as COI Alignment revision 2. Previous revision preserved.", state.active_viewer._status.text())
        self.assertEqual(state.current_project.get_entry("coi-alignment").revision_state.name, "SUPERSEDED")
        view.close()

    def test_unsaved_alignment_close_requires_explicit_save_discard_or_cancel(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGC"),
                AlignmentRecord("IK346", "IK346", "ATGT"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        self.assertTrue(viewer.set_base("IK345", 0, "G"))

        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Cancel,
        ):
            self.assertFalse(viewer.close_viewer())
        self.assertTrue(viewer.has_pending_scientific_changes)

        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Discard,
        ):
            self.assertTrue(viewer.close_viewer())

        viewer.save_edited_alignment = lambda: object()  # type: ignore[method-assign]
        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Save,
        ):
            self.assertTrue(viewer.close_viewer())

    def test_alignment_viewer_full_export_actions_write_alignment_files(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        viewer._grid.select_rectangle(1, 1, 2, 2)
        original_selection = viewer.selection_fasta_text()

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch(
                "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "alignment_export"), "FASTA files (*.fasta *.fas *.fa *.fna)"),
            ):
                fasta_path = viewer.request_export_alignment_fasta()
            with patch(
                "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "alignment_export"), "NEXUS files (*.nex *.nexus)"),
            ):
                nexus_path = viewer.request_export_alignment_nexus()
            with patch(
                "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
                return_value=(str(root / "alignment_export"), "PHYLIP files (*.phy *.phylip)"),
            ):
                phylip_path = viewer.request_export_alignment_phylip()

            self.assertIn(">IK345\nATG-C\n", Path(fasta_path).read_text(encoding="utf-8"))
            self.assertIn("GAP=-", Path(nexus_path).read_text(encoding="utf-8"))
            self.assertTrue(Path(phylip_path).read_text(encoding="utf-8").startswith("2 5"))
            self.assertEqual(viewer.selection_fasta_text(), original_selection)

    def test_alignment_selected_rows_and_regions_export_with_distinct_semantics(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        viewer = AlignmentViewer(alignment)

        # A one-cell selection still selects its complete AlignmentDataset row.
        viewer._grid.select_rectangle(1, 2, 1, 2)
        self.assertEqual(viewer.selected_rows_fasta_text(), ">IK345\nATG-C\n")
        self.assertEqual(viewer.selection_fasta_text(), ">IK345\nG\n")
        self.assertEqual(
            viewer.selected_rows_export_summary(),
            "1 sequence selected • Alignment length: 5 columns",
        )
        self.assertEqual(
            viewer.selected_region_export_summary(),
            "1 sequence • Columns 3–3 • Region length: 1 columns",
        )

        # A rectangular region across rows preserves only its selected columns,
        # while selected-row export preserves every row in full and retains gaps.
        viewer._grid.select_rectangle(1, 1, 2, 3)
        self.assertEqual(
            viewer.selected_rows_fasta_text(),
            ">IK345\nATG-C\n>IK346\nATGTC\n",
        )
        self.assertEqual(
            viewer.selection_fasta_text(),
            ">IK345\nTG-\n>IK346\nTGT\n",
        )
        self.assertEqual(
            viewer.selected_region_export_summary(),
            "2 sequences • Columns 2–4 • Region length: 3 columns",
        )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            rows_path = root / "selected_rows.fasta"
            region_path = root / "selected_region.fasta"
            self.assertEqual(
                viewer.export_selected_rows_fasta(rows_path),
                ">IK345\nATG-C\n>IK346\nATGTC\n",
            )
            self.assertEqual(
                viewer.export_selection_fasta(region_path),
                ">IK345\nTG-\n>IK346\nTGT\n",
            )
            self.assertEqual(rows_path.read_text(encoding="utf-8"), ">IK345\nATG-C\n>IK346\nATGTC\n")
            self.assertEqual(region_path.read_text(encoding="utf-8"), ">IK345\nTG-\n>IK346\nTGT\n")

        # Cancelling either explicit export never changes the saved alignment.
        with patch(
            "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
            return_value=("", ""),
        ):
            self.assertIsNone(viewer.request_export_selected_rows_fasta())
            self.assertIsNone(viewer.request_export_selection_fasta())
        self.assertEqual(alignment.get_record("IK345").aligned_sequence, "ATG-C")
        self.assertEqual(alignment.get_record("IK346").aligned_sequence, "ATGTC")

    def test_alignment_selected_fasta_exports_require_an_explicit_selection(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(AlignmentRecord("IK345", "IK345", "ATG-C"),),
        )
        viewer = AlignmentViewer(alignment)
        viewer._grid.clear_selection()

        self.assertEqual(viewer.selected_rows_fasta_text(), "")
        self.assertEqual(viewer.selection_fasta_text(), "")
        with TemporaryDirectory() as directory, patch(
            "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName"
        ) as save_dialog:
            self.assertIsNone(viewer.request_export_selected_rows_fasta())
            self.assertIsNone(viewer.request_export_selection_fasta())
            self.assertFalse((Path(directory) / "unexpected.fasta").exists())
        save_dialog.assert_not_called()
        with self.assertRaises(ValueError):
            viewer.export_selected_rows_fasta(Path("unused.fasta"))
        with self.assertRaises(ValueError):
            viewer.export_selection_fasta(Path("unused.fasta"))

        # A grid refresh cannot leave a stale selection exportable.
        viewer._grid.select_rectangle(1, 0, 1, 0)
        viewer._grid.set_rows((), preserve_selection=True)
        self.assertEqual(viewer.selected_rows_fasta_text(), "")
        self.assertEqual(viewer.selection_fasta_text(), "")

    def test_alignment_selected_fasta_export_actions_are_unambiguous(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(AlignmentRecord("IK345", "IK345", "ATG-C"),),
        )
        viewer = AlignmentViewer(alignment)
        actions = {action.action_id: action for action in viewer.action_providers[0].actions_for(viewer)}

        self.assertEqual(actions["alignment.export_selected_rows_fasta"].label, "Export Selected Rows as FASTA…")
        self.assertEqual(actions["alignment.export_selection_fasta"].label, "Export Selected Region as FASTA…")
        self.assertNotIn("Export Selected Sequences", actions["alignment.export_selection_fasta"].label)

    def test_pending_alignment_edits_cannot_silently_export_saved_revision(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        self.assertTrue(viewer.set_base("IK345", 1, "N"))
        self.assertTrue(viewer.is_dirty)
        with TemporaryDirectory() as directory, patch(
            "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
            return_value=(str(Path(directory) / "should_not_exist"), "FASTA files (*.fasta)"),
        ), patch("widgets.viewers.alignment_viewer.QMessageBox.warning") as warning:
            self.assertIsNone(viewer.request_export_alignment_fasta())
            self.assertFalse((Path(directory) / "should_not_exist").exists())
        warning.assert_called_once()
        self.assertIn("Save or discard", warning.call_args.args[2])
        self.assertFalse(
            next(action for action in viewer.action_providers[0].actions_for(viewer)
                 if action.action_id == "alignment.export_fasta").enabled
        )

    def test_alignment_partition_actions_export_existing_marker_regions(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
            ),
            marker_regions=(MarkerRegion("COI", 1, 5),),
        )
        viewer = AlignmentViewer(alignment)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "partitions"
            with patch(
                "widgets.viewers.alignment_viewer.QFileDialog.getSaveFileName",
                return_value=(str(path), "Text files (*.txt)"),
            ):
                output = viewer.request_export_iqtree_partitions()
            self.assertEqual(Path(output).read_text(encoding="utf-8"), "COI = 1-5\n")

    def test_alignment_viewer_row_hide_and_delete_are_non_destructive_until_saved(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
                AlignmentRecord("IK347", "IK347", "ATGTA"),
            ),
        )
        viewer = AlignmentViewer(alignment)

        viewer._grid.select_row("IK346")
        self.assertTrue(viewer.hide_selected_rows())
        self.assertNotIn("IK346", tuple(row.row_id for row in viewer._grid.rows))
        self.assertEqual(tuple(row.record_id for row in alignment.records), ("IK345", "IK346", "IK347"))
        viewer.show_all_rows()
        self.assertEqual(viewer._grid.row_label(2), "IK346")

        viewer._grid.select_row("IK346")
        self.assertTrue(viewer.delete_selected_rows_from_derived_dataset())
        self.assertEqual(viewer.pending_deleted_row_ids, frozenset({"IK346"}))
        self.assertIn("Unsaved changes • 1 row deleted", viewer._summary.text())
        self.assertNotIn("IK346", tuple(row.row_id for row in viewer._grid.rows))
        self.assertTrue(viewer.undo())
        self.assertEqual(viewer.pending_deleted_row_ids, frozenset())
        self.assertIn("IK346", tuple(row.row_id for row in viewer._grid.rows))
        self.assertTrue(viewer.redo())
        derived = viewer.create_edited_alignment_dataset(
            alignment_id="coi-alignment-derived",
            name="Derived",
        )

        self.assertEqual(tuple(record.record_id for record in derived.records), ("IK345", "IK347"))
        self.assertEqual(derived.metadata["deleted_rows"], ("IK346",))
        self.assertEqual(tuple(row.record_id for row in alignment.records), ("IK345", "IK346", "IK347"))

    def test_alignment_transient_consensus_distinguishes_hide_and_pending_delete(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG"),
                AlignmentRecord("IK346", "IK346", "ACG"),
                AlignmentRecord("IK347", "IK347", "ACG"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        self.assertEqual(viewer._grid.rows[0].sequence, "ACG")

        viewer._grid.select_row("IK346")
        self.assertTrue(viewer.hide_selected_rows())
        # Hide is display-only: the hidden sequence remains consensus input.
        self.assertEqual(viewer._grid.rows[0].sequence, "ACG")

        viewer.show_all_rows()
        viewer._grid.select_row("IK346")
        self.assertTrue(viewer.delete_selected_rows_from_derived_dataset())
        self.assertEqual(viewer._grid.rows[0].sequence, "ATG")

        self.assertTrue(viewer.set_base("IK345", 1, "N"))
        self.assertEqual(viewer._grid.rows[0].sequence, "ANG")

    def test_alignment_delete_columns_is_structural_and_undo_redo_safe(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGCGTA"),
                AlignmentRecord("IK346", "IK346", "ATGCGTA"),
                AlignmentRecord("IK347", "IK347", "ATGTGTA"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        viewer._grid.select_column_range(3, 3)
        self.assertTrue(viewer.delete_selected_columns())
        self.assertEqual(viewer.current_alignment_length, 6)
        self.assertEqual(viewer._grid.rows[1].sequence, "ATGGTA")
        self.assertEqual(viewer._grid.rows[0].sequence, "ATGGTA")
        self.assertIn("1 column deleted", viewer._summary.text())
        self.assertEqual(alignment.length, 7)

        self.assertTrue(viewer.undo())
        self.assertEqual(viewer.current_alignment_length, 7)
        self.assertEqual(viewer._grid.rows[1].sequence, "ATGCGTA")
        self.assertTrue(viewer.redo())
        self.assertEqual(viewer._grid.rows[1].sequence, "ATGGTA")

        derived = viewer.create_edited_alignment_dataset(
            alignment_id="coi-alignment-edited", name="Edited",
        )
        self.assertEqual(derived.length, 6)
        self.assertEqual(derived.get_record("IK345").aligned_sequence, "ATGGTA")
        self.assertEqual(derived.metadata["deleted_columns"], (3,))
        self.assertEqual(alignment.get_record("IK345").aligned_sequence, "ATGCGTA")

    def test_deleted_alignment_column_preserves_source_trace_mapping_after_reopen(self) -> None:
        read = SangerRead(
            filename="IK345_F.ab1",
            sequence="ATGCG",
            quality=[30] * 5,
            traces={base: [1] * 20 for base in "ACGT"},
            base_positions=[1, 3, 5, 7, 9],
            trim_start=0,
            trim_end=5,
            trimmed_sequence="ATGCG",
            trimmed_quality=[30] * 5,
            trimmed_base_positions=[1, 3, 5, 7, 9],
            trimmed_traces={base: [1] * 20 for base in "ACGT"},
        )
        alignment = AlignmentDataset(
            alignment_id="source-alignment",
            name="Source",
            parent_dataset_id="reads",
            records=(
                AlignmentRecord(
                    "IK345_F.ab1",
                    "IK345_F.ab1",
                    "ATGCG",
                    metadata={"source_filename": "IK345_F.ab1"},
                ),
            ),
        )
        editor = AlignmentViewer(alignment)
        editor._grid.select_column(3)
        self.assertTrue(editor.delete_selected_columns())
        derived = editor.create_edited_alignment_dataset(
            alignment_id="source-alignment-r2", name="Source r2"
        )
        reopened = AlignmentChromatogramViewer(
            (read,),
            alignment=(SimpleNamespace(id="IK345_F.ab1", seq="ATGG"),),
            alignment_dataset=derived,
        )

        # Current display column 4 is root source column 5, not the deleted
        # column's following peak shifted left by an ungapped recount.
        self.assertEqual(reopened.maps["IK345_F.ab1"][4], 9)

    def test_alignment_column_delete_remaps_exclusion_edits_and_paste(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGCGTA"),
                AlignmentRecord("IK346", "IK346", "ATGCGTA"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        viewer._grid.select_column(4)
        self.assertTrue(viewer.exclude_selected_columns())
        self.assertEqual(viewer._grid.excluded_columns, frozenset({4}))
        self.assertTrue(viewer.set_base("IK345", 4, "N"))

        viewer._grid.select_column(1)
        self.assertTrue(viewer.delete_selected_columns())
        self.assertEqual(viewer.current_alignment_length, 6)
        self.assertEqual(viewer._grid.excluded_columns, frozenset({3}))
        self.assertIn(("IK345", 3), viewer.edited_cells)

        viewer._grid.select_rectangle(1, 0, 2, 1)
        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            self.assertTrue(viewer.paste_selection("RY\nKM"))
        self.assertEqual(viewer._grid.rows[1].sequence[:2], "RY")
        self.assertEqual(viewer._grid.rows[2].sequence[:2], "KM")
        self.assertTrue(viewer.undo())
        self.assertEqual(viewer._grid.rows[1].sequence[:2], "AG")
        self.assertTrue(viewer.redo())

        viewer._grid.select_rectangle(1, 0, 2, 1)
        self.assertFalse(viewer.paste_selection("AA"))
        self.assertIn("shape mismatch", viewer._status.text())
        self.assertFalse(viewer.paste_selection("Z"))
        self.assertIn("DNA/IUPAC", viewer._status.text())

    def test_alignment_delete_rows_captures_selection_before_confirmation_and_rebuilds_grid(self) -> None:
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATG-C"),
                AlignmentRecord("IK346", "IK346", "ATGTC"),
                AlignmentRecord("IK347", "IK347", "ATGTA"),
                AlignmentRecord("IK348", "IK348", "ATGTT"),
            ),
        )
        viewer = AlignmentViewer(alignment)
        viewer._grid.select_row("IK346")
        viewer._grid.toggle_row_selection(3)  # IK347; row 0 is Consensus.

        def accept_after_native_focus_change(*_args, **_kwargs):
            viewer._grid.clear_selection()
            return QMessageBox.StandardButton.Yes

        with patch(
            "widgets.viewers.alignment_viewer.QMessageBox.question",
            side_effect=accept_after_native_focus_change,
        ):
            self.assertTrue(viewer.request_delete_selected_rows())

        self.assertEqual(viewer.pending_deleted_row_ids, frozenset({"IK346", "IK347"}))
        self.assertEqual(
            tuple(row.row_id for row in viewer._grid.rows),
            ("__consensus__", "IK345", "IK348"),
        )
        self.assertTrue(viewer._grid.selection.is_empty)
        self.assertIsNone(viewer._grid.current_cell())
        self.assertIn("Unsaved changes • 2 rows deleted", viewer._summary.text())

        # A new selection after the compacted rebuild must use current row IDs,
        # rather than an index that belonged to a removed row.
        self.assertTrue(viewer._grid.select_cell("IK348", 2))
        self.assertEqual(viewer._grid.current_cell(), ("IK348", 2, "G"))
        self.assertTrue(viewer.undo())
        self.assertEqual(
            tuple(row.row_id for row in viewer._grid.rows),
            ("__consensus__", "IK345", "IK346", "IK347", "IK348"),
        )
        self.assertTrue(viewer.redo())
        self.assertEqual(
            tuple(row.row_id for row in viewer._grid.rows),
            ("__consensus__", "IK345", "IK348"),
        )

    def test_alignment_save_then_file_save_and_tab_switch_leave_no_stale_toolbar_actions(self) -> None:
        source = SequenceDataset.from_sequence_pairs(
            "coi-import", "COI Imported", SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"), ("IK346", "ATGT")),
        )
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id=source.dataset_id,
            records=(
                AlignmentRecord("IK345", "IK345", "ATGC"),
                AlignmentRecord("IK346", "IK346", "ATGT"),
            ),
        )
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        controller.open_project(
            Project.create("project", "Project")
            .add_dataset(source)
            .add_dataset(alignment, parent_dataset_id=source.dataset_id)
        )
        toolbar.show()
        viewer = AlignmentViewer(alignment, context=view.viewer_context)
        view.tab_manager.open_viewer(viewer, resource_key="alignment:coi-alignment")
        self.application.processEvents()

        save_action = view.action_manager.action("alignment.save_edited_alignment")
        self.assertIsNotNone(save_action)
        self.assertIsNotNone(view.action_manager.action("alignment.delete_selected_rows"))
        self.assertNotIn("Rows", tuple(action.text() for action in toolbar.actions()))
        viewer._grid.select_row("__consensus__")
        self.assertFalse(viewer.delete_selected_rows_from_derived_dataset())
        viewer._grid.select_row("IK346")
        self.assertTrue(viewer.delete_selected_rows_from_derived_dataset())
        self.assertTrue(viewer.undo())
        self.assertIn("IK346", tuple(row.row_id for row in viewer._grid.rows))
        self.assertTrue(viewer.redo())
        generation_before_file_save = view.action_manager._action_generation
        save_button = toolbar.widgetForAction(save_action)
        self.assertIsNone(save_button)
        save_action.trigger()
        with TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "project.sangerflow"
            controller.save_project_bundle(str(bundle_path))
            loaded = load_project_bundle(bundle_path)
            try:
                revised = loaded.project.get_dataset("coi-alignment_edited")
                self.assertEqual(tuple(record.record_id for record in revised.records), ("IK345",))
            finally:
                loaded.cleanup()
        self.assertEqual(view.action_manager._action_generation, generation_before_file_save)

        controller.activate_tab("Project Summary")
        self.application.processEvents()
        self.assertIsNone(state.active_viewer)
        view.tab_manager.close_all()
        self.application.processEvents()
        self.assertEqual(view.action_manager.action_ids(), ())
        self.assertTrue(state.current_project.has_dataset("coi-alignment_edited"))
        self.assertEqual(tuple(record.record_id for record in alignment.records), ("IK345", "IK346"))
        view.close()

    def test_alignment_viewer_action_opens_alignment_chromatogram_viewer(self) -> None:
        from core.models import SangerRead
        from core.trimming import trim_sequence

        def read(filename: str, sequence: str) -> SangerRead:
            trace_length = max(40, len(sequence) * 10)
            return trim_sequence(
                SangerRead(
                    filename=filename,
                    sequence=sequence,
                    quality=[35 for _ in sequence],
                    traces={base: [10 for _ in range(trace_length)] for base in "ACGT"},
                    base_positions=[5 + index * 8 for index in range(len(sequence))],
                    average_quality=35.0,
                )
            )

        reads = (read("IK345", "ATGC"), read("IK346", "ATGT"))
        alignment = AlignmentDataset(
            alignment_id="coi-alignment",
            name="COI Alignment",
            parent_dataset_id="coi-import",
            records=(
                AlignmentRecord("IK345", "IK345", "ATGC"),
                AlignmentRecord("IK346", "IK346", "ATGT"),
            ),
            metadata={"source_reads": reads},
        )
        state = AppState()
        controller = ProjectController(state)
        tabs = WorkspaceTabs(state, controller)
        tab_manager = TabManager(tabs, state)
        context = ViewerContext(state, controller, tab_manager=tab_manager)
        viewer = AlignmentViewer(alignment, context=context)
        toolbar = QToolBar()
        from app.action_manager import ActionManager

        action_manager = ActionManager(state)
        action_manager.attach_toolbar(toolbar)

        tab_manager.open_viewer(viewer, resource_key="alignment:coi-alignment")
        self.application.processEvents()
        state.set_active_viewer(viewer)

        action = action_manager.action("alignment.review_chromatograms")
        self.assertIsNotNone(action)
        action.trigger()
        self.application.processEvents()

        self.assertIsInstance(tabs.widget(3), AlignmentChromatogramViewer)
        action.trigger()
        self.application.processEvents()
        self.assertEqual(tabs.count(), 4)

    def test_dataset_viewer_does_not_expose_obsolete_placeholder_viewer_action(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "coi-import",
            "COI Imported",
            SourceType.IMPORTED_FASTA,
            (("IK345", "ATGC"),),
        )
        project = Project.create("project-1", "Project 1").add_dataset(dataset)
        state = AppState()
        controller = ProjectController(state)
        view = ProjectView(state, controller)

        controller.open_project(project)
        self.application.processEvents()
        explorer = view.widget(0)
        tabs = view.widget(1)
        toolbar = QToolBar()
        view.action_manager.attach_toolbar(toolbar)
        explorer.setCurrentItem(explorer.topLevelItem(0).child(0).child(0))
        self.application.processEvents()

        self.assertIsNone(view.action_manager.action("dataset.open_placeholder_viewer"))
