"""Project-facing controller; views delegate state changes here."""

from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from datetime import datetime, timezone

from PySide6.QtCore import QObject, QThread, Qt, Slot
from PySide6.QtWidgets import QDialog, QMessageBox

from app.app_state import AppState
from app.gui_thread import assert_main_gui_thread
from app.selection import SelectionKind, StudioSelection
from controllers.identification_workers import BlastWorker
from core.ab1_reader import read_ab1
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.models import SangerRead
from core.blast_filter import BlastResultSelection
from core.blast_result import BlastAnalysisMode, BlastResultDataset
from core.bold_filter import BoldResultSelection
from core.bold_result import BoldResultDataset
from core.chromatogram_alignment import align_reads
from core.fasta_dataset import read_fasta_dataset
from core.lineage import (
    LineageRelation,
    LineageRelationType,
    LineageSourceKind,
    RecordProvenance,
    RecordRef,
)
from metadata.sample_metadata import (
    import_sample_metadata,
    merge_sample_metadata,
    merge_sample_metadata_for_datasets,
)
from core.project import DerivationType, Project, ProjectDatasetEntry, RevisionOperation, RevisionState
from core.result_repository import FilesystemResultRepository
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import LoadedProjectBundle, load_project_bundle, save_project_bundle
from core.trimming import trim_sequence
from widgets.viewers import ViewerContext, ViewerRegistry
from widgets.viewers.chromatogram_viewer import ChromatogramViewer, reads_from_dataset
from widgets.viewers.consensus_review_viewer import build_reviewed_consensus_dataset
from widgets.viewers.fr_consensus_review import (
    ConsensusReviewManagerViewer,
    ConsensusSampleRow,
    MultipleConsensusReviewViewer,
    SingleConsensusReviewViewer,
    build_consensus_sample_rows,
)
from workflow.project_reviewed_consensus import add_reviewed_consensus_dataset_to_project
from workflow.reviewed_consensus_dataset import create_dataset_from_reviewed_consensus
from workflow.blast_selection_dataset import create_dataset_from_blast_selection
from workflow.cross_dataset_builder import CrossDatasetBuild, build_dataset_from_record_refs
from workflow.blast_workflow import run_blast_workflow
from workflow.bold_identification_service import BoldIdentificationRunner, BoldIdentificationUnavailableError
from workflow.bold_selection_dataset import create_dataset_from_bold_selection
from workflow.bold_workflow import run_bold_workflow
from workflow.project_blast import add_blast_result_to_project
from workflow.project_bold import add_bold_result_to_project
from workflow.mafft_workflow import align_sequence_dataset
from workflow.ncbi_blast_xml_import import BlastXmlImportPreview, import_ncbi_blast_xml
from widgets.identification_service_dialogs import (
    BlastMetadataSettings, BlastSettingsDialog, BlastWebsiteDialog, IdentificationProgressDialog,
)
from widgets.alignment_settings_dialog import AlignmentSettings, AlignmentSettingsDialog
from widgets.consensus_settings_dialog import ConsensusSettingsDialog
from services.metadata_template import (
    write_metadata_excel_template,
    write_project_metadata_excel_template,
)
from services.application_settings import resolve_studio_mafft_executable
from services.project_workspace import (
    ProjectWorkspace,
    create_project_workspace,
    workspace_for_bundle,
)


