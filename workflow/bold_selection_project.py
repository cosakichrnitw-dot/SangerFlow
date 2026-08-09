"""Project adapters for immutable datasets derived from a BOLD selection."""

from __future__ import annotations

from collections.abc import Mapping

from core.bold_filter import BoldResultSelection
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset
from workflow.bold_selection_dataset import create_dataset_from_bold_selection


def add_bold_selection_dataset_to_project(
    project: Project,
    dataset: SequenceDataset,
    *,
    parent_dataset_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Append a BOLD-selection subset to an immutable Project."""

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    if dataset.metadata.get("derived_from") != "BOLD_SELECTION":
        raise ValueError("dataset must be derived_from BOLD_SELECTION")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    source_dataset_id = dataset.metadata.get("source_dataset_id")
    resolved_parent_id = parent_dataset_id if parent_dataset_id is not None else source_dataset_id
    if not isinstance(resolved_parent_id, str) or not resolved_parent_id.strip():
        raise ValueError("parent_dataset_id is required for a BOLD selection dataset")

    entry_metadata = dict(metadata or {})
    entry_metadata.update(
        {
            "created_by": "BOLD Selection",
            "derivation_detail": "BOLD_SELECTION",
            "bold_result_id": dataset.metadata.get("bold_result_id"),
        }
    )
    return project.add_dataset(
        dataset,
        parent_dataset_id=resolved_parent_id,
        derivation_type=DerivationType.SUBSET_FROM_DATASET,
        metadata=entry_metadata,
    )


def create_project_dataset_from_bold_selection(
    project: Project,
    source_dataset: SequenceDataset,
    selection: BoldResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Create a BOLD-selection subset and append it to a new Project value."""

    dataset = create_dataset_from_bold_selection(
        source_dataset,
        selection,
        dataset_id=dataset_id,
        name=name,
        metadata=metadata,
    )
    return add_bold_selection_dataset_to_project(
        project,
        dataset,
        parent_dataset_id=source_dataset.dataset_id,
        metadata=metadata,
    )
