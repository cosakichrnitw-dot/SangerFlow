"""Register reviewed-consensus datasets in immutable projects.

This adapter deliberately only links an already-created
``SourceType.REVIEWED_CONSENSUS`` dataset to a :class:`core.project.Project`.
It does not create consensus sequences, alter review decisions, or modify the
dataset being registered.
"""

from __future__ import annotations

from collections.abc import Mapping

from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType


def add_reviewed_consensus_dataset_to_project(
    project: Project,
    dataset: SequenceDataset,
    *,
    parent_dataset_id: str | None = None,
    display_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Return a new project containing a reviewed-consensus dataset.

    The parent is normally the Consensus Candidate dataset.  It may be passed
    explicitly, or supplied by the dataset metadata as ``parent_dataset_id``.
    Project-level validation verifies that the resolved parent exists.
    """
    if not isinstance(project, Project):
        raise TypeError("project must be a Project")
    if not isinstance(dataset, SequenceDataset):
        raise TypeError("dataset must be a SequenceDataset")
    if dataset.source_type is not SourceType.REVIEWED_CONSENSUS:
        raise ValueError("dataset must have SourceType.REVIEWED_CONSENSUS")
    if dataset.metadata.get("reviewed") is not True:
        raise ValueError("reviewed consensus dataset metadata must set reviewed=True")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping or None")

    resolved_parent_id = parent_dataset_id
    if resolved_parent_id is None:
        metadata_parent = dataset.metadata.get("parent_dataset_id")
        if isinstance(metadata_parent, str) and metadata_parent:
            resolved_parent_id = metadata_parent

    if not isinstance(resolved_parent_id, str) or not resolved_parent_id:
        raise ValueError(
            "parent_dataset_id is required to register a reviewed consensus dataset"
        )

    entry_metadata = dict(metadata or {})
    entry_metadata.update(
        {
            "created_by": "Reviewed Consensus",
            "derivation_detail": "REVIEWED_CONSENSUS",
            "consensus_method": dataset.metadata.get("consensus_method"),
            "original_read_count": dataset.metadata.get("original_read_count"),
        }
    )

    return project.add_dataset(
        dataset,
        display_name=display_name,
        parent_dataset_id=resolved_parent_id,
        derivation_type=DerivationType.REVIEWED_FROM_CONSENSUS,
        metadata=entry_metadata,
    )
