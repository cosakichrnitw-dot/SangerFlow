"""Project adapter for immutable BOLD workflow results."""

from __future__ import annotations

from collections.abc import Mapping

from core.analysis_result import AnalysisResultType
from core.bold_result import BoldResultDataset
from core.project import Project


def add_bold_result_to_project(
    project: Project,
    bold_result: BoldResultDataset,
    *,
    display_name: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> Project:
    """Return a new Project containing ``bold_result`` as a BOLD analysis entry."""

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    if not isinstance(bold_result, BoldResultDataset):
        raise ValueError("bold_result must be a BoldResultDataset")
    if not bold_result.hits:
        raise ValueError("bold_result must contain at least one hit")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    analysis_result = bold_result.analysis_result
    if analysis_result.result_type is not AnalysisResultType.BOLD:
        raise ValueError("bold_result must expose an AnalysisResultType.BOLD result")
    if not analysis_result.parent_dataset_id.strip():
        raise ValueError("bold_result parent_dataset_id must be non-empty")

    entry_metadata = {"added_by": "BOLD Workflow"}
    if metadata is not None:
        entry_metadata.update(metadata)
    return project.add_analysis_result(
        analysis_result,
        display_name=display_name,
        metadata=entry_metadata,
    )
