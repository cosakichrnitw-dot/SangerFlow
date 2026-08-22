"""Project adapters for immutable datasets derived from a BLAST selection."""

from __future__ import annotations

from collections.abc import Mapping

from core.blast_filter import BlastResultSelection
from core.lineage import LineageRelation, LineageRelationType, LineageSourceKind
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset
from workflow.blast_selection_dataset import create_dataset_from_blast_selection


def add_blast_selection_dataset_to_project(
    project: Project,
    dataset: SequenceDataset,
    *,
    parent_dataset_id: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Append a BLAST-selection subset to an immutable project.

    ``Project`` currently defines ``SUBSET_FROM_DATASET`` as its compatible
    general derivation type.  The more specific BLAST-selection provenance is
    retained in entry metadata without changing Project's public enum.
    """

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    if dataset.metadata.get("derived_from") != "BLAST_SELECTION":
        raise ValueError("dataset must be derived_from BLAST_SELECTION")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    source_dataset_id = dataset.metadata.get("source_dataset_id")
    resolved_parent_id = parent_dataset_id if parent_dataset_id is not None else source_dataset_id
    if not isinstance(resolved_parent_id, str) or not resolved_parent_id.strip():
        raise ValueError("parent_dataset_id is required for a BLAST selection dataset")

    entry_metadata = dict(metadata or {})
    entry_metadata.update(
        {
            "created_by": "BLAST Selection",
            "derivation_detail": "BLAST_SELECTION",
            "blast_result_id": dataset.metadata.get("blast_result_id"),
        }
    )
    relations = [
        LineageRelation(
            LineageSourceKind.DATASET,
            resolved_parent_id,
            LineageRelationType.SUBSET_FROM_DATASET,
        )
    ]
    blast_result_id = dataset.metadata.get("blast_result_id")
    if isinstance(blast_result_id, str) and project.has_analysis_result(blast_result_id):
        relations.append(
            LineageRelation(
                LineageSourceKind.ANALYSIS_RESULT,
                blast_result_id,
                LineageRelationType.SELECTED_FROM_BLAST,
            )
        )
    return project.add_dataset(
        dataset,
        parent_dataset_id=resolved_parent_id,
        derivation_type=DerivationType.SUBSET_FROM_DATASET,
        metadata=entry_metadata,
        lineage_relations=tuple(relations),
    )


def create_project_dataset_from_blast_selection(
    project: Project,
    source_dataset: SequenceDataset,
    selection: BlastResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Create a selection subset, then return a Project with it appended."""

    dataset = create_dataset_from_blast_selection(
        source_dataset,
        selection,
        dataset_id=dataset_id,
        name=name,
        metadata=metadata,
    )
    return add_blast_selection_dataset_to_project(
        project,
        dataset,
        parent_dataset_id=source_dataset.dataset_id,
        metadata=metadata,
    )
