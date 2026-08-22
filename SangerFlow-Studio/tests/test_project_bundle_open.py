"""Offscreen integration checks for opening a persisted SangerFlow Project."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.app_state import AppState
import controllers.project_controller as project_controller_module
from controllers.project_controller import ProjectController
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.models import SangerRead
from core.lineage import RecordProvenance, RecordRef
from core.project import Project, RevisionOperation
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import save_project_bundle
from app.qt_runtime import configure_qt_plugins
configure_qt_plugins()
from PySide6.QtWidgets import QApplication
from views.project_view import ProjectView


def _bundle_project() -> Project:
    dataset = SequenceDataset.from_sequence_pairs(
        "bundle-imported-fasta",
        "Imported FASTA",
        SourceType.IMPORTED_FASTA,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )
    project = Project.create("bundle-project", "Bundle Project", {"marker": "COI"})
    project = project.add_dataset(dataset)
    return project.add_analysis_result(
        AnalysisResult(
            result_id="bundle-blast",
            name="BLAST",
            result_type=AnalysisResultType.BLAST,
            parent_dataset_id=dataset.dataset_id,
        )
    )


class ProjectBundleOpenTests(unittest.TestCase):
    @staticmethod
    def _read_ids(project: Project) -> tuple[tuple[str, tuple[str, ...], tuple[tuple[RecordRef, ...], ...]], ...]:
        """Stable identity snapshot; intentionally ignores transient SangerRead objects."""

        values = []
        for entry in project.dataset_entries:
            dataset = entry.dataset
            if isinstance(dataset, SequenceDataset):
                values.append((
                    dataset.dataset_id,
                    dataset.sequence_ids,
                    tuple(record.provenance.source_records for record in dataset.records),
                ))
        return tuple(values)

    def test_controller_loads_bundle_and_refreshes_project_tree_and_inspector(self) -> None:
        with TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "bundle.sangerflow"
            save_project_bundle(_bundle_project(), bundle_path)

            state = AppState()
            controller = ProjectController(state)
            application = QApplication.instance() or QApplication([])
            view = ProjectView(state, controller)
            loaded = controller.open_project_bundle(str(bundle_path))
            application.processEvents()

            self.assertEqual(state.current_project.name, "Bundle Project")
            self.assertIs(state.current_repository, loaded.repository)
            explorer = view.widget(0)
            root = explorer.topLevelItem(0)
            self.assertEqual(root.text(0), "Bundle Project")
            self.assertEqual(root.child(0).text(0), "Working Datasets")
            self.assertEqual(root.child(0).child(0).text(0), "Imported FASTA")
            self.assertEqual(root.child(2).child(0).text(0), "BLAST")

            explorer.setCurrentItem(root.child(0).child(0))
            application.processEvents()
            inspector = view.widget(2)
            self.assertEqual(inspector._title.text(), "Dataset")
            inspector_values = [
                inspector._layout.itemAt(index).widget().text()
                for index in range(inspector._layout.count())
                if inspector._layout.itemAt(index).widget() is not None
            ]
            self.assertIn("bundle-imported-fasta", inspector_values)

            state.close_current_bundle()

    def test_controller_saves_current_project_bundle_and_clears_dirty_state(self) -> None:
        with TemporaryDirectory() as directory:
            bundle_path = Path(directory) / "saved.sangerflow"
            state = AppState()
            controller = ProjectController(state)
            state.set_project(_bundle_project())
            state.mark_dirty()

            saved_path = controller.save_project_bundle(str(bundle_path))

            self.assertEqual(saved_path, str(bundle_path))
            self.assertTrue(bundle_path.is_file())
            self.assertFalse(state.is_dirty)
            self.assertEqual(state.current_bundle_path, str(bundle_path))

    def test_bundle_reload_reattaches_ab1_source_reference_when_source_path_exists(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ab1_path = root / "IK345.ab1"
            ab1_path.write_bytes(b"placeholder")
            parent = SequenceDataset(
                dataset_id="ab1-dataset",
                name="AB1 Dataset",
                source_type=SourceType.AB1_TRIMMED,
                records=(
                    SequenceRecord(
                        "IK345.ab1",
                        "ATGC",
                        metadata={"source_filepath": str(ab1_path)},
                    ),
                ),
            )
            alignment = AlignmentDataset(
                alignment_id="ab1-alignment",
                name="AB1 Alignment",
                parent_dataset_id=parent.dataset_id,
                records=(
                    AlignmentRecord(
                        record_id="IK345.ab1",
                        source_record_id="IK345.ab1",
                        aligned_sequence="ATG-C",
                    ),
                ),
            )
            project = Project.create("project", "Project").add_dataset(parent).add_dataset(
                alignment,
                parent_dataset_id=parent.dataset_id,
            )
            bundle_path = root / "project.sangerflow"
            save_project_bundle(project, bundle_path)

            fake_read = SangerRead(
                filename="IK345.ab1",
                sequence="ATGC",
                quality=[30, 31, 32, 33],
                traces={"A": [0], "C": [0], "G": [0], "T": [0]},
                base_positions=[0, 1, 2, 3],
            )
            original_read_ab1 = project_controller_module.read_ab1
            original_trim_sequence = project_controller_module.trim_sequence
            project_controller_module.read_ab1 = lambda _path: fake_read
            project_controller_module.trim_sequence = lambda read: read
            try:
                state = AppState()
                controller = ProjectController(state)
                controller.open_project_bundle(str(bundle_path))
            finally:
                project_controller_module.read_ab1 = original_read_ab1
                project_controller_module.trim_sequence = original_trim_sequence

            loaded_parent = state.current_project.get_dataset("ab1-dataset")
            self.assertIs(loaded_parent.records[0].source_reference, fake_read)
            self.assertEqual(state.current_project.lineage("ab1-alignment"), ("ab1-dataset", "ab1-alignment"))
            state.close_current_bundle()

    def test_bundle_reload_uses_workspace_relative_raw_data_after_workspace_move(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original_workspace = root / "original"
            moved_workspace = root / "移動先 workspace"
            original_raw = original_workspace / "Raw_Data" / "サンプル 1.ab1"
            moved_raw = moved_workspace / "Raw_Data" / "サンプル 1.ab1"
            original_raw.parent.mkdir(parents=True)
            moved_raw.parent.mkdir(parents=True)
            original_raw.write_bytes(b"old")
            moved_raw.write_bytes(b"new")
            parent = SequenceDataset(
                dataset_id="ab1-dataset",
                name="AB1 Dataset",
                source_type=SourceType.AB1_TRIMMED,
                records=(
                    SequenceRecord(
                        "sample",
                        "ATGC",
                        metadata={
                            "source_filepath": str(original_raw),
                            "workspace_relative_path": "Raw_Data/サンプル 1.ab1",
                        },
                    ),
                ),
            )
            project = Project.create("project", "Project").add_dataset(parent)
            bundle_path = moved_workspace / "project.sangerflow"
            save_project_bundle(project, bundle_path)
            original_raw.unlink()

            fake_read = SangerRead(
                filename="サンプル 1.ab1",
                sequence="ATGC",
                quality=[30, 31, 32, 33],
                traces={"A": [0], "C": [0], "G": [0], "T": [0]},
                base_positions=[0, 1, 2, 3],
            )
            observed_paths = []
            original_read_ab1 = project_controller_module.read_ab1
            original_trim_sequence = project_controller_module.trim_sequence
            project_controller_module.read_ab1 = lambda path: observed_paths.append(path) or fake_read
            project_controller_module.trim_sequence = lambda read: read
            try:
                state = AppState()
                ProjectController(state).open_project_bundle(str(bundle_path))
            finally:
                project_controller_module.read_ab1 = original_read_ab1
                project_controller_module.trim_sequence = original_trim_sequence

            self.assertEqual(tuple(Path(path).resolve() for path in observed_paths), (moved_raw.resolve(),))
            self.assertIs(
                state.current_project.get_dataset("ab1-dataset").records[0].source_reference,
                fake_read,
            )
            state.close_current_bundle()

    def test_bundle_reload_leaves_source_unattached_when_raw_data_is_missing(self) -> None:
        """A moved bundle remains usable even when its external AB1 is absent."""

        with TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            workspace.mkdir()
            missing_raw = workspace / "Raw_Data" / "missing sample.ab1"
            dataset = SequenceDataset(
                dataset_id="ab1-dataset",
                name="AB1 Dataset",
                source_type=SourceType.AB1_TRIMMED,
                records=(
                    SequenceRecord(
                        "sample",
                        "ATGC",
                        metadata={
                            "source_filepath": "/former/mac/workspace/Raw_Data/missing sample.ab1",
                            "workspace_relative_path": "Raw_Data/missing sample.ab1",
                        },
                    ),
                ),
            )
            bundle_path = workspace / "project.sangerflow"
            save_project_bundle(Project.create("project", "Project").add_dataset(dataset), bundle_path)

            state = AppState()
            controller = ProjectController(state)
            controller.open_project_bundle(str(bundle_path))

            record = state.current_project.get_dataset("ab1-dataset").records[0]
            self.assertFalse(missing_raw.exists())
            self.assertIsNone(record.source_reference)
            self.assertEqual(record.metadata["workspace_relative_path"], "Raw_Data/missing sample.ab1")
            self.assertEqual(len(controller.last_warnings), 1)
            self.assertIn("Missing AB1 source", controller.last_warnings[0])
            state.close_current_bundle()

    def test_reopening_bundle_is_read_only_for_record_ids_revisions_and_provenance(self) -> None:
        """Open/close cycles never allocate or rewrite record IDs."""

        source = SequenceDataset(
            "ab1", "AB1 reads", SourceType.AB1_TRIMMED,
            (
                SequenceRecord("C2_FishF1", "ATGC", metadata={"source_filename": "C2_FishF1.ab1"}),
                SequenceRecord("R1_FishF1", "ATGT", metadata={"source_filename": "R1_FishF1.ab1"}),
            ),
        )
        metadata_revision = SequenceDataset(
            "ab1_metadata", "AB1 reads", SourceType.AB1_TRIMMED,
            tuple(
                SequenceRecord(
                    record.sequence_id, record.sequence, metadata={**record.metadata, "Location": "Cirebon"},
                    provenance=RecordProvenance((RecordRef("ab1", record.sequence_id),)),
                )
                for record in source.records
            ),
        )
        blast_metadata_revision = SequenceDataset(
            "ab1_blast_metadata", "AB1 reads", SourceType.AB1_TRIMMED,
            tuple(
                SequenceRecord(
                    record.sequence_id, record.sequence,
                    metadata={**record.metadata, "blast_scientific_name": "Rhynchobatus springeri"},
                    provenance=RecordProvenance((RecordRef("ab1_metadata", record.sequence_id),)),
                )
                for record in metadata_revision.records
            ),
        )
        derived = SequenceDataset(
            "springeri", "Springeri", SourceType.DERIVED,
            (
                SequenceRecord(
                    "C2_FishF1", "ATGC", metadata={"blast_scientific_name": "Rhynchobatus springeri"},
                    provenance=RecordProvenance((RecordRef("ab1_blast_metadata", "C2_FishF1"),)),
                ),
            ),
        )
        project = (
            Project.create("project", "Project")
            .add_dataset(source)
            .add_dataset_revision("ab1", metadata_revision, operation=RevisionOperation.METADATA_MERGE)
            .add_dataset_revision(
                "ab1_metadata", blast_metadata_revision, operation=RevisionOperation.METADATA_MERGE
            )
            .add_dataset(derived)
        )
        expected = self._read_ids(project)
        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "project.sangerflow"
            save_project_bundle(project, bundle)
            for _ in range(3):
                state = AppState()
                controller = ProjectController(state)
                controller.open_project_bundle(str(bundle))
                self.assertEqual(self._read_ids(state.current_project), expected)
                state.close_current_bundle()

    def test_copy_mode_uses_original_filename_for_record_id_not_raw_data_collision_suffix(self) -> None:
        """Raw_Data collision suffixes are storage-only and never stable IDs."""

        class _Tabs:
            def open_viewer(self, _viewer, *, resource_key: str) -> str:
                return resource_key

        def _fake_read(path: str) -> SangerRead:
            return SangerRead(
                filename=Path(path).name,
                sequence="ATGC",
                quality=[40, 40, 40, 40],
                traces={"A": [0], "C": [0], "G": [0], "T": [0]},
                base_positions=[0, 1, 2, 3],
            )

        application = QApplication.instance() or QApplication([])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "incoming" / "C2_FishF1.ab1"
            source.parent.mkdir()
            source.write_bytes(b"source")
            bundle = root / "project.sangerflow"
            raw_data = root / "Raw_Data"
            raw_data.mkdir()
            (raw_data / source.name).write_bytes(b"existing")

            state = AppState()
            controller = ProjectController(state)
            controller._tab_manager = _Tabs()
            state.set_project(Project.create("project", "Project"), bundle_path=str(bundle))
            with (
                patch("controllers.project_controller.read_ab1", side_effect=_fake_read),
                patch("controllers.project_controller.trim_sequence", side_effect=lambda read: read),
                patch("controllers.project_controller.ChromatogramViewer"),
            ):
                controller._open_ab1_files(
                    (source,), source_label="AB1 Folder: incoming", source_batch="incoming", source_file_handling="copy"
                )

            imported = state.current_project.dataset_entries[-1].dataset
            self.assertEqual(imported.sequence_ids, ("C2_FishF1",))
            self.assertEqual(imported.metadata["source_batch"], "incoming")
            self.assertEqual(imported.records[0].metadata["source_batch"], "incoming")
            self.assertEqual(imported.records[0].metadata["source_filename"], "C2_FishF1.ab1")
            self.assertEqual(Path(imported.records[0].metadata["source_filepath"]).name, "C2_FishF1_2.ab1")
            save_project_bundle(state.current_project, bundle)

            reloaded_state = AppState()
            reloaded_controller = ProjectController(reloaded_state)
            with (
                patch("controllers.project_controller.read_ab1", side_effect=_fake_read),
                patch("controllers.project_controller.trim_sequence", side_effect=lambda read: read),
            ):
                reloaded_controller.open_project_bundle(str(bundle))
            reloaded = reloaded_state.current_project.dataset_entries[-1].dataset
            self.assertEqual(reloaded.sequence_ids, ("C2_FishF1",))
            self.assertEqual(reloaded.metadata["source_batch"], "incoming")
            self.assertEqual(reloaded.records[0].metadata["source_batch"], "incoming")
            self.assertEqual(
                reloaded.records[0].source_reference.filename,
                "C2_FishF1.ab1",
            )
            application.processEvents()
            state.close_current_bundle()
            reloaded_state.close_current_bundle()

    def test_folder_import_uses_selected_folder_name_as_source_batch_not_workspace_names(self) -> None:
        class _Tabs:
            def open_viewer(self, _viewer, *, resource_key: str):
                return resource_key

        def _fake_read(path: str) -> SangerRead:
            return SangerRead(
                filename=Path(path).name,
                sequence="ATGC",
                quality=[40, 40, 40, 40],
                traces={"A": [0], "C": [0], "G": [0], "T": [0]},
                base_positions=[0, 1, 2, 3],
            )

        with TemporaryDirectory() as directory:
            root = Path(directory)
            selected_folder = root / "Cirebon"
            selected_folder.mkdir()
            (selected_folder / "R1_FishF1.ab1").write_bytes(b"source")

            state = AppState()
            controller = ProjectController(state)
            controller._tab_manager = _Tabs()
            with (
                patch("controllers.project_controller.read_ab1", side_effect=_fake_read),
                patch("controllers.project_controller.trim_sequence", side_effect=lambda read: read),
                patch("controllers.project_controller.ChromatogramViewer"),
            ):
                controller.open_ab1_folder(str(selected_folder))

            imported = state.current_project.dataset_entries[-1].dataset
            self.assertEqual(imported.metadata["source_batch"], "Cirebon")
            self.assertEqual(imported.records[0].metadata["source_batch"], "Cirebon")
            self.assertNotIn(imported.metadata["source_batch"], {"result", "All", "Raw_Data"})

    def test_unsaved_session_dataset_changes_do_not_leak_into_next_bundle_open(self) -> None:
        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "saved.sangerflow"
            saved = _bundle_project()
            save_project_bundle(saved, bundle)
            transient = SequenceDataset.from_sequence_pairs(
                "session_only", "Unsaved session", SourceType.IMPORTED_FASTA, (("C2_FishF1_5", "ATGC"),)
            )
            state = AppState()
            state.set_project(saved.add_dataset(transient), dirty=True)

            reopened_state = AppState()
            ProjectController(reopened_state).open_project_bundle(str(bundle))
            self.assertEqual(reopened_state.current_project.dataset_ids, saved.dataset_ids)
            self.assertNotIn("session_only", reopened_state.current_project.dataset_ids)
            self.assertEqual(
                reopened_state.current_project.get_dataset("bundle-imported-fasta").sequence_ids,
                ("IK345", "IK346"),
            )
            reopened_state.close_current_bundle()
