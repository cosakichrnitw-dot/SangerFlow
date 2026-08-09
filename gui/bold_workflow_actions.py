"""Callback-only application action for opening project-tracked BOLD results."""

from __future__ import annotations

from typing import Callable, Optional

from core.analysis_result import AnalysisResultType
from core.bold_filter import BoldResultSelection
from core.bold_result import BoldResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset
from workflow.bold_selection_project import create_project_dataset_from_bold_selection


class BoldWorkflowActionError(ValueError):
    """A safe user-facing error at the BOLD GUI/application boundary."""


BoldResultResolver = Callable[[str], BoldResultDataset]
OpenBoldResultCallback = Callable[[BoldResultDataset], None]
ProjectChangedCallback = Callable[[Project], None]


def open_project_bold_result(
    project: Project,
    result_id: str,
    *,
    resolve_bold_result: BoldResultResolver,
    on_open_bold_result: OpenBoldResultCallback,
) -> BoldResultDataset:
    """Resolve a tracked BOLD payload and pass it to a viewer callback."""

    if not isinstance(project, Project):
        raise BoldWorkflowActionError("project must be a Project")
    if not isinstance(result_id, str) or not result_id.strip():
        raise BoldWorkflowActionError("result_id must be a non-empty string")
    if not callable(resolve_bold_result):
        raise BoldWorkflowActionError("resolve_bold_result must be callable")
    if not callable(on_open_bold_result):
        raise BoldWorkflowActionError("on_open_bold_result must be callable")
    try:
        project_result = project.get_analysis_result(result_id)
    except KeyError as error:
        raise BoldWorkflowActionError(f"unknown project analysis result: {result_id}") from error
    if project_result.result_type is not AnalysisResultType.BOLD:
        raise BoldWorkflowActionError(f"analysis result is not BOLD: {result_id}")

    bold_result = resolve_bold_result(result_id)
    if not isinstance(bold_result, BoldResultDataset):
        raise BoldWorkflowActionError("BOLD result resolver must return a BoldResultDataset")
    resolved_common_result = bold_result.analysis_result
    if (
        resolved_common_result.result_id != project_result.result_id
        or resolved_common_result.parent_dataset_id != project_result.parent_dataset_id
    ):
        raise BoldWorkflowActionError("resolved BOLD result does not match the project analysis result")
    on_open_bold_result(bold_result)
    return bold_result


def create_project_dataset_from_bold_viewer_selection(
    project: Project,
    source_dataset: SequenceDataset,
    selection: BoldResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: dict[str, object] | None = None,
    on_project_changed: Optional[ProjectChangedCallback] = None,
) -> Project:
    """Create and register a BOLD-selection dataset through one callback boundary."""

    updated_project = create_project_dataset_from_bold_selection(
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
