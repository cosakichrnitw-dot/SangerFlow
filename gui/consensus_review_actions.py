"""Application callbacks for promoting reviewed consensus into a Project.

Tk review windows supply an immutable ``ReviewedConsensus`` value here.  This
module owns the workflow hand-off; it does not inspect GUI widgets, mutate a
review session, or retain a Project internally.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from core.human_review import ReviewedConsensus
from core.project import Project
from workflow.project_reviewed_consensus import (
    add_reviewed_consensus_dataset_to_project,
)
from workflow.reviewed_consensus_dataset import create_dataset_from_reviewed_consensus


class ConsensusReviewActionError(ValueError):
    """Raised for safe failures at the consensus-review application boundary."""


ProjectChangedCallback = Callable[[Project], None]


def register_reviewed_consensus_in_project(
    project: Project,
    reviewed_consensus: ReviewedConsensus,
    *,
    dataset_id: str,
    name: str,
    parent_dataset_id: str,
    metadata: Mapping[str, object] | None = None,
    display_name: str | None = None,
    on_project_changed: ProjectChangedCallback | None = None,
) -> Project:
    """Create and register one reviewed-consensus Dataset in a new Project.

    ``parent_dataset_id`` must identify the already registered candidate
    dataset.  The original Project and reviewed consensus remain unchanged;
    callers retain the returned Project via ``on_project_changed``.
    """
    if not isinstance(project, Project):
        raise ConsensusReviewActionError("project must be a Project")
    if not isinstance(reviewed_consensus, ReviewedConsensus):
        raise ConsensusReviewActionError("reviewed_consensus must be a ReviewedConsensus")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ConsensusReviewActionError("dataset_id must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise ConsensusReviewActionError("name must be a non-empty string")
    if not isinstance(parent_dataset_id, str) or not parent_dataset_id.strip():
        raise ConsensusReviewActionError("parent_dataset_id must be a non-empty string")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ConsensusReviewActionError("metadata must be a mapping or None")
    if on_project_changed is not None and not callable(on_project_changed):
        raise ConsensusReviewActionError("on_project_changed must be callable or None")

    dataset_metadata = dict(metadata or {})
    dataset_metadata["parent_dataset_id"] = parent_dataset_id
    try:
        dataset = create_dataset_from_reviewed_consensus(
            reviewed_consensus,
            dataset_id=dataset_id,
            name=name,
            metadata=dataset_metadata,
        )
        updated_project = add_reviewed_consensus_dataset_to_project(
            project,
            dataset,
            parent_dataset_id=parent_dataset_id,
            display_name=display_name,
            metadata={"created_by": "Consensus Review Manager"},
        )
    except (TypeError, ValueError) as error:
        raise ConsensusReviewActionError(str(error)) from error

    if on_project_changed is not None:
        on_project_changed(updated_project)
    return updated_project
