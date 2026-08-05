"""Project adapter for immutable BLAST workflow results."""

from __future__ import annotations

from collections.abc import Mapping

from core.analysis_result import AnalysisResultType
from core.blast_result import BlastResultDataset
from core.project import Project


def add_blast_result_to_project(
    project: Project,
    blast_result: BlastResultDataset,
    *,
    display_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Return a new project containing ``blast_result`` as an analysis entry.

    The adapter stores the common ``AnalysisResult`` view exposed by the
    BLAST-specific payload; it never copies or modifies the BLAST hit data.
    """

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(blast_result, BlastResultDataset):
        raise ValueError("blast_result must be a BlastResultDataset")
    analysis_result = blast_result.analysis_result
    if analysis_result.result_type is not AnalysisResultType.BLAST:
        raise ValueError("blast_result must expose an AnalysisResultType.BLAST result")
    if not analysis_result.parent_dataset_id.strip():
        raise ValueError("blast_result parent_dataset_id must be non-empty")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    entry_metadata = {"added_by": "BLAST Workflow"}
    if metadata is not None:
        entry_metadata.update(metadata)
    return project.add_analysis_result(
        analysis_result,
        display_name=display_name,
        metadata=entry_metadata,
    )
