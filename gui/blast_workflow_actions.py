"""Application-layer callbacks connecting BLAST GUI actions to workflows.

This module contains no Tk widgets and does not perform BLAST communication.
It keeps result-payload resolution outside ``Project``, which intentionally
stores only common immutable ``AnalysisResult`` metadata.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.analysis_result import AnalysisResultType
from core.blast_filter import BlastResultSelection
from core.blast_result import BlastResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset
from workflow.blast_selection_project import create_project_dataset_from_blast_selection


class BlastWorkflowActionError(ValueError):
    """A safe user-facing error at the BLAST GUI/application boundary."""


BlastResultResolver = Callable[[str], BlastResultDataset]
OpenBlastResultCallback = Callable[[BlastResultDataset], None]
ProjectChangedCallback = Callable[[Project], None]


def open_project_blast_result(
    project: Project,
    result_id: str,
    *,
    resolve_blast_result: BlastResultResolver,
    on_open_blast_result: OpenBlastResultCallback,
) -> BlastResultDataset:
    """Resolve a tracked BLAST payload and pass it to a Viewer callback."""

    if not isinstance(project, Project):
        raise BlastWorkflowActionError("project must be a Project")
    if not isinstance(result_id, str) or not result_id.strip():
        raise BlastWorkflowActionError("result_id must be a non-empty string")
    if not callable(resolve_blast_result):
        raise BlastWorkflowActionError("resolve_blast_result must be callable")
    if not callable(on_open_blast_result):
        raise BlastWorkflowActionError("on_open_blast_result must be callable")

    try:
        project_result = project.get_analysis_result(result_id)
    except KeyError as error:
        raise BlastWorkflowActionError(f"unknown project analysis result: {result_id}") from error
    if project_result.result_type is not AnalysisResultType.BLAST:
        raise BlastWorkflowActionError(f"analysis result is not BLAST: {result_id}")

    blast_result = resolve_blast_result(result_id)
    if not isinstance(blast_result, BlastResultDataset):
        raise BlastWorkflowActionError("BLAST result resolver must return a BlastResultDataset")
    resolved_common_result = blast_result.analysis_result
    if (
        resolved_common_result.result_id != project_result.result_id
        or resolved_common_result.parent_dataset_id != project_result.parent_dataset_id
    ):
        raise BlastWorkflowActionError("resolved BLAST result does not match the project analysis result")

    on_open_blast_result(blast_result)
    return blast_result


def create_project_dataset_from_blast_viewer_selection(
    project: Project,
    source_dataset: SequenceDataset,
    selection: BlastResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: dict[str, object] | None = None,
    on_project_changed: Optional[ProjectChangedCallback] = None,
) -> Project:
    """Create and register a BLAST-selection dataset through one callback boundary."""

    updated_project = create_project_dataset_from_blast_selection(
        project,
        source_dataset,
        selection,
        dataset_id=dataset_id,
        name=name,
        metadata=metadata,
    )
    if on_project_changed is not None:
        on_project_changed(updated_project)
    return updated_project
