"""Add a MAFFT-derived alignment dataset to an immutable Project."""

from __future__ import annotations

from typing import Mapping

from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType


def add_alignment_to_project(
    project: Project,
    alignment_dataset: SequenceDataset,
    *,
    parent_dataset_id: str | None = None,
    display_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Return a new Project containing one validated MAFFT alignment dataset.

    The dataset itself remains the exact immutable workflow result.  Project
    entry metadata records this membership event without attempting to mutate
    the alignment dataset's metadata.
    """

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(alignment_dataset, SequenceDataset):
        raise ValueError("alignment_dataset must be a SequenceDataset")
    if alignment_dataset.source_type is not SourceType.IMPORTED_ALIGNMENT:
        raise ValueError("alignment_dataset must have SourceType.IMPORTED_ALIGNMENT")
    if not alignment_dataset.is_equal_length:
        raise ValueError("alignment_dataset must contain equal-length alignment rows")
    if alignment_dataset.metadata.get("derivation_type") != "ALIGNED_WITH_MAFFT":
        raise ValueError("alignment_dataset must be a MAFFT workflow result")

    resolved_parent_id = parent_dataset_id
    if resolved_parent_id is None:
        metadata_parent = alignment_dataset.metadata.get("parent_dataset_id")
        resolved_parent_id = metadata_parent if isinstance(metadata_parent, str) else None
    if not resolved_parent_id:
        raise ValueError("parent_dataset_id is required for a MAFFT alignment dataset")

    entry_metadata = dict(metadata or {})
    entry_metadata["added_to_project"] = True
    return project.add_dataset(
        alignment_dataset,
        display_name=display_name,
        parent_dataset_id=resolved_parent_id,
        derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
        metadata=entry_metadata,
    )
