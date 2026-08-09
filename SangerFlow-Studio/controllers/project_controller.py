"""Project-facing controller; views delegate state changes here."""

from pathlib import Path

from app.app_state import AppState
from app.selection import SelectionKind, StudioSelection
from core.ab1_reader import read_ab1
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.chromatogram_alignment import align_reads
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import LoadedProjectBundle, load_project_bundle
from core.trimming import trim_sequence
from widgets.viewers import ViewerContext, ViewerRegistry
from widgets.viewers.chromatogram_viewer import ChromatogramViewer


class ProjectController:
    """Coordinates views with existing immutable SangerFlow Project models."""

    def __init__(self, state: AppState) -> None:
        self._state = state
        self._viewer_registry: ViewerRegistry | None = None
        self._viewer_context: ViewerContext | None = None
        self._tab_manager: object | None = None

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

    def open_project(self, project: object) -> None:
        self._state.set_project(project)

    def open_project_bundle(self, filepath: str) -> LoadedProjectBundle:
        """Load a bundle through persistence, then publish it to the Studio state."""

        loaded_bundle = load_project_bundle(filepath)
        self._state.set_loaded_project_bundle(loaded_bundle)
        return loaded_bundle

    def open_ab1_folder(self, folderpath: str) -> str | None:
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

        reads = []
        for filepath in files:
            reads.append(trim_sequence(read_ab1(str(filepath))))

        dataset = _sequence_dataset_from_reads(
            reads,
            dataset_id=_unique_dataset_id(
                self._state.project,
                _safe_identifier(folder.name) or "ab1_reads",
            ),
            name=f"AB1 reads: {folder.name}",
            metadata={
                "source": "AB1 Folder",
                "source_folder": str(folder),
                "read_count": len(reads),
                "creation_context": "SangerFlow-Studio AB1 folder open",
            },
        )
        project = self._state.project
        if project is None:
            project = Project.create(
                project_id=_safe_identifier(folder.name) or "sangerflow_project",
                name=f"Project: {folder.name}",
                metadata={"created_by": "SangerFlow-Studio", "source_folder": str(folder)},
            )
        project = project.add_dataset(
            dataset,
            derivation_type=DerivationType.TRIMMED_FROM_READS,
            metadata={"added_by": "AB1 Folder Open"},
        )
        self._state.set_project(project, self._state.current_repository)

        viewer = ChromatogramViewer(
            reads,
            title=f"Chromatograms: {folder.name}",
            source_object_id=dataset.dataset_id,
            context=self._viewer_context,
            source_dataset=dataset,
        )
        return self._tab_manager.open_viewer(
            viewer,
            resource_key=f"chromatogram:{dataset.dataset_id}",
        )

    def select_item(self, item: object | None) -> None:
        self._state.set_selected_item(item)
        if isinstance(item, StudioSelection) and item.kind == SelectionKind.DATASET:
            self.open_selected_item()

    def activate_tab(self, tab_name: str) -> None:
        self._state.set_active_tab(tab_name)

    def open_selected_item(self) -> str | None:
        selection = self._state.selected_item
        if not isinstance(selection, StudioSelection):
            return None
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
        resource_key = f"dataset:{_dataset_identifier(dataset)}"
        return self._tab_manager.open_viewer(viewer, resource_key=resource_key)

    def align_chromatogram_viewer(self, viewer: ChromatogramViewer) -> str | None:
        """Create an AlignmentDataset from a ChromatogramViewer and open AlignmentViewer."""

        if (
            self._viewer_registry is None
            or self._viewer_context is None
            or self._tab_manager is None
        ):
            return None
        reads = tuple(read_view.read for read_view in viewer.visible_read_views)
        if len(reads) < 2:
            viewer.status_message_changed.emit("At least two visible reads are required for alignment.")
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

        alignment = align_reads(reads)
        alignment_dataset_id = _unique_dataset_id(
            project,
            f"{source_dataset.dataset_id}_alignment",
        )
        alignment_dataset = _alignment_dataset_from_alignment(
            alignment,
            source_dataset,
            alignment_id=alignment_dataset_id,
            name=f"{source_dataset.name} alignment",
        )
        project = project.add_dataset(
            alignment_dataset,
            parent_dataset_id=source_dataset.dataset_id,
            derivation_type=DerivationType.ALIGNMENT_FROM_DATASET,
            metadata={"added_by": "Chromatogram Align"},
        )
        self._state.set_project(project, self._state.current_repository)
        alignment_viewer = self._viewer_registry.create_viewer_for(
            alignment_dataset,
            self._viewer_context,
        )
        return self._tab_manager.open_viewer(
            alignment_viewer,
            resource_key=f"alignment:{alignment_dataset.alignment_id}",
        )


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
    records = tuple(
        SequenceRecord(
            sequence_id=getattr(read, "filename"),
            sequence=getattr(read, "trimmed_sequence", None) or getattr(read, "sequence"),
            source_reference=read,
        )
        for read in reads
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=SourceType.AB1_TRIMMED,
        records=records,
        metadata=metadata,
    )


def _alignment_dataset_from_alignment(
    alignment: object,
    parent_dataset: SequenceDataset,
    *,
    alignment_id: str,
    name: str,
) -> AlignmentDataset:
    records = tuple(
        AlignmentRecord(
            record_id=record.id,
            source_record_id=record.id,
            aligned_sequence=str(record.seq),
        )
        for record in alignment
    )
    return AlignmentDataset.from_sequence_dataset(
        alignment_id=alignment_id,
        name=name,
        parent_dataset=parent_dataset,
        records=records,
        metadata={
            "alignment_method": "MAFFT",
            "software": "MAFFT",
            "parent_dataset_id": parent_dataset.dataset_id,
            "derivation_type": DerivationType.ALIGNMENT_FROM_DATASET.value,
            "input_source_type": parent_dataset.source_type.value,
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


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in str(value)
    ).strip("_")