class _AsyncBlastGuiReceiver(QObject):
    """Main-thread-only receiver for data emitted by one BlastWorker."""

    def __init__(
        self,
        controller: "ProjectController",
        *,
        source_dataset: object,
        query_dataset: SequenceDataset,
        parent_dataset_id: str,
        progress_dialog: IdentificationProgressDialog,
        thread: QThread,
        worker: BlastWorker,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._source_dataset = source_dataset
        self._query_dataset = query_dataset
        self._parent_dataset_id = parent_dataset_id
        self._progress_dialog = progress_dialog
        self._thread = thread
        self._worker = worker

    @Slot(object)
    def update_progress(self, progress: object) -> None:
        assert_main_gui_thread("_AsyncBlastGuiReceiver.update_progress")
        self._progress_dialog.update_progress(progress)

    @Slot(object)
    def complete(self, result: object) -> None:
        assert_main_gui_thread("_AsyncBlastGuiReceiver.complete")
        self._controller._complete_async_blast(
            result,
            source_dataset=self._source_dataset,
            query_dataset=self._query_dataset,
            parent_dataset_id=self._parent_dataset_id,
            progress_dialog=self._progress_dialog,
        )

    @Slot(str)
    def fail(self, message: str) -> None:
        assert_main_gui_thread("_AsyncBlastGuiReceiver.fail")
        self._controller._fail_async_blast(message, self._progress_dialog)

    @Slot()
    def cleanup(self) -> None:
        assert_main_gui_thread("_AsyncBlastGuiReceiver.cleanup")
        self._controller._forget_identification_thread(
            self._thread,
            self._worker,
            self._progress_dialog,
            receiver=self,
        )
        self.deleteLater()


class ProjectController(QObject):
    """Coordinates views with existing immutable SangerFlow Project models."""

    def __init__(self, state: AppState, *, mafft_executable_resolver=None) -> None:
        super().__init__()
        self._state = state
        self._viewer_registry: ViewerRegistry | None = None
        self._viewer_context: ViewerContext | None = None
        self._tab_manager: object | None = None
        self._last_warnings: tuple[str, ...] = ()
        self._blast_runner = None
        self._bold_runner = None
        self._temporary_repository_directory: TemporaryDirectory | None = None
        self._identification_threads: list[tuple[QThread, object, object, object]] = []
        self._mafft_executable_resolver = (
            mafft_executable_resolver or resolve_studio_mafft_executable
        )

    def __del__(self) -> None:
        temporary_directory = getattr(self, "_temporary_repository_directory", None)
        if temporary_directory is not None:
            temporary_directory.cleanup()

    @property
    def last_warnings(self) -> tuple[str, ...]:
        """Warnings from the last controller operation, suitable for GUI display."""

        return self._last_warnings

    def configure_viewer_framework(
        self,
        *,
        viewer_registry: ViewerRegistry,
        viewer_context: ViewerContext,
        tab_manager: object,
    ) -> None:
        self._viewer_registry = viewer_registry
        self._viewer_context = viewer_context
        self._tab_manager = tab_manager

    def open_project_records_viewer(self) -> object:
        """Open the single Project-wide record browser through the TabManager."""

        project = self._require_current_project()
        if self._viewer_context is None or self._tab_manager is None:
            raise ValueError("Project Records Viewer is not configured.")
        from widgets.viewers.project_records_viewer import create_project_records_viewer

        viewer = create_project_records_viewer(self._viewer_context, project)
        self._tab_manager.open_viewer(
            viewer,
            resource_key=f"project-records:{project.project_id}",
        )
        return viewer

    def configure_identification_runners(self, *, blast_runner=None, bold_runner=None) -> None:
        """Install optional test/application runners without coupling GUI to network code."""

        self._blast_runner = blast_runner
        self._bold_runner = bold_runner

    def open_project(self, project: object) -> None:
        self._state.set_project(project)

    def create_project(
        self,
        name: str,
        *,
        location: str | Path | None = None,
        create_workspace: bool = True,
    ) -> Project:
        """Create a logical Project and, optionally, its Studio workspace shell."""

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Project name is required.")
        project = Project.create(
            project_id=_safe_identifier(name) or "sangerflow_project",
            name=name.strip(),
            metadata={"created_by": "SangerFlow-Studio"},
        )
        if not create_workspace:
            self._state.set_project(project, dirty=True)
            return project
        if location is None:
            raise ValueError("Workspace location is required.")
        workspace = create_project_workspace(location, name)
        try:
            save_project_bundle(project, workspace.bundle_path)
        except Exception:
            # No Project is published until its initial bundle has been safely written.
            raise
        self._state.set_project(
            project,
            dirty=False,
            bundle_path=str(workspace.bundle_path),
        )
        return project

    def close_project(self) -> None:
        """Close all non-persistent viewer state before resetting the Studio shell."""

        close_all = getattr(self._tab_manager, "close_all", None)
        if callable(close_all):
            close_all()
        self._state.close_project()

    def current_workspace(self) -> ProjectWorkspace | None:
        """Return the optional filesystem workspace next to the active Bundle."""

        return workspace_for_bundle(self._state.current_bundle_path)

    def export_default_directory(self) -> str:
        workspace = self.current_workspace()
        if workspace is None:
            return ""
        workspace.ensure_directories()
        return str(workspace.exports_directory)

    def metadata_default_directory(self) -> str:
        workspace = self.current_workspace()
        if workspace is None:
            return ""
        workspace.ensure_directories()
        return str(workspace.metadata_directory)

    def create_metadata_excel_template(
        self,
        dataset: SequenceDataset,
        filepath: str | Path,
    ) -> str:
        project = self._state.current_project
        if not isinstance(project, Project) or not project.has_dataset(dataset.dataset_id):
            raise ValueError("Dataset must be registered in the current Project.")
        return str(write_metadata_excel_template(dataset, filepath))

    def create_project_metadata_excel_template(self, filepath: str | Path) -> str:
        """Create a metadata template for the current Project-wide record scope."""

        project = self._require_current_project()
        datasets = tuple(
            entry.dataset for entry in project.current_dataset_entries()
            if isinstance(entry.dataset, SequenceDataset)
        )
        return str(write_project_metadata_excel_template(datasets, filepath))

    def rename_dataset(self, dataset_id: str, display_name: str) -> Project:
        project = self._require_current_project()
        updated = project.rename_dataset(dataset_id, display_name.strip())
        self._state.replace_project(updated, dirty=True)
        return updated

    def remove_dataset(self, dataset_id: str) -> Project:
        project = self._require_current_project()
        # Project.remove_dataset() deliberately owns scientific dependency
        # validation.  Revision succession is a Studio working-state concern:
        # never allow an earlier immutable revision to be deleted while a later
        # revision still references it as its predecessor.
        if any(
            entry.supersedes_dataset_id == dataset_id
            for entry in project.dataset_entries
        ):
            raise ValueError(
                "Cannot remove this Dataset because a later immutable revision exists."
            )
        updated = project.remove_dataset(dataset_id)
        self._state.replace_project(updated, dirty=True)
        return updated

    def dataset_delete_dependencies(self, dataset_id: str) -> tuple[str, ...]:
        """Return human-readable blockers before a safe leaf deletion attempt."""

        project = self._require_current_project()
        project.get_entry(dataset_id)
        labels: list[str] = []
        for child_id in project.child_dataset_ids(dataset_id):
            labels.append(project.get_entry(child_id).display_name)
        for result in project.analysis_results:
            if result.parent_dataset_id == dataset_id:
                labels.append(result.display_name)
        for entry in project.dataset_entries:
            if entry.supersedes_dataset_id == dataset_id:
                labels.append(f"{entry.display_name} (later revision)")
        return tuple(labels)

    def archive_logical_dataset(self, logical_id: str) -> Project:
        project = self._require_current_project()
        updated = project.archive_logical_dataset(logical_id)
        self._state.replace_project(updated, dirty=True)
        return updated

    def restore_logical_dataset(self, logical_id: str) -> Project:
        project = self._require_current_project()
        updated = project.restore_logical_dataset(logical_id)
        self._state.replace_project(updated, dirty=True)
        return updated

    def _require_current_project(self) -> Project:
        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        return project

    @staticmethod
    def _require_current_revision(project: Project, dataset_id: str) -> ProjectDatasetEntry:
        """Reject stale and archived revision edits before creating any branch."""

        entry = project.get_entry(dataset_id)
        if entry.revision_state is RevisionState.ARCHIVED:
            raise ValueError(
                "This logical Dataset is archived. Restore it before editing."
            )
        if not project.is_current_revision(dataset_id):
            raise ValueError(
                "This dataset revision is no longer current. Open the current revision before editing."
            )
        return entry

    def _open_revision_viewer(self, dataset: object) -> None:
        """Focus the newly-created immutable revision when the Studio is configured."""

        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return
        viewer = self._viewer_registry.create_viewer_for(dataset, self._viewer_context)
        resource_id = getattr(dataset, "alignment_id", None) or getattr(dataset, "dataset_id", None)
        prefix = "alignment" if isinstance(dataset, AlignmentDataset) else "dataset"
        self._tab_manager.open_viewer(viewer, resource_key=f"{prefix}:{resource_id}")

    def open_project_bundle(self, filepath: str) -> LoadedProjectBundle:
        """Load a bundle through persistence, then publish it to the Studio state."""

        self._last_warnings = ()
        loaded_bundle = load_project_bundle(filepath)
        project, warnings = _reattach_ab1_source_references(
            loaded_bundle.project,
            workspace_root=Path(filepath).expanduser().resolve().parent,
        )
        if project is not loaded_bundle.project:
            loaded_bundle.project = project
        self._last_warnings = warnings
        self._state.set_loaded_project_bundle(loaded_bundle, bundle_path=str(Path(filepath)))
        return loaded_bundle

    def save_project_bundle(self, filepath: str | None = None) -> str:
        """Save the current Project through the shared persistence bundle layer."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        output_path = filepath or self._state.current_bundle_path
        if not output_path:
            raise ValueError("Save Project requires a destination path.")
        save_project_bundle(
            project,
            output_path,
            repository=self._state.current_repository,
        )
        self._state.set_bundle_path(str(Path(output_path)))
        self._state.mark_clean()
        return str(Path(output_path))

    def open_ab1_folder(
        self,
        folderpath: str,
        *,
        source_file_handling: str = "reference",
    ) -> str | None:
        """Read AB1 files through existing core logic and open a chromatogram tab."""

        if self._tab_manager is None:
            return None
        folder = Path(folderpath)
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"AB1 folder does not exist: {folderpath}")
        files = tuple(
            sorted(
                path
                for path in folder.iterdir()
                if path.is_file() and path.suffix.lower() in {".ab1", ".abi"}
            )
        )
        if not files:
            raise ValueError(f"No AB1 files found in folder: {folderpath}")

        return self._open_ab1_files(
            files,
            source_label=f"AB1 Folder: {folder.name}",
            source_batch=folder.name,
            source_file_handling=source_file_handling,
        )

    def open_ab1_file(
        self,
        filepath: str,
        *,
        source_file_handling: str = "reference",
    ) -> str | None:
        """Open one AB1/ABI file through the same dataset workflow as a folder."""

        path = Path(filepath)
        if not path.is_file() or path.suffix.lower() not in {".ab1", ".abi"}:
            raise ValueError(f"AB1 file does not exist or has an unsupported suffix: {filepath}")
        return self._open_ab1_files(
            (path,),
            source_label=f"AB1 file: {path.name}",
            source_batch=path.parent.name,
            source_file_handling=source_file_handling,
        )

    def _open_ab1_files(
        self,
        files: tuple[Path, ...],
        *,
        source_label: str,
        source_batch: str | None = None,
        source_file_handling: str = "reference",
    ) -> str | None:
        if self._tab_manager is None:
            return None
        # Copy mode may add ``_2``, ``_3`` … solely to avoid overwriting an
        # existing raw *file* in the workspace.  That storage collision must
        # never become part of the biological/stable SequenceRecord ID.
        original_filenames = tuple(path.name for path in files)
        # The caller captures this from the user-selected original import
        # location before copy mode moves physical files into Raw_Data.  It is
        # researcher-facing provenance, never a dataset display name or a
        # replacement for RecordRef(dataset_id, sequence_id).
        canonical_source_batch = str(source_batch or _source_batch_from_import_label(source_label)).strip()
        source_stem = files[0].parent.name if len(files) > 1 else files[0].stem
        files = self._resolve_ab1_source_files(files, source_file_handling)
        reads = []
        workspace = self.current_workspace() if source_file_handling == "copy" else None
        for filepath, original_filename in zip(files, original_filenames):
            read = trim_sequence(read_ab1(str(filepath)))
            read.filename = original_filename
            setattr(read, "_sangerflow_source_filepath", str(filepath))
            if workspace is not None:
                try:
                    relative_path = filepath.relative_to(workspace.root).as_posix()
                except ValueError:
                    relative_path = None
                if relative_path is not None:
                    setattr(read, "_sangerflow_workspace_relative_path", relative_path)
            reads.append(read)

        dataset = _sequence_dataset_from_reads(
            reads,
            dataset_id=_unique_dataset_id(
                self._state.project,
                _safe_identifier(source_stem) or "ab1_reads",
            ),
            name=f"AB1 reads: {source_stem}",
            metadata={
                "source": source_label,
                "source_batch": canonical_source_batch,
                "source_filepaths": tuple(str(path) for path in files),
                "read_count": len(reads),
                "creation_context": "SangerFlow-Studio AB1 open",
            },
        )
        project = self._state.project
        if project is None:
            project = Project.create(
                project_id=_safe_identifier(source_stem) or "sangerflow_project",
                name=f"Project: {source_stem}",
                metadata={"created_by": "SangerFlow-Studio", "source": source_label},
            )
        project = project.add_dataset(
            dataset,
            derivation_type=DerivationType.TRIMMED_FROM_READS,
            metadata={"added_by": "AB1 Open"},
        )
        self._state.replace_project(project, dirty=True)

        viewer = ChromatogramViewer(
            reads,
            title=f"Chromatograms: {source_stem}",
            source_object_id=dataset.dataset_id,
            context=self._viewer_context,
            source_dataset=dataset,
        )
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"chromatogram:{dataset.dataset_id}",
        )

    def _resolve_ab1_source_files(
        self,
        files: tuple[Path, ...],
        source_file_handling: str,
    ) -> tuple[Path, ...]:
        if source_file_handling == "reference":
            return files
        if source_file_handling != "copy":
            raise ValueError("source_file_handling must be 'reference' or 'copy'")
        workspace = self.current_workspace()
        if workspace is None:
            raise ValueError("Copying AB1 files requires a saved Project Workspace.")
        workspace.ensure_directories()
        copied: list[Path] = []
        for source in files:
            destination = _unique_copy_destination(workspace.raw_data_directory, source.name)
            try:
                shutil.copy2(source, destination)
            except OSError as error:
                raise ValueError(f"could not copy AB1 file '{source.name}': {error}") from error
            copied.append(destination)
        return tuple(copied)

    def import_sample_metadata_for_dataset(
        self,
        dataset: SequenceDataset,
        filepath: str,
    ) -> SequenceDataset:
        """Merge existing CSV/XLSX metadata into a derived project dataset."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("Sample metadata can only be imported for a SequenceDataset.")
        previous_entry = self._require_current_revision(project, dataset.dataset_id)

        metadata_table = import_sample_metadata(filepath)
        merged = merge_sample_metadata(dataset, metadata_table)
        derived_id = _unique_dataset_id(project, f"{dataset.dataset_id}_metadata")
        derived = _copy_sequence_dataset(
            merged,
            dataset_id=derived_id,
            name=dataset.name,
            metadata={
                **dict(merged.metadata),
                "source_dataset_id": dataset.dataset_id,
                "derived_from": "SAMPLE_METADATA_MERGE",
            },
        )
        updated = project.add_dataset_revision(
            dataset.dataset_id,
            derived,
            operation=RevisionOperation.METADATA_MERGE,
            display_name=previous_entry.display_name,
            parent_dataset_id=previous_entry.parent_dataset_id,
            derivation_type=previous_entry.derivation_type,
            lineage_relations=previous_entry.lineage_relations,
            metadata={
                **dict(previous_entry.metadata),
                "added_by": "Sample Metadata Import Revision",
                "derivation_detail": "SAMPLE_METADATA_MERGE",
                "metadata_filepath": str(filepath),
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        if (
            self._viewer_registry is not None
            and self._viewer_context is not None
            and self._tab_manager is not None
        ):
            viewer = self._viewer_registry.create_viewer_for(derived, self._viewer_context)
            self._tab_manager.open_viewer(
                viewer,
                resource_key=f"dataset:{derived.dataset_id}",
            )
        return derived

    def import_sample_metadata_for_project(self, filepath: str) -> tuple[SequenceDataset, ...]:
        """Apply metadata across all current SequenceDataset records as one scope.

        Project-wide record identity remains ``RecordRef(dataset_id, sequence_id)``;
        ``source_batch`` is only used by the metadata matcher when duplicate
        sample IDs require it.
        """
        project = self._require_current_project()
        entries = tuple(
            entry for entry in project.current_dataset_entries()
            if isinstance(entry.dataset, SequenceDataset)
        )
        if not entries:
            raise ValueError("No current SequenceDataset is available for metadata import.")
        metadata_table = import_sample_metadata(filepath)
        merged_datasets = merge_sample_metadata_for_datasets(
            tuple(entry.dataset for entry in entries), metadata_table
        )
        updated = project
        derived_datasets: list[SequenceDataset] = []
        for entry, merged in zip(entries, merged_datasets):
            derived = _copy_sequence_dataset(
                merged,
                dataset_id=_unique_dataset_id(updated, f"{merged.dataset_id}_metadata"),
                name=merged.name,
                metadata={
                    **dict(merged.metadata),
                    "source_dataset_id": merged.dataset_id,
                    "derived_from": "SAMPLE_METADATA_MERGE",
                },
            )
            updated = updated.add_dataset_revision(
                entry.dataset.dataset_id,
                derived,
                operation=RevisionOperation.METADATA_MERGE,
                display_name=entry.display_name,
                parent_dataset_id=entry.parent_dataset_id,
                derivation_type=entry.derivation_type,
                lineage_relations=entry.lineage_relations,
                metadata={
                    **dict(entry.metadata),
                    "added_by": "Sample Metadata Import Revision",
                    "derivation_detail": "SAMPLE_METADATA_MERGE",
                    "metadata_filepath": str(filepath),
                },
            )
            derived_datasets.append(derived)
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        return tuple(derived_datasets)

    def create_dataset_revision_with_record_renames(
        self,
        dataset: SequenceDataset,
        rename_by_id: dict[str, str],
        *,
        operation: RevisionOperation,
    ) -> SequenceDataset:
        """Create one full-dataset rename revision without creating a subset.

        Each new record directly references the immediately preceding immutable
        revision, including records whose visible ID did not change.
        """

        project = self._require_current_project()
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("Record rename requires a SequenceDataset.")
        previous_entry = self._require_current_revision(project, dataset.dataset_id)
        if operation not in {RevisionOperation.RECORD_RENAME, RevisionOperation.BATCH_RENAME}:
            raise ValueError("record rename requires RECORD_RENAME or BATCH_RENAME operation")
        requested = {str(source_id): str(target_id).strip() for source_id, target_id in rename_by_id.items()}
        unknown = sorted(set(requested) - set(dataset.sequence_ids))
        if unknown:
            raise ValueError("Unknown record IDs: " + ", ".join(unknown))
        if not requested:
            raise ValueError("At least one record rename is required.")
        records = tuple(
            SequenceRecord(
                sequence_id=requested.get(record.sequence_id, record.sequence_id),
                sequence=record.sequence,
                description=record.description,
                source_reference=record.source_reference,
                metadata=record.metadata,
                provenance=RecordProvenance((RecordRef(dataset.dataset_id, record.sequence_id),)),
            )
            for record in dataset.records
        )
        if any(not record.sequence_id for record in records):
            raise ValueError("Record rename would produce an empty record ID.")
        if len({record.sequence_id for record in records}) != len(records):
            raise ValueError("Record rename would produce duplicate record IDs.")
        suffix = "batch_renamed" if operation is RevisionOperation.BATCH_RENAME else "renamed"
        derived = SequenceDataset(
            dataset_id=_unique_dataset_id(project, f"{dataset.dataset_id}_{suffix}"),
            name=dataset.name,
            source_type=dataset.source_type,
            records=records,
            metadata={
                **dict(dataset.metadata),
                "source_dataset_id": dataset.dataset_id,
                "derived_from": operation.value,
                "record_id_renames": requested,
            },
        )
        updated = project.add_dataset_revision(
            dataset.dataset_id,
            derived,
            operation=operation,
            display_name=previous_entry.display_name,
            parent_dataset_id=previous_entry.parent_dataset_id,
            derivation_type=previous_entry.derivation_type,
            lineage_relations=previous_entry.lineage_relations,
            metadata={
                **dict(previous_entry.metadata),
                "added_by": "Studio Record Rename Revision",
                "derivation_detail": operation.value,
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._open_revision_viewer(derived)
        return derived

    def create_dataset_from_record_selection(
        self,
        dataset: SequenceDataset,
        selected_record_ids: tuple[str, ...],
        *,
        renamed_record_ids: dict[str, str] | None = None,
    ) -> SequenceDataset:
        """Register an immutable record-subset Dataset without touching its parent."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        if not isinstance(dataset, SequenceDataset) or not project.has_dataset(dataset.dataset_id):
            raise ValueError("Source SequenceDataset must be registered in the current Project.")
        selected = tuple(str(record_id) for record_id in selected_record_ids)
        if not selected:
            raise ValueError("Select at least one record.")
        selected_set = set(selected)
        source_records = tuple(record for record in dataset.records if record.sequence_id in selected_set)
        if len(source_records) != len(selected_set):
            missing = selected_set - {record.sequence_id for record in source_records}
            raise ValueError("Unknown selected record IDs: " + ", ".join(sorted(missing)))
        renamed_record_ids = dict(renamed_record_ids or {})
        records = tuple(
            SequenceRecord(
                sequence_id=renamed_record_ids.get(record.sequence_id, record.sequence_id),
                sequence=record.sequence,
                description=record.description,
                source_reference=record.source_reference,
                metadata=record.metadata,
                provenance=RecordProvenance(
                    (RecordRef(dataset.dataset_id, record.sequence_id),)
                ),
            )
            for record in source_records
        )
        ids = tuple(record.sequence_id for record in records)
        if len(set(ids)) != len(ids):
            raise ValueError("Rename would produce duplicate record IDs.")
        derived = SequenceDataset(
            dataset_id=_unique_dataset_id(project, f"{dataset.dataset_id}_selection"),
            name=f"{dataset.name} selection",
            source_type=dataset.source_type,
            records=records,
            metadata={
                **dict(dataset.metadata),
                "source_dataset_id": dataset.dataset_id,
                "derived_from": "RECORD_SELECTION",
                "selected_record_ids": tuple(record.sequence_id for record in records),
                "record_id_renames": renamed_record_ids,
            },
        )
        updated = project.add_dataset(
            derived,
            parent_dataset_id=dataset.dataset_id,
            derivation_type=DerivationType.SUBSET_FROM_DATASET,
            metadata={
                "added_by": "Dataset Viewer Selection",
                "derivation_detail": "RECORD_SELECTION",
            },
        )
        self._state.replace_project(updated, dirty=True)
        if (
            self._viewer_registry is not None
            and self._viewer_context is not None
            and self._tab_manager is not None
        ):
            viewer = self._viewer_registry.create_viewer_for(derived, self._viewer_context)
            self._tab_manager.open_viewer(viewer, resource_key=f"dataset:{derived.dataset_id}")
        return derived

    def create_dataset_from_project_record_refs(
        self,
        record_refs: tuple[RecordRef, ...] | list[RecordRef],
        *,
        name: str,
        dataset_id: str | None = None,
        metadata: dict[str, object] | None = None,
        output_record_ids: dict[RecordRef, str] | None = None,
    ) -> SequenceDataset:
        """Build and register a Dataset from ordered records across Project datasets.

        This is a controller API for the future Project Records UI; it performs
        no widget work and leaves the current selection/viewer unchanged.
        """

        project = self._require_current_project()
        resolved_dataset_id = _unique_dataset_id(
            project,
            dataset_id if dataset_id is not None else name,
        )
        if dataset_id is not None and resolved_dataset_id != dataset_id:
            raise ValueError(f"dataset_id already exists in project: {dataset_id}")
        build: CrossDatasetBuild = build_dataset_from_record_refs(
            project,
            record_refs,
            dataset_id=resolved_dataset_id,
            name=name,
            metadata=metadata,
            output_record_ids=output_record_ids,
        )
        updated = project.add_dataset(
            build.dataset,
            derivation_type=(
                DerivationType.SUBSET_FROM_DATASET
                if len(build.lineage_relations) == 1
                else None
            ),
            lineage_relations=build.lineage_relations,
            metadata={
                "added_by": "Cross-Dataset Record Builder",
                "derivation_detail": "CROSS_DATASET_RECORD_SELECTION",
                "source_dataset_count": len(build.lineage_relations),
            },
        )
        self._state.replace_project(updated, dirty=True)
        return build.dataset

    def open_sequence_file(self, filepath: str) -> str | None:
        """Import FASTA/FAS content and open the matching Studio dataset viewer."""

        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return None
        path = Path(filepath)
        imported = read_fasta_dataset(path)
        project = self._state.project
        if project is None:
            project = Project.create(
                project_id=_safe_identifier(path.stem) or "imported_sequences",
                name=f"Project: {path.stem or path.name}",
                metadata={"created_by": "SangerFlow-Studio", "source_file": str(path)},
            )

        if imported.source_type is SourceType.IMPORTED_ALIGNMENT:
            parent_dataset = _copy_sequence_dataset(
                imported,
                dataset_id=_unique_dataset_id(project, f"{imported.dataset_id}_source"),
                source_type=SourceType.IMPORTED_FASTA,
                name=f"{imported.name} source sequences",
                metadata={
                    **dict(imported.metadata),
                    "studio_import_role": "alignment_source",
                },
            )
            project = project.add_dataset(
                parent_dataset,
                derivation_type=DerivationType.IMPORTED,
                metadata={"added_by": "FASTA Import", "import_role": "alignment_source"},
            )
            alignment_dataset = AlignmentDataset.from_sequence_dataset(
                alignment_id=_unique_dataset_id(project, f"{imported.dataset_id}_alignment"),
                name=f"{imported.name} alignment",
                parent_dataset=parent_dataset,
                records=tuple(
                    AlignmentRecord(
                        record_id=record.sequence_id,
                        source_record_id=record.sequence_id,
                        aligned_sequence=record.sequence,
                        metadata=record.metadata,
                    )
                    for record in imported.records
                ),
                metadata={
                    **dict(imported.metadata),
                    "source": "Imported FASTA alignment",
                    "parent_dataset_id": parent_dataset.dataset_id,
                },
            )
            project = project.add_dataset(
                alignment_dataset,
                parent_dataset_id=parent_dataset.dataset_id,
                derivation_type=DerivationType.IMPORTED,
                metadata={"added_by": "FASTA Import", "import_role": "alignment"},
            )
            self._state.replace_project(project, dirty=True)
            viewer = self._viewer_registry.create_viewer_for(alignment_dataset, self._viewer_context)
            return self._tab_manager.open_viewer(
                viewer,
                resource_key=f"alignment:{alignment_dataset.alignment_id}",
            )

        dataset = _copy_sequence_dataset(
            imported,
            dataset_id=_unique_dataset_id(project, imported.dataset_id),
            source_type=imported.source_type,
        )
        project = project.add_dataset(
            dataset,
            derivation_type=DerivationType.IMPORTED,
            metadata={"added_by": "FASTA Import"},
        )
        self._state.replace_project(project, dirty=True)
        viewer = self._viewer_registry.create_viewer_for(dataset, self._viewer_context)
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"dataset:{dataset.dataset_id}",
        )

    def select_item(self, item: object | None, *, open_viewer: bool = True) -> None:
        self._state.set_selected_item(item)
        if open_viewer and isinstance(item, StudioSelection) and item.kind in {
            SelectionKind.DATASET,
            SelectionKind.ANALYSIS_RESULT,
        }:
            self.open_selected_item()

    def activate_tab(self, tab_name: str) -> None:
        self._state.set_active_tab(tab_name)

    def open_selected_item(self) -> str | None:
        selection = self._state.selected_item
        if not isinstance(selection, StudioSelection):
            return None
        if selection.kind == SelectionKind.ANALYSIS_RESULT:
            return self._open_selected_analysis_result(selection)
        if selection.kind != SelectionKind.DATASET:
            return None
        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return None

        entry = selection.payload
        dataset = getattr(entry, "dataset", None)
        if dataset is None:
            return None
        viewer = self._viewer_registry.create_viewer_for(dataset, self._viewer_context)
        if isinstance(dataset, AlignmentDataset):
            resource_key = f"alignment:{dataset.alignment_id}"
        else:
            resource_key = f"dataset:{_dataset_identifier(dataset)}"
        return self._tab_manager.open_viewer(viewer, resource_key=resource_key)

    def _open_selected_analysis_result(self, selection: StudioSelection) -> str | None:
        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return None
        entry = selection.payload
        analysis_result = getattr(entry, "analysis_result", None)
        repository = self._state.current_repository
        getter = getattr(repository, "get_for_analysis_result", None)
        if not callable(getter) or analysis_result is None:
            return None
        payload = getter(analysis_result)
        from widgets.viewers.identification_result_viewers import (
            BlastResultStudioViewer,
            BoldResultStudioViewer,
        )

        if isinstance(payload, BlastResultDataset):
            viewer = BlastResultStudioViewer(payload, context=self._viewer_context)
        elif isinstance(payload, BoldResultDataset):
            viewer = BoldResultStudioViewer(payload, context=self._viewer_context)
        else:
            return None
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"analysis-result:{analysis_result.result_id}",
        )

    def request_alignment_from_chromatogram_viewer(self, viewer: ChromatogramViewer) -> str | None:
        """Confirm reproducible MAFFT settings before creating an AlignmentDataset."""

        reads = tuple(read_view.read for read_view in viewer.visible_read_views)
        if not reads:
            viewer.status_message_changed.emit("At least one visible read is required for alignment.")
            return None
        source = getattr(viewer, "source_dataset", None)
        name = getattr(source, "name", None) or viewer.viewer_title
        dialog = AlignmentSettingsDialog(
            dataset_name=str(name), sequence_count=len(reads), parent=viewer,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        try:
            settings = dialog.settings()
        except ValueError as error:
            QMessageBox.warning(viewer, "Alignment Settings", str(error))
            return None
        return self.align_chromatogram_viewer(viewer, settings=settings)

    def align_chromatogram_viewer(
        self, viewer: ChromatogramViewer, *, settings: AlignmentSettings | None = None,
    ) -> str | None:
        """Create an AlignmentDataset from a ChromatogramViewer and open AlignmentViewer."""

        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return None
        reads = tuple(read_view.read for read_view in viewer.visible_read_views)
        if not reads:
            viewer.status_message_changed.emit("At least one visible read is required for alignment.")
            return None
        project = self._state.project
        source_dataset = getattr(viewer, "source_dataset", None)
        if source_dataset is None:
            source_dataset = _sequence_dataset_from_reads(
                reads,
                dataset_id=_unique_dataset_id(project, f"{_dataset_identifier(viewer)}_reads"),
                name=f"{viewer.viewer_title} reads",
                metadata={
                    "source": "Chromatogram Viewer",
                    "read_count": len(reads),
                    "creation_context": "SangerFlow-Studio chromatogram alignment",
                },
            )
        if project is None:
            project = Project.create(
                project_id="sangerflow_studio_project",
                name="SangerFlow Studio Project",
                metadata={"created_by": "SangerFlow-Studio"},
            )
        if not project.has_dataset(source_dataset.dataset_id):
            project = project.add_dataset(
                source_dataset,
                derivation_type=DerivationType.TRIMMED_FROM_READS,
                metadata={"added_by": "Chromatogram Viewer"},
            )

        resolved_settings = settings or AlignmentSettings(output_name=f"{source_dataset.name} alignment")
        try:
            mafft_executable = self._mafft_executable_resolver()
            alignment = align_reads(
                reads,
                strategy=resolved_settings.strategy,
                gap_opening_penalty=resolved_settings.gap_opening_penalty,
                offset=resolved_settings.offset,
                maxiterate=resolved_settings.maxiterate,
                adjust_direction=resolved_settings.adjust_direction,
                mafft_executable=mafft_executable,
            )
        except Exception as error:
            viewer.status_message_changed.emit(f"MAFFT alignment could not start: {error}")
            return None
        alignment_dataset_id = _unique_dataset_id(
            project,
            f"{source_dataset.dataset_id}_alignment",
        )
        alignment_dataset = _alignment_dataset_from_alignment(
            alignment,
            source_dataset,
            alignment_id=alignment_dataset_id,
            name=resolved_settings.output_name,
            metadata=resolved_settings.metadata(),
        )
        project = project.add_dataset(
            alignment_dataset,
            parent_dataset_id=source_dataset.dataset_id,
            derivation_type=DerivationType.ALIGNMENT_FROM_DATASET,
            metadata={"added_by": "Chromatogram Align"},
        )
        self._state.replace_project(project, dirty=True)
        if not resolved_settings.open_after_completion:
            return None
        alignment_viewer = self._viewer_registry.create_viewer_for(
            alignment_dataset,
            self._viewer_context,
        )
        return self._tab_manager.open_viewer(
            alignment_viewer,
            resource_key=f"alignment:{alignment_dataset.alignment_id}",
        )

    def run_consensus_workflow_from_chromatogram_viewer(
        self,
        viewer: ChromatogramViewer,
    ) -> str | None:
        """Open the Studio F/R Consensus Review Manager for visible reads."""

        if self._tab_manager is None:
            return None
        reads = tuple(read_view.read for read_view in viewer.visible_read_views)
        if not reads:
            viewer.status_message_changed.emit("At least one visible read is required for consensus.")
            return None
        dialog = ConsensusSettingsDialog(read_count=len(reads), parent=viewer)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings = dialog.settings()
        rows = build_consensus_sample_rows(reads, scoring=settings.scoring())
        ready_count = sum(1 for row in rows if row.is_ready)
        if ready_count == 0:
            viewer.status_message_changed.emit(
                "No clear Forward/Reverse pairs were found. Check filename suffixes such as _F and _R."
            )
        else:
            viewer.status_message_changed.emit(
                f"Consensus Review: {ready_count} clear Forward/Reverse pair(s) ready."
            )
        manager = ConsensusReviewManagerViewer(
            rows,
            context=self._viewer_context,
            source_dataset=getattr(viewer, "source_dataset", None),
            settings_metadata=settings.metadata(),
        )
        source_dataset = getattr(viewer, "source_dataset", None)
        source_id = getattr(source_dataset, "dataset_id", None) or viewer.viewer_id
        return self._tab_manager.open_viewer(
            manager,
            resource_key=f"fr-consensus-manager:{source_id}",
        )

    def open_single_fr_consensus_review(
        self,
        row: ConsensusSampleRow,
        *,
        source_dataset: object | None = None,
        settings_metadata: dict[str, object] | None = None,
    ) -> str | None:
        """Open one ready F/R pair in the Studio Single Consensus Review viewer."""

        if self._tab_manager is None:
            return None
        viewer = SingleConsensusReviewViewer(
            row,
            context=self._viewer_context,
            source_dataset=source_dataset,
            settings_metadata=settings_metadata,
        )
        viewer.open_related_requested.connect(self._handle_consensus_related_request)
        source_id = getattr(source_dataset, "dataset_id", None) or "reads"
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"single-fr-consensus:{source_id}:{row.sample_id}",
        )

    def open_multiple_fr_consensus_review(
        self,
        rows: tuple[ConsensusSampleRow, ...],
        *,
        source_dataset: object | None = None,
    ) -> str | None:
        """Open all ready F/R pairs in the Studio Multiple Consensus Review viewer."""

        if self._tab_manager is None:
            return None
        viewer = MultipleConsensusReviewViewer(
            rows,
            context=self._viewer_context,
            source_dataset=source_dataset,
        )
        source_id = getattr(source_dataset, "dataset_id", None) or "reads"
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"multiple-fr-consensus:{source_id}",
        )

    def register_fr_reviewed_consensus_from_viewer(
        self,
        viewer: SingleConsensusReviewViewer,
    ) -> SequenceDataset:
        """Create and register a reviewed consensus from the F/R review viewer."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        source_dataset = getattr(viewer, "source_dataset", None)
        if not isinstance(source_dataset, SequenceDataset):
            raise ValueError("F/R Consensus Review requires a source SequenceDataset.")
        if not project.has_dataset(source_dataset.dataset_id):
            raise ValueError(
                "Source SequenceDataset must be registered in the current Project before review."
            )
        reviewed_consensus = viewer.create_reviewed_consensus()
        dataset_id = _unique_dataset_id(
            project,
            f"{source_dataset.dataset_id}_{reviewed_consensus.sample_id}_reviewed_consensus",
        )
        dataset = create_dataset_from_reviewed_consensus(
            reviewed_consensus,
            dataset_id=dataset_id,
            name=f"Reviewed Consensus: {reviewed_consensus.sample_id}",
            metadata={
                "parent_dataset_id": source_dataset.dataset_id,
                "consensus_method": "consensus-v2.1 + human_review",
                "original_read_count": 2,
                "source_sample_id": reviewed_consensus.sample_id,
                "workflow": "F/R Consensus Review",
                "consensus_settings": getattr(viewer, "settings_metadata", {}),
                "original_consensus": reviewed_consensus.original_sequence,
                "reviewed_consensus": reviewed_consensus.reviewed_sequence,
                "review_decisions": _review_decisions_metadata(reviewed_consensus),
            },
        )
        updated = add_reviewed_consensus_dataset_to_project(
            project,
            dataset,
            parent_dataset_id=source_dataset.dataset_id,
            display_name="Reviewed Consensus",
            metadata={
                "added_by": "Studio F/R Consensus Review",
                "sample_id": reviewed_consensus.sample_id,
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        return dataset

    def register_multiple_fr_reviewed_consensus_from_viewer(
        self,
        viewer: MultipleConsensusReviewViewer,
    ) -> SequenceDataset:
        """Create and register a multi-sample reviewed consensus dataset."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        source_dataset = getattr(viewer, "source_dataset", None)
        if not isinstance(source_dataset, SequenceDataset):
            raise ValueError("Multiple Consensus Review requires a source SequenceDataset.")
        if not project.has_dataset(source_dataset.dataset_id):
            raise ValueError(
                "Source SequenceDataset must be registered in the current Project before review."
            )
        dataset_id = _unique_dataset_id(
            project,
            f"{source_dataset.dataset_id}_reviewed_consensus",
        )
        dataset = viewer.create_reviewed_consensus_dataset(
            dataset_id=dataset_id,
            name=f"{source_dataset.name} reviewed consensus",
            metadata={
                "parent_dataset_id": source_dataset.dataset_id,
                "workflow": "F/R Multiple Consensus Review",
            },
        )
        updated = add_reviewed_consensus_dataset_to_project(
            project,
            dataset,
            parent_dataset_id=source_dataset.dataset_id,
            display_name="Reviewed Consensus",
            metadata={
                "added_by": "Studio F/R Multiple Consensus Review",
                "sample_count": len(viewer.rows),
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        return dataset

    def align_multiple_consensus_review(
        self,
        viewer: MultipleConsensusReviewViewer,
        *,
        runner: object | None = None,
    ) -> SequenceDataset:
        """Run existing MAFFT for a viewer-session-only consensus alignment.

        This deliberately does not call ``Project.add_dataset``.  A temporary
        alignment is review state rather than a new research result until an
        explicit save workflow is designed with a consensus parent dataset.
        """

        if not isinstance(viewer, MultipleConsensusReviewViewer):
            raise ValueError("viewer must be a MultipleConsensusReviewViewer")
        sequences = viewer.alignment_input_sequences()
        source_dataset = SequenceDataset(
            dataset_id="temporary_multiple_consensus",
            name="Temporary Multiple Consensus Alignment",
            source_type=SourceType.REVIEWED_CONSENSUS,
            records=tuple(
                SequenceRecord(sequence_id=sample_id, sequence=sequence)
                for sample_id, sequence in sequences.items()
            ),
            metadata={"temporary": True, "workflow": "Multiple Consensus Review"},
        )
        aligned = align_sequence_dataset(
            source_dataset,
            dataset_id="temporary_multiple_consensus_mafft",
            name="Temporary Multiple Consensus MAFFT Alignment",
            runner=runner,
        )
        viewer.set_temporary_alignment(aligned)
        return aligned

    def register_edited_alignment_from_viewer(self, viewer: object) -> AlignmentDataset:
        """Register an AlignmentViewer save as the next immutable alignment revision."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        alignment_dataset = getattr(viewer, "dataset", None)
        if not isinstance(alignment_dataset, AlignmentDataset):
            raise ValueError("Alignment editing requires an AlignmentDataset.")
        previous_entry = self._require_current_revision(project, alignment_dataset.alignment_id)
        dataset_id = _unique_dataset_id(
            project,
            f"{alignment_dataset.alignment_id}_edited",
        )
        create = getattr(viewer, "create_edited_alignment_dataset", None)
        if not callable(create):
            raise ValueError("viewer cannot create an edited AlignmentDataset.")
        edited_dataset = create(
            alignment_id=dataset_id,
            name=alignment_dataset.name,
            metadata={"parent_alignment_id": alignment_dataset.alignment_id},
        )
        updated = project.add_dataset_revision(
            alignment_dataset.alignment_id,
            edited_dataset,
            operation=RevisionOperation.ALIGNMENT_EDIT,
            display_name=previous_entry.display_name,
            parent_dataset_id=previous_entry.parent_dataset_id,
            derivation_type=previous_entry.derivation_type,
            lineage_relations=previous_entry.lineage_relations,
            metadata={
                **dict(previous_entry.metadata),
                "added_by": "Studio Alignment Editor Revision",
                "derivation_detail": "EDITED_ALIGNMENT",
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        self._open_revision_viewer(edited_dataset)
        return edited_dataset

    def register_edited_sequence_dataset_from_viewer(self, viewer: object) -> SequenceDataset:
        """Save a Sequence Editor session as the next immutable Dataset revision."""

        project = self._require_current_project()
        dataset = getattr(viewer, "dataset", None)
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("Sequence editing requires a SequenceDataset.")
        previous_entry = self._require_current_revision(project, dataset.dataset_id)
        create = getattr(viewer, "create_edited_sequence_dataset", None)
        if not callable(create):
            raise ValueError("viewer cannot create an edited SequenceDataset.")
        edited = create(
            dataset_id=_unique_dataset_id(project, f"{dataset.dataset_id}_edited"),
            name=dataset.name,
            metadata={"parent_sequence_dataset_id": dataset.dataset_id},
        )
        updated = project.add_dataset_revision(
            dataset.dataset_id,
            edited,
            operation=RevisionOperation.SEQUENCE_EDIT,
            display_name=previous_entry.display_name,
            parent_dataset_id=previous_entry.parent_dataset_id,
            derivation_type=previous_entry.derivation_type,
            lineage_relations=previous_entry.lineage_relations,
            metadata={
                **dict(previous_entry.metadata),
                "added_by": "Studio Sequence Editor Revision",
                "derivation_detail": "SEQUENCE_EDIT",
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        self._open_revision_viewer(edited)
        return edited

    def align_sequence_dataset_from_editor(self, viewer: object) -> str | None:
        """Create a new logical AlignmentDataset from a saved unaligned revision."""

        dataset = getattr(viewer, "dataset", None)
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("Align requires a SequenceDataset.")
        if bool(getattr(viewer, "is_dirty", False)):
            raise ValueError("Save or discard pending sequence edits before alignment.")
        if self._viewer_registry is None or self._viewer_context is None or self._tab_manager is None:
            return None
        project = self._require_current_project()
        self._require_current_revision(project, dataset.dataset_id)
        dialog = AlignmentSettingsDialog(dataset_name=dataset.name, sequence_count=dataset.sequence_count, parent=viewer)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings = dialog.settings()
        alignment_input = dataset
        if dataset.has_gaps:
            answer = QMessageBox.question(
                viewer,
                "Align Sequences",
                "This unaligned Dataset contains '-' symbols. MAFFT requires "
                "gap-free input. Remove only those existing gap symbols from "
                "the temporary MAFFT input?\n\n"
                "The current Dataset revision will not be changed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return None
            alignment_input = _gapless_mafft_input(dataset)
        try:
            aligned_sequences = align_sequence_dataset(
                alignment_input,
                dataset_id=_unique_dataset_id(project, f"{dataset.dataset_id}_mafft"),
                name=settings.output_name,
                mafft_executable=self._mafft_executable_resolver(),
            )
        except Exception as error:
            raise ValueError(f"MAFFT alignment could not start: {error}") from error
        alignment = AlignmentDataset.from_sequence_dataset(
            alignment_id=_unique_dataset_id(project, f"{dataset.dataset_id}_alignment"),
            name=settings.output_name,
            parent_dataset=dataset,
            records=tuple(
                AlignmentRecord(
                    record_id=record.sequence_id,
                    source_record_id=record.sequence_id,
                    aligned_sequence=record.sequence,
                    metadata=record.metadata,
                )
                for record in aligned_sequences.records
            ),
            metadata={
                **dict(aligned_sequences.metadata),
                "alignment_method": "MAFFT",
                "software": "MAFFT",
                "mafft_input_gap_handling": "removed_existing_gap_symbols" if dataset.has_gaps else "none",
                **settings.metadata(),
            },
        )
        updated = project.add_dataset(
            alignment,
            parent_dataset_id=dataset.dataset_id,
            derivation_type=DerivationType.ALIGNMENT_FROM_DATASET,
            metadata={"added_by": "Studio Sequence Editor Align"},
        )
        self._state.replace_project(updated, dirty=True)
        result_viewer = self._viewer_registry.create_viewer_for(alignment, self._viewer_context)
        return self._tab_manager.open_viewer(result_viewer, resource_key=f"alignment:{alignment.alignment_id}")

    def open_source_chromatogram_for_sequence_editor(self, viewer: object, record_id: str, column: int) -> bool:
        """Open source evidence for a Sequence Editor record.

        Ordinary AB1-derived records open Main Chromatogram Viewer.  A reviewed
        F/R consensus has no single raw read; its persisted parent Dataset ID
        and sample ID instead resolve the original pair and reopen the existing
        Single Consensus Review evidence view.  This relies only on the
        persisted lineage metadata and the normal AB1 reattachment path.
        """

        dataset = getattr(viewer, "dataset", None)
        if not isinstance(dataset, SequenceDataset) or self._tab_manager is None:
            return False
        try:
            record = dataset.get_record(record_id)
        except KeyError:
            return False
        source = record.source_reference
        if not isinstance(source, SangerRead):
            opened = self._open_reviewed_consensus_source_evidence(
                dataset, record, column
            )
            if not opened:
                status_signal = getattr(viewer, "status_message_changed", None)
                emit = getattr(status_signal, "emit", None)
                if callable(emit):
                    emit(
                        "Forward/Reverse source evidence is unavailable. "
                        "Check that the original AB1 source files are accessible."
                    )
            return opened
        chromatogram = ChromatogramViewer(
            (source,), title=f"Chromatogram: {record_id}", source_object_id=dataset.dataset_id,
            context=self._viewer_context, source_dataset=dataset,
        )
        tab_id = self._tab_manager.open_viewer(chromatogram, resource_key=f"chromatogram:{dataset.dataset_id}:{record_id}")
        positions = tuple(getattr(source, "base_positions", ()) or ())
        if 0 <= column < len(positions):
            chromatogram.jump_to_trace_position(record_id, int(positions[column]))
        return bool(tab_id)

    def _open_reviewed_consensus_source_evidence(
        self,
        dataset: SequenceDataset,
        record: SequenceRecord,
        column: int,
    ) -> bool:
        """Resolve reviewed-consensus evidence through its persisted parent.

        ``SequenceRecord.source_reference`` is deliberately transient and is
        not serialized in a Project bundle.  The reviewed Dataset already
        stores its original source Dataset and sample identity in metadata, so
        reconstructing the normal F/R review view after reload needs no schema
        change and never invents trace evidence.
        """

        project = self._state.current_project
        if not isinstance(project, Project) or self._tab_manager is None:
            return False
        parent_dataset_id = str(
            dataset.metadata.get("parent_dataset_id", "")
            or dataset.metadata.get("source_dataset_id", "")
        ).strip()
        sample_id = str(
            record.metadata.get("source_sample_id", "")
            or record.metadata.get("sample_id", "")
            or dataset.metadata.get("source_sample_id", "")
        ).strip()
        if not parent_dataset_id or not sample_id or not project.has_dataset(parent_dataset_id):
            return False
        parent_dataset = project.get_dataset(parent_dataset_id)
        if not isinstance(parent_dataset, SequenceDataset):
            return False
        reads = tuple(reads_from_dataset(parent_dataset))
        if not reads:
            return False
        rows = build_consensus_sample_rows(reads)
        row = next(
            (candidate for candidate in rows if candidate.sample_id == sample_id and candidate.is_ready),
            None,
        )
        if row is None:
            return False
        settings_metadata = dataset.metadata.get("consensus_settings", {})
        if not isinstance(settings_metadata, dict):
            settings_metadata = {}
        tab_id = self.open_single_fr_consensus_review(
            row,
            source_dataset=parent_dataset,
            settings_metadata=settings_metadata,
        )
        if not tab_id:
            return False
        source_key = f"single-fr-consensus:{parent_dataset.dataset_id}:{row.sample_id}"
        review_viewer = self._tab_manager.viewer_for_resource_key(source_key)
        select_position = getattr(review_viewer, "select_position", None)
        if callable(select_position) and 0 <= column < len(record.sequence):
            select_position(column)
        return True

    def run_blast_for_dataset(
        self, dataset: object, *, included_record_ids: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> BlastResultDataset:
        """Run BLAST for a Project dataset, register the result, and open its viewer."""

        project = self._require_project()
        query_dataset, parent_dataset_id = self._identification_query_dataset(dataset)
        query_dataset = self._blast_query_subset(query_dataset, included_record_ids)
        if not project.has_dataset(parent_dataset_id):
            raise ValueError("BLAST input dataset must be registered in the current Project.")
        result = run_blast_workflow(
            query_dataset,
            analysis_mode=BlastAnalysisMode.IDENTIFICATION,
            database="nt",
            runner=self._blast_runner,
        )
        result = self._reparent_blast_result(
            result,
            parent_dataset_id=parent_dataset_id,
            query_dataset=query_dataset,
            source_dataset=dataset,
        )
        updated = add_blast_result_to_project(project, result)
        self._store_result_and_open(updated, result)
        return result

    def import_ncbi_blast_xml_for_dataset(
        self,
        dataset: object,
        filepath: str | Path,
        *,
        included_record_ids: set[str] | frozenset[str] | tuple[str, ...] | None = None,
    ) -> tuple[BlastResultDataset, BlastXmlImportPreview]:
        """Register an exact-query matched offline NCBI Web BLAST XML import."""

        project = self._require_project()
        query_dataset, parent_dataset_id = self._identification_query_dataset(dataset)
        query_dataset = self._blast_query_subset(query_dataset, included_record_ids)
        if not project.has_dataset(parent_dataset_id):
            raise ValueError("BLAST XML input dataset must be registered in the current Project.")
        result_id = _unique_result_id(project, f"{parent_dataset_id}_ncbi_web_xml")
        result, preview = import_ncbi_blast_xml(
            filepath, query_dataset, result_id=result_id,
        )
        result = self._reparent_blast_result(
            result,
            parent_dataset_id=parent_dataset_id,
            query_dataset=query_dataset,
            source_dataset=dataset,
        )
        updated = add_blast_result_to_project(
            project, result, metadata={"added_by": "NCBI Web BLAST XML Import"},
        )
        self._store_result_and_open(updated, result)
        return result, preview

    def apply_blast_result_metadata(
        self,
        result: BlastResultDataset,
        settings: BlastMetadataSettings,
        *,
        selected_query_ids: tuple[str, ...] | list[str] | set[str] | frozenset[str] | None = None,
    ) -> SequenceDataset:
        """Copy selected, stable-query BLAST evidence into a metadata revision."""

        if not isinstance(result, BlastResultDataset):
            raise ValueError("BLAST metadata requires a BlastResultDataset.")
        if not isinstance(settings, BlastMetadataSettings):
            raise ValueError("BLAST metadata settings are invalid.")
        project = self._require_current_project()
        dataset = project.get_dataset(result.parent_dataset_id)
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("BLAST metadata can only be applied to a SequenceDataset.")
        previous_entry = self._require_current_revision(project, dataset.dataset_id)
        result_query_ids = result.query_ids()
        if selected_query_ids is None:
            selected_ids = result_query_ids
        else:
            selected_ids = tuple(str(query_id) for query_id in selected_query_ids)
            if not selected_ids:
                raise ValueError("Select at least one BLAST query before applying metadata.")
            if len(set(selected_ids)) != len(selected_ids):
                raise ValueError("Selected BLAST query IDs must not contain duplicates.")
            unknown = tuple(query_id for query_id in selected_ids if query_id not in result_query_ids)
            if unknown:
                raise ValueError("Selected BLAST queries are not present in this result: " + ", ".join(unknown))
        dataset_ids = set(dataset.sequence_ids)
        missing_records = tuple(query_id for query_id in selected_ids if query_id not in dataset_ids)
        if missing_records:
            raise ValueError(
                "Selected BLAST queries do not match records in the current Dataset: "
                + ", ".join(missing_records)
            )
        selected_set = set(selected_ids)
        records: list[SequenceRecord] = []
        for record in dataset.records:
            hits = result.get_hits(record.sequence_id)
            metadata = dict(record.metadata)
            if record.sequence_id in selected_set and hits:
                hit = hits[0]
                passes = hit.identity >= settings.minimum_identity and hit.query_coverage >= settings.minimum_coverage
                blast_fields = {
                    # Description is the original NCBI hit text.  It remains
                    # separate from the conservatively extracted taxonomy.
                    "blast_best_hit": hit.description or hit.organism,
                    "blast_scientific_name": (
                        hit.scientific_name
                        if (passes or settings.mark_uncertain) and hit.scientific_name != "Unknown"
                        else ""
                    ),
                    "blast_accession": hit.hit_accession,
                    "blast_identity": hit.identity,
                    "blast_query_coverage": hit.query_coverage,
                    "blast_evalue": hit.evalue,
                }
                metadata.update({
                    key: value for key, value in blast_fields.items() if key in settings.fields
                })
                # These control fields preserve the evidence source and its
                # threshold outcome even when the user elects not to expose a
                # particular display field in this metadata revision.
                metadata.update({
                    "blast_identification_status": "accepted" if passes else "uncertain",
                    "blast_result_id": result.result_id,
                })
            records.append(SequenceRecord(
                sequence_id=record.sequence_id, sequence=record.sequence,
                description=record.description, source_reference=record.source_reference,
                metadata=metadata,
                provenance=RecordProvenance((RecordRef(dataset.dataset_id, record.sequence_id),)),
            ))
        derived = SequenceDataset(
            dataset_id=_unique_dataset_id(project, f"{dataset.dataset_id}_blast_metadata"),
            name=dataset.name, source_type=dataset.source_type, records=tuple(records),
            metadata={
                **dict(dataset.metadata), "source_dataset_id": dataset.dataset_id,
                "derived_from": "BLAST_METADATA_MERGE", "blast_result_id": result.result_id,
                "blast_metadata_thresholds": {
                    "minimum_identity": settings.minimum_identity,
                    "minimum_coverage": settings.minimum_coverage,
                    "mark_uncertain": settings.mark_uncertain,
                    "fields": tuple(sorted(settings.fields)),
                },
                "blast_metadata_selected_query_ids": selected_ids,
            },
        )
        updated = project.add_dataset_revision(
            dataset.dataset_id, derived, operation=RevisionOperation.METADATA_MERGE,
            display_name=previous_entry.display_name,
            parent_dataset_id=previous_entry.parent_dataset_id,
            derivation_type=previous_entry.derivation_type,
            lineage_relations=previous_entry.lineage_relations,
            metadata={
                **dict(previous_entry.metadata), "added_by": "BLAST Metadata Revision",
                "derivation_detail": "BLAST_METADATA_MERGE", "blast_result_id": result.result_id,
                "selected_query_count": len(selected_ids),
            },
        )
        self._state.replace_project(updated, dirty=True)
        self._open_revision_viewer(derived)
        return derived

    def run_blast_for_dataset_interactive(
        self,
        dataset: object,
        *,
        included_record_ids: set[str] | frozenset[str] | tuple[str, ...] | None = None,
        parent_widget: object | None = None,
    ) -> None:
        """Open settings/progress UI and run real BLAST without blocking Qt."""

        assert_main_gui_thread("ProjectController.run_blast_for_dataset_interactive")
        project = self._require_project()
        query_dataset, parent_dataset_id = self._identification_query_dataset(dataset)
        if not project.has_dataset(parent_dataset_id):
            QMessageBox.warning(parent_widget, "Run BLAST", "BLAST input dataset is not registered in the current Project.")
            return
        available_ids = {record.sequence_id for record in query_dataset.records}
        selected_ids = set(included_record_ids or available_ids)
        selected_ids.intersection_update(available_ids)
        if not selected_ids:
            QMessageBox.warning(parent_widget, "BLAST", "Select at least one included record before running BLAST.")
            return
        if self._blast_runner is not None:
            try:
                self.run_blast_for_dataset(dataset, included_record_ids=selected_ids)
            except Exception as error:
                QMessageBox.critical(parent_widget, "BLAST failed", str(error))
            return

        settings_dialog = BlastSettingsDialog(
            query_count=query_dataset.sequence_count,
            included_query_count=len(selected_ids),
            parent=parent_widget,
        )
        if settings_dialog.exec() != QDialog.DialogCode.Accepted:
            return
        query_ids = available_ids if settings_dialog.query_scope == "all" else selected_ids
        selected_query_dataset = self._blast_query_subset(query_dataset, query_ids)
        if settings_dialog.launch_mode == "website":
            website_dialog = BlastWebsiteDialog(
                selected_query_dataset,
                on_import_xml=lambda filepath: self.import_ncbi_blast_xml_for_dataset(
                    dataset, filepath, included_record_ids=query_ids,
                ),
                parent=parent_widget,
            )
            website_dialog.exec()
            return
        try:
            settings = settings_dialog.settings()
        except Exception as error:
            QMessageBox.warning(parent_widget, "Invalid BLAST settings", str(error))
            return

        progress_dialog = IdentificationProgressDialog(title="NCBI BLAST", parent=parent_widget)
        self._start_async_blast_worker(
            selected_query_dataset,
            settings,
            source_dataset=dataset,
            parent_dataset_id=parent_dataset_id,
            progress_dialog=progress_dialog,
        )

    def _start_async_blast_worker(
        self,
        query_dataset: SequenceDataset,
        settings: object,
        *,
        source_dataset: object,
        parent_dataset_id: str,
        progress_dialog: IdentificationProgressDialog,
    ) -> tuple[QThread, BlastWorker]:
        """Start data-only BLAST work and queue every UI update to this controller."""

        assert_main_gui_thread("ProjectController._start_async_blast_worker")
        worker = BlastWorker(query_dataset, settings)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        # requestInterruption is thread-safe.  A queued call to a busy worker
        # would not be processed until the network operation had already ended.
        progress_dialog._cancel_button.clicked.connect(thread.requestInterruption)
        receiver = _AsyncBlastGuiReceiver(
            self,
            source_dataset=source_dataset,
            query_dataset=query_dataset,
            parent_dataset_id=parent_dataset_id,
            progress_dialog=progress_dialog,
            thread=thread,
            worker=worker,
        )
        worker.progress.connect(receiver.update_progress, Qt.ConnectionType.QueuedConnection)
        worker.completed.connect(receiver.complete, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(receiver.fail, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(receiver.cleanup, Qt.ConnectionType.QueuedConnection)
        self._identification_threads.append((thread, worker, progress_dialog, receiver))
        progress_dialog.show()
        thread.start()
        return thread, worker

    @staticmethod
    def _blast_query_subset(
        query_dataset: SequenceDataset,
        included_record_ids: set[str] | frozenset[str] | tuple[str, ...] | None,
    ) -> SequenceDataset:
        """Create an ordered, exact-ID query view without mutating its source Dataset."""

        if included_record_ids is None:
            return query_dataset
        selected = set(included_record_ids)
        records = tuple(record for record in query_dataset.records if record.sequence_id in selected)
        if not records:
            raise ValueError("BLAST requires at least one included record.")
        if len(records) == len(query_dataset.records):
            return query_dataset
        return SequenceDataset(
            dataset_id=f"{query_dataset.dataset_id}_blast_selection",
            name=f"{query_dataset.name} (BLAST selection)",
            source_type=query_dataset.source_type,
            records=records,
            metadata={
                **dict(query_dataset.metadata),
                "derived_from": "BLAST_QUERY_SELECTION",
                "selected_record_ids": tuple(record.sequence_id for record in records),
                "source_dataset_id": query_dataset.dataset_id,
            },
        )

    @staticmethod
    def _reparent_blast_result(
        result: BlastResultDataset,
        *,
        parent_dataset_id: str,
        query_dataset: SequenceDataset,
        source_dataset: object,
    ) -> BlastResultDataset:
        """Keep a temporary selected query view out of immutable Project lineage."""

        if result.parent_dataset_id == parent_dataset_id:
            return result
        return BlastResultDataset(
            result_id=result.result_id,
            name=result.name,
            hits=result.hits,
            parent_dataset_id=parent_dataset_id,
            metadata={
                **dict(result.metadata),
                "query_dataset_id": query_dataset.dataset_id,
                "parent_dataset_id": parent_dataset_id,
                "selected_record_ids": query_dataset.sequence_ids,
                "alignment_query_ungapped": isinstance(source_dataset, AlignmentDataset),
            },
            analysis_mode=result.analysis_mode,
            marker=result.marker,
            database=result.database,
        )

    def run_bold_for_dataset(self, dataset: object) -> BoldResultDataset:
        """Run BOLD for a Project dataset, register the result, and open its viewer."""

        project = self._require_project()
        query_dataset, parent_dataset_id = self._identification_query_dataset(dataset)
        if not project.has_dataset(parent_dataset_id):
            raise ValueError("BOLD input dataset must be registered in the current Project.")
        result = run_bold_workflow(
            query_dataset,
            database="BOLD",
            runner=self._bold_runner,
        )
        if result.parent_dataset_id != parent_dataset_id:
            result = BoldResultDataset(
                result_id=result.result_id,
                name=result.name,
                parent_dataset_id=parent_dataset_id,
                marker=result.marker,
                database=result.database,
                hits=result.hits,
                metadata={
                    **dict(result.metadata),
                    "query_dataset_id": query_dataset.dataset_id,
                    "parent_dataset_id": parent_dataset_id,
                    "alignment_query_ungapped": isinstance(dataset, AlignmentDataset),
                },
            )
        updated = add_bold_result_to_project(project, result)
        self._store_result_and_open(updated, result)
        return result

    def run_bold_for_dataset_interactive(self, dataset: object, *, parent_widget: object | None = None) -> None:
        """Run configured BOLD runner or explain why real BOLD is unavailable."""

        if self._bold_runner is None:
            try:
                BoldIdentificationRunner()("")
            except BoldIdentificationUnavailableError as error:
                QMessageBox.information(parent_widget, "BOLD Identification", str(error))
            return
        try:
            self.run_bold_for_dataset(dataset)
        except Exception as error:
            QMessageBox.critical(parent_widget, "BOLD failed", str(error))

    def _complete_async_blast(
        self,
        result: BlastResultDataset,
        *,
        source_dataset: object,
        query_dataset: SequenceDataset,
        parent_dataset_id: str,
        progress_dialog: IdentificationProgressDialog,
    ) -> None:
        assert_main_gui_thread("ProjectController._complete_async_blast")
        result = self._reparent_blast_result(
            result,
            parent_dataset_id=parent_dataset_id,
            query_dataset=query_dataset,
            source_dataset=source_dataset,
        )
        try:
            updated = add_blast_result_to_project(self._require_project(), result)
            self._store_result_and_open(updated, result)
            progress_dialog.close()
        except Exception as error:
            QMessageBox.critical(progress_dialog, "Could not register BLAST result", str(error))

    def _fail_async_blast(self, message: str, progress_dialog: IdentificationProgressDialog) -> None:
        assert_main_gui_thread("ProjectController._fail_async_blast")
        QMessageBox.critical(progress_dialog, "NCBI BLAST failed", message)
        progress_dialog.close()

    def _forget_identification_thread(
        self,
        thread: QThread,
        worker: object,
        dialog: object,
        *,
        receiver: object | None = None,
    ) -> None:
        self._identification_threads = [
            item
            for item in self._identification_threads
            if item[:3] != (thread, worker, dialog)
        ]

    def create_dataset_from_blast_result_selection(
        self,
        viewer: object,
        selection: BlastResultSelection,
        *,
        name: str,
    ) -> SequenceDataset:
        """Create and register a SequenceDataset from a BLAST viewer selection."""

        result = getattr(viewer, "result", None)
        if not isinstance(result, BlastResultDataset):
            raise ValueError("viewer must expose a BlastResultDataset")
        source_dataset = self._source_dataset_for_result(result)
        dataset_id = _unique_dataset_id(
            self._state.current_project,
            _safe_identifier(name) or f"{result.parent_dataset_id}_blast_selection",
        )
        metadata = _selection_dataset_metadata(
            parent_dataset_id=result.parent_dataset_id,
            derivation_type="BLAST_SELECTION",
            source_analysis="BLAST",
            result_id=result.result_id,
            selection=selection,
        )
        dataset = create_dataset_from_blast_selection(
            source_dataset,
            selection,
            dataset_id=dataset_id,
            name=name,
            metadata=metadata,
        )
        updated = self._state.current_project.add_dataset(
            dataset,
            parent_dataset_id=result.parent_dataset_id,
            derivation_type=DerivationType.SUBSET_FROM_DATASET,
            lineage_relations=(
                LineageRelation(
                    LineageSourceKind.DATASET,
                    result.parent_dataset_id,
                    LineageRelationType.SUBSET_FROM_DATASET,
                ),
                LineageRelation(
                    LineageSourceKind.ANALYSIS_RESULT,
                    result.result_id,
                    LineageRelationType.SELECTED_FROM_BLAST,
                ),
            ),
            metadata={
                "created_by": "BLAST Selection",
                "derivation_detail": "BLAST_SELECTION",
                "blast_result_id": result.result_id,
            },
        )
        self._state.replace_project(updated, dirty=True)
        return dataset

    def create_dataset_from_bold_result_selection(
        self,
        viewer: object,
        selection: BoldResultSelection,
        *,
        name: str,
    ) -> SequenceDataset:
        """Create and register a SequenceDataset from a BOLD viewer selection."""

        result = getattr(viewer, "result", None)
        if not isinstance(result, BoldResultDataset):
            raise ValueError("viewer must expose a BoldResultDataset")
        source_dataset = self._source_dataset_for_result(result)
        dataset_id = _unique_dataset_id(
            self._state.current_project,
            _safe_identifier(name) or f"{result.parent_dataset_id}_bold_selection",
        )
        metadata = _selection_dataset_metadata(
            parent_dataset_id=result.parent_dataset_id,
            derivation_type="BOLD_SELECTION",
            source_analysis="BOLD",
            result_id=result.result_id,
            selection=selection,
        )
        dataset = create_dataset_from_bold_selection(
            source_dataset,
            selection,
            dataset_id=dataset_id,
            name=name,
            metadata=metadata,
        )
        updated = self._state.current_project.add_dataset(
            dataset,
            parent_dataset_id=result.parent_dataset_id,
            derivation_type=DerivationType.SUBSET_FROM_DATASET,
            lineage_relations=(
                LineageRelation(
                    LineageSourceKind.DATASET,
                    result.parent_dataset_id,
                    LineageRelationType.SUBSET_FROM_DATASET,
                ),
                LineageRelation(
                    LineageSourceKind.ANALYSIS_RESULT,
                    result.result_id,
                    LineageRelationType.SELECTED_FROM_BOLD,
                ),
            ),
            metadata={
                "created_by": "BOLD Selection",
                "derivation_detail": "BOLD_SELECTION",
                "bold_result_id": result.result_id,
            },
        )
        self._state.replace_project(updated, dirty=True)
        return dataset

    def _store_result_and_open(self, project: Project, result: object) -> None:
        repository = self._ensure_result_repository()
        repository.register_result(result)
        self._state.replace_project(project, dirty=True)
        if self._tab_manager is None or self._viewer_context is None:
            return
        from widgets.viewers.identification_result_viewers import (
            BlastResultStudioViewer,
            BoldResultStudioViewer,
        )

        if isinstance(result, BlastResultDataset):
            viewer = BlastResultStudioViewer(result, context=self._viewer_context)
        elif isinstance(result, BoldResultDataset):
            viewer = BoldResultStudioViewer(result, context=self._viewer_context)
        else:
            return
        self._tab_manager.open_viewer(
            viewer,
            resource_key=f"analysis-result:{result.result_id}",
        )

    def _require_project(self) -> Project:
        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        return project

    def _ensure_result_repository(self) -> FilesystemResultRepository:
        repository = self._state.current_repository
        if isinstance(repository, FilesystemResultRepository):
            return repository
        if self._temporary_repository_directory is None:
            self._temporary_repository_directory = TemporaryDirectory(prefix="sangerflow-studio-results-")
        repository = FilesystemResultRepository(self._temporary_repository_directory.name)
        self._state.set_repository(repository)
        return repository

    def _identification_query_dataset(self, dataset: object) -> tuple[SequenceDataset, str]:
        if isinstance(dataset, SequenceDataset):
            return dataset, dataset.dataset_id
        if isinstance(dataset, AlignmentDataset):
            records = tuple(
                SequenceRecord(
                    sequence_id=record.record_id,
                    sequence=record.aligned_sequence.replace("-", ""),
                    source_reference=record,
                    metadata={
                        **dict(record.metadata),
                        "source_record_id": record.source_record_id,
                        "aligned_sequence": record.aligned_sequence,
                        "ungapped_for_identification": True,
                    },
                )
                for record in dataset.records
            )
            return (
                SequenceDataset(
                    dataset_id=dataset.alignment_id,
                    name=dataset.name,
                    source_type=SourceType.IMPORTED_ALIGNMENT,
                    records=records,
                    metadata={
                        **dict(dataset.metadata),
                        "source_alignment_id": dataset.alignment_id,
                        "identification_query": "UNGAPPED_ALIGNMENT",
                    },
                ),
                dataset.alignment_id,
            )
        raise ValueError("Identification workflow requires a SequenceDataset or AlignmentDataset.")

    def _source_dataset_for_result(self, result: object) -> SequenceDataset:
        project = self._require_project()
        parent_id = getattr(result, "parent_dataset_id", None)
        if not isinstance(parent_id, str) or not project.has_dataset(parent_id):
            raise ValueError("Result parent dataset is not present in the Project.")
        parent = project.get_dataset(parent_id)
        if isinstance(parent, SequenceDataset):
            source = parent
        elif isinstance(parent, AlignmentDataset):
            source, _parent_id = self._identification_query_dataset(parent)
        else:
            raise ValueError("Result parent is not a supported dataset type.")
        metadata_key = "blast_result_id" if isinstance(result, BlastResultDataset) else "bold_result_id"
        return SequenceDataset(
            dataset_id=source.dataset_id,
            name=source.name,
            source_type=source.source_type,
            records=source.records,
            metadata={**dict(source.metadata), metadata_key: result.result_id},
        )

    def _handle_consensus_related_request(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("action") != "TRACE_JUMP":
            return
        source_dataset = getattr(payload.get("viewer"), "source_dataset", None)
        if source_dataset is None or self._tab_manager is None:
            return
        resource_key = f"chromatogram:{getattr(source_dataset, 'dataset_id', '')}"
        chromatogram_viewer = None
        finder = getattr(self._tab_manager, "viewer_for_resource_key", None)
        if callable(finder):
            chromatogram_viewer = finder(resource_key)
        if chromatogram_viewer is None:
            try:
                chromatogram_viewer = ChromatogramViewer(
                    reads_from_dataset(source_dataset),
                    title=f"Chromatograms: {getattr(source_dataset, 'name', 'Dataset')}",
                    source_object_id=getattr(source_dataset, "dataset_id", None),
                    context=self._viewer_context,
                    source_dataset=source_dataset,
                )
            except Exception:
                return
            self._tab_manager.open_viewer(chromatogram_viewer, resource_key=resource_key)
        else:
            self._tab_manager.open_viewer(chromatogram_viewer, resource_key=resource_key)
        jump = getattr(chromatogram_viewer, "jump_to_trace_position", None)
        if callable(jump) and payload.get("read_id") is not None and payload.get("raw_trace_position") is not None:
            jump(payload.get("read_id"), payload.get("raw_trace_position"))

    def register_reviewed_consensus_from_viewer(self, viewer: object) -> SequenceDataset:
        """Create a Reviewed Consensus Dataset from a Studio viewer and register it."""

        project = self._state.current_project
        if not isinstance(project, Project):
            raise ValueError("No Project is open.")
        alignment_dataset = getattr(viewer, "alignment_dataset", None)
        if not isinstance(alignment_dataset, AlignmentDataset):
            raise ValueError("Consensus Review requires an AlignmentDataset.")
        if not project.has_dataset(alignment_dataset.alignment_id):
            raise ValueError(
                "AlignmentDataset must be registered in the current Project before review."
            )
        dataset_id = _unique_dataset_id(
            project,
            f"{alignment_dataset.alignment_id}_reviewed_consensus",
        )
        dataset = build_reviewed_consensus_dataset(
            alignment_dataset,
            dataset_id=dataset_id,
            name=f"{alignment_dataset.name} reviewed consensus",
            original_consensus=getattr(viewer, "original_consensus"),
            reviewed_consensus=getattr(viewer, "reviewed_consensus"),
            change_log=getattr(viewer, "change_log"),
        )
        updated = add_reviewed_consensus_dataset_to_project(
            project,
            dataset,
            parent_dataset_id=alignment_dataset.alignment_id,
            display_name="Reviewed Consensus",
            metadata={"added_by": "Consensus Review Viewer"},
        )
        self._state.replace_project(updated, dirty=True)
        self._last_warnings = ()
        return dataset


def _dataset_identifier(dataset: object) -> str:
    return (
        getattr(dataset, "dataset_id", None)
        or getattr(dataset, "alignment_id", None)
        or repr(id(dataset))
    )


def _sequence_dataset_from_reads(
    reads: tuple[object, ...] | list[object],
    *,
    dataset_id: str,
    name: str,
    metadata: dict[str, object] | None = None,
) -> SequenceDataset:
    record_ids = tuple(_record_id_from_source_filename(getattr(read, "filename")) for read in reads)
    duplicates = tuple(sorted({record_id for record_id in record_ids if record_ids.count(record_id) > 1}))
    if duplicates:
        raise ValueError(
            "AB1 source filenames produce duplicate record IDs after extension removal: "
            + ", ".join(duplicates)
        )
    source_batch = str((metadata or {}).get("source_batch", "")).strip()
    records = tuple(
        SequenceRecord(
            sequence_id=record_id,
            sequence=getattr(read, "trimmed_sequence", None) or getattr(read, "sequence"),
            source_reference=read,
            metadata={
                "source_filepath": str(getattr(read, "_sangerflow_source_filepath", "")),
                "source_filename": getattr(read, "filename", ""),
                "workspace_relative_path": str(
                    getattr(read, "_sangerflow_workspace_relative_path", "")
                ),
                **({"source_batch": source_batch} if source_batch else {}),
            },
        )
        for read, record_id in zip(reads, record_ids)
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=SourceType.AB1_TRIMMED,
        records=records,
        metadata=metadata,
    )


def _record_id_from_source_filename(filename: object) -> str:
    """Keep biological record IDs separate from raw AB1 filenames."""

    value = str(filename)
    path = Path(value)
    return path.stem if path.suffix.lower() in {".ab1", ".abi"} else value


def _copy_sequence_dataset(
    dataset: SequenceDataset,
    *,
    dataset_id: str,
    source_type: SourceType | None = None,
    name: str | None = None,
    metadata: dict[str, object] | None = None,
) -> SequenceDataset:
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name or dataset.name,
        source_type=source_type or dataset.source_type,
        records=dataset.records,
        metadata=dict(dataset.metadata) if metadata is None else metadata,
    )


def _gapless_mafft_input(dataset: SequenceDataset) -> SequenceDataset:
    """Make an ephemeral MAFFT input without mutating an unaligned Dataset.

    A ``-`` in an unaligned editor is not silently reinterpreted as an
    alignment column.  The user has explicitly approved stripping it for the
    MAFFT request; the Project revision and its raw record sequences remain
    unchanged.
    """

    records = tuple(
        SequenceRecord(
            sequence_id=record.sequence_id,
            sequence=record.sequence.replace("-", ""),
            description=record.description,
            source_reference=record.source_reference,
            metadata=record.metadata,
            provenance=record.provenance,
        )
        for record in dataset.records
    )
    empty = tuple(record.sequence_id for record in records if not record.sequence)
    if empty:
        raise ValueError(
            "MAFFT cannot align records containing only gaps: " + ", ".join(empty)
        )
    return SequenceDataset(
        dataset_id=f"{dataset.dataset_id}_gapless_mafft_input",
        name=f"{dataset.name} (gapless MAFFT input)",
        source_type=dataset.source_type,
        records=records,
        metadata={
            **dict(dataset.metadata),
            "temporary": True,
            "gap_handling": "removed_existing_gap_symbols",
            "source_dataset_id": dataset.dataset_id,
        },
    )


def _alignment_dataset_from_alignment(
    alignment: object,
    parent_dataset: SequenceDataset,
    *,
    alignment_id: str,
    name: str,
    metadata: dict[str, object] | None = None,
) -> AlignmentDataset:
    source_record_by_alignment_id = {
        getattr(record.source_reference, "filename", record.sequence_id): record
        for record in parent_dataset.records
    }
    records: list[AlignmentRecord] = []
    for record in alignment:
        source_record = source_record_by_alignment_id.get(record.id)
        source_record_id = source_record.sequence_id if source_record is not None else record.id
        # Alignment rows are derived presentations of their source records;
        # carry non-scientific provenance metadata such as source_batch forward
        # without altering the immutable parent SequenceDataset.
        row_metadata = dict(source_record.metadata) if source_record is not None else {}
        row_metadata["source_filename"] = record.id
        records.append(AlignmentRecord(
            record_id=source_record_id,
            source_record_id=source_record_id,
            aligned_sequence=str(record.seq),
            metadata=row_metadata,
        ))
    return AlignmentDataset.from_sequence_dataset(
        alignment_id=alignment_id,
        name=name,
        parent_dataset=parent_dataset,
        records=tuple(records),
        metadata={
            "alignment_method": "MAFFT",
            "software": "MAFFT",
            "parent_dataset_id": parent_dataset.dataset_id,
            "derivation_type": DerivationType.ALIGNMENT_FROM_DATASET.value,
            "input_source_type": parent_dataset.source_type.value,
            **(metadata or {}),
        },
    )


def _unique_dataset_id(project: object | None, base_id: str) -> str:
    base = _safe_identifier(base_id) or "dataset"
    if project is None or not getattr(project, "has_dataset", lambda _id: False)(base):
        return base
    index = 2
    while getattr(project, "has_dataset")(f"{base}_{index}"):
        index += 1
    return f"{base}_{index}"


def _unique_result_id(project: Project, base_id: str) -> str:
    base = _safe_identifier(base_id) or "blast_result"
    if not project.has_analysis_result(base):
        return base
    index = 2
    while project.has_analysis_result(f"{base}_{index}"):
        index += 1
    return f"{base}_{index}"


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in str(value)
    ).strip("_")


def _source_batch_from_import_label(source_label: str) -> str:
    """Compatibility fallback for direct callers that supply an AB1 folder label.

    Normal GUI imports pass the selected folder name explicitly.  This fallback
    deliberately recognises only that label, never a Dataset name, workspace
    directory, or copied Raw_Data path.
    """

    prefix = "AB1 Folder:"
    if isinstance(source_label, str) and source_label.startswith(prefix):
        return source_label[len(prefix):].strip()
    return ""


def _unique_copy_destination(directory: Path, filename: str) -> Path:
    """Choose a non-overwriting filename within a Workspace Raw_Data directory."""

    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _review_decisions_metadata(reviewed_consensus: object) -> tuple[dict[str, object], ...]:
    decisions = getattr(reviewed_consensus, "applied_decisions", ())
    values: list[dict[str, object]] = []
    for decision in decisions:
        timestamp = getattr(decision, "timestamp", None)
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        decision_type = getattr(decision, "decision_type", "")
        if hasattr(decision_type, "value"):
            decision_type = decision_type.value
        values.append(
            {
                "sample_id": getattr(decision, "sample_id", ""),
                "consensus_position": getattr(decision, "consensus_position", None),
                "original_base": getattr(decision, "original_base", None),
                "reviewed_base": getattr(decision, "reviewed_base", None),
                "decision_type": decision_type,
                "reason": getattr(decision, "reason", ""),
                "reviewer": getattr(decision, "reviewer", ""),
                "timestamp": timestamp,
            }
        )
    return tuple(values)


def _selection_dataset_metadata(
    *,
    parent_dataset_id: str,
    derivation_type: str,
    source_analysis: str,
    result_id: str,
    selection: object,
) -> dict[str, object]:
    return {
        "parent_dataset_id": parent_dataset_id,
        "derivation_type": derivation_type,
        "source_analysis": source_analysis,
        "source_result_id": result_id,
        "filter_conditions": dict(getattr(selection, "filter_metadata", {}) or {}),
        "selected_record_ids": tuple(getattr(selection, "selected_query_ids", ())),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _reattach_ab1_source_references(
    project: Project,
    *,
    workspace_root: Path | None = None,
) -> tuple[Project, tuple[str, ...]]:
    """Rebuild transient SangerRead references from persisted source file paths.

    Project JSON deliberately omits ``SequenceRecord.source_reference``.  Studio
    can still restore chromatogram-review behavior when the original AB1 files
    remain at the saved paths by reading those files after bundle load.
    """

    warnings: list[str] = []
    changed = False
    entries: list[ProjectDatasetEntry] = []
    for entry in project.dataset_entries:
        dataset = entry.dataset
        if not isinstance(dataset, SequenceDataset):
            entries.append(entry)
            continue
        records: list[SequenceRecord] = []
        record_changed = False
        for record in dataset.records:
            source_path = str(record.metadata.get("source_filepath", "")).strip()
            relative_path = str(record.metadata.get("workspace_relative_path", "")).strip()
            source_candidates = _ab1_source_candidates(
                source_path,
                relative_path,
                workspace_root=workspace_root,
            )
            if not source_candidates:
                records.append(record)
                continue
            path = next((candidate for candidate in source_candidates if candidate.is_file()), None)
            if path is None:
                source_description = source_path or relative_path
                warnings.append(
                    f"Missing AB1 source for {record.sequence_id}: {source_description}"
                )
                records.append(record)
                continue
            try:
                read = trim_sequence(read_ab1(str(path)))
            except Exception as error:  # pragma: no cover - exercised by GUI error path
                warnings.append(
                    f"Could not reload AB1 source for {record.sequence_id}: {error}"
                )
                records.append(record)
                continue
            setattr(read, "_sangerflow_source_filepath", str(path))
            # The filename may include a workspace-only collision suffix such
            # as ``_3``.  Retain the persisted biological/source filename for
            # evidence labels; record.sequence_id itself is never regenerated
            # during bundle open.
            persisted_filename = str(record.metadata.get("source_filename", "")).strip()
            if persisted_filename:
                read.filename = persisted_filename
            records.append(
                SequenceRecord(
                    sequence_id=record.sequence_id,
                    sequence=record.sequence,
                    description=record.description,
                    source_reference=read,
                    metadata=record.metadata,
                    provenance=record.provenance,
                )
            )
            record_changed = True
        if record_changed:
            changed = True
            dataset = SequenceDataset(
                dataset_id=dataset.dataset_id,
                name=dataset.name,
                source_type=dataset.source_type,
                records=tuple(records),
                metadata=dataset.metadata,
            )
            entry = ProjectDatasetEntry(
                dataset=dataset,
                display_name=entry.display_name,
                parent_dataset_id=entry.parent_dataset_id,
                derivation_type=entry.derivation_type,
                metadata=entry.metadata,
                lineage_relations=entry.lineage_relations,
                logical_id=entry.logical_id,
                revision_number=entry.revision_number,
                revision_state=entry.revision_state,
                revision_operation=entry.revision_operation,
                supersedes_dataset_id=entry.supersedes_dataset_id,
            )
        entries.append(entry)
    if not changed:
        return project, tuple(warnings)
    return (
        Project(
            project_id=project.project_id,
            name=project.name,
            dataset_entries=tuple(entries),
            metadata=project.metadata,
            analysis_results=project.analysis_results,
        ),
        tuple(warnings),
    )


def _ab1_source_candidates(
    absolute_path: str,
    workspace_relative_path: str,
    *,
    workspace_root: Path | None,
) -> tuple[Path, ...]:
    """Return safe absolute-first source candidates for a persisted AB1 read."""

    candidates: list[Path] = []
    if absolute_path:
        candidates.append(Path(absolute_path))
    if workspace_root is not None and workspace_relative_path:
        relative = Path(workspace_relative_path)
        if not relative.is_absolute() and ".." not in relative.parts:
            candidates.append(workspace_root / relative)
    return tuple(candidates)
