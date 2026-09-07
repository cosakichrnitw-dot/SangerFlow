"""Read-only view model for the Project QC & Provenance Summary.

This module intentionally interprets only facts already held by immutable
Project values, record provenance, and the optional result repository.  It
does not load AB1 data, run workflows, or modify Project state.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from core.alignment_dataset import AlignmentDataset
from core.analysis_result import AnalysisResultType
from core.lineage import LineageSourceKind, RecordRef
from core.project import Project, ProjectDatasetEntry, RevisionState
from core.sequence_dataset import SequenceDataset, SequenceRecord
from services.project_workspace import resolve_workspace_source_path


AVAILABLE = "Available"
UNAVAILABLE = "Unavailable"
NOT_RECORDED = "Not recorded"
NOT_APPLICABLE = "Not applicable"
NO_RECORD = "No record"


@dataclass(frozen=True)
class ProjectOverview:
    project_name: str
    dataset_count: int
    sequence_dataset_count: int
    alignment_dataset_count: int
    analysis_result_count: int
    current_count: int
    superseded_count: int
    archived_count: int


@dataclass(frozen=True)
class DatasetLineageRow:
    dataset_id: str
    display_name: str
    dataset_type: str
    revision: int
    state: str
    operation: str
    sources: str


@dataclass(frozen=True)
class ProvenanceNode:
    record_ref: RecordRef
    record_name: str
    dataset_name: str
    source_batch: str
    source_filename: str
    ab1_source_state: str
    review_pairing_state: str
    direct_sources: tuple[RecordRef, ...]
    state: str = AVAILABLE


@dataclass(frozen=True)
class IdentificationSummary:
    dataset_id: str
    record_id: str
    best_hit: str
    scientific_name: str
    identity: str
    query_coverage: str
    accession: str
    result_id: str
    result_reference_state: str
    payload_state: str


@dataclass(frozen=True)
class AlignmentPreparationSummary:
    dataset_id: str
    display_name: str
    sequence_count: int
    alignment_length: int
    parent_dataset_id: str
    revision: int
    state: str
    marker_regions: str
    excluded_columns: str
    deleted_columns: str
    edited_positions: str
    marker_region_state: str


@dataclass(frozen=True)
class ProjectProvenanceSummary:
    overview: ProjectOverview
    lineage: tuple[DatasetLineageRow, ...]
    provenance_nodes: Mapping[RecordRef, ProvenanceNode]
    identifications: tuple[IdentificationSummary, ...]
    alignments: tuple[AlignmentPreparationSummary, ...]


def build_project_provenance_summary(
    project: Project,
    *,
    result_repository: object | None = None,
    workspace_root: Path | None = None,
) -> ProjectProvenanceSummary:
    """Create a lightweight snapshot from persisted Project facts only."""

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    entries = tuple(project.dataset_entries)
    overview = ProjectOverview(
        project_name=project.name,
        dataset_count=len(entries),
        sequence_dataset_count=sum(isinstance(entry.dataset, SequenceDataset) for entry in entries),
        alignment_dataset_count=sum(isinstance(entry.dataset, AlignmentDataset) for entry in entries),
        analysis_result_count=len(project.analysis_results),
        current_count=sum(entry.revision_state is RevisionState.CURRENT for entry in entries),
        superseded_count=sum(entry.revision_state is RevisionState.SUPERSEDED for entry in entries),
        archived_count=sum(entry.revision_state is RevisionState.ARCHIVED for entry in entries),
    )
    lineage = tuple(_lineage_row(entry) for entry in entries)
    provenance_nodes = _provenance_nodes(entries, workspace_root=workspace_root)
    identifications = _identifications(entries, project, result_repository)
    alignments = tuple(_alignment_summary(entry) for entry in entries if isinstance(entry.dataset, AlignmentDataset))
    return ProjectProvenanceSummary(overview, lineage, provenance_nodes, identifications, alignments)


def provenance_chain(
    summary: ProjectProvenanceSummary,
    record_ref: RecordRef,
) -> tuple[ProvenanceNode, ...]:
    """Follow direct persisted RecordRef sources, preserving Dataset identity."""

    values: list[ProvenanceNode] = []
    seen: set[RecordRef] = set()

    def visit(ref: RecordRef) -> None:
        if ref in seen:
            return
        seen.add(ref)
        node = summary.provenance_nodes.get(ref)
        if node is None:
            values.append(ProvenanceNode(ref, ref.sequence_id, ref.dataset_id, "", "", NOT_RECORDED, NOT_RECORDED, (), UNAVAILABLE))
            return
        values.append(node)
        for source in node.direct_sources:
            visit(source)

    visit(record_ref)
    return tuple(values)


def _lineage_row(entry: ProjectDatasetEntry) -> DatasetLineageRow:
    dataset = entry.dataset
    dataset_id = _dataset_id(entry)
    source_labels: list[str] = []
    for relation in entry.lineage_relations:
        kind = "Dataset" if relation.source_kind is LineageSourceKind.DATASET else "Result"
        source_labels.append(f"{kind}: {relation.source_id} ({relation.relation_type.value})")
    if entry.supersedes_dataset_id:
        source_labels.append(f"Revision: {entry.supersedes_dataset_id}")
    return DatasetLineageRow(
        dataset_id=dataset_id,
        display_name=entry.display_name,
        dataset_type="AlignmentDataset" if isinstance(dataset, AlignmentDataset) else "SequenceDataset",
        revision=entry.revision_number,
        state=entry.revision_state.value,
        operation=entry.revision_operation.value,
        sources="; ".join(source_labels) if source_labels else NO_RECORD,
    )


def _provenance_nodes(
    entries: tuple[ProjectDatasetEntry, ...],
    *,
    workspace_root: Path | None,
) -> dict[RecordRef, ProvenanceNode]:
    nodes: dict[RecordRef, ProvenanceNode] = {}
    for entry in entries:
        dataset = entry.dataset
        dataset_id = _dataset_id(entry)
        if isinstance(dataset, SequenceDataset):
            for record in dataset.records:
                ref = RecordRef(dataset_id, record.sequence_id)
                nodes[ref] = _sequence_provenance_node(
                    ref,
                    record,
                    entry,
                    workspace_root=workspace_root,
                )
        elif isinstance(dataset, AlignmentDataset):
            for record in dataset.records:
                ref = RecordRef(dataset_id, record.record_id)
                nodes[ref] = ProvenanceNode(
                    record_ref=ref,
                    record_name=record.record_id,
                    dataset_name=entry.display_name,
                    source_batch=_text(record.metadata.get("source_batch")),
                    source_filename=_text(record.metadata.get("source_filename")),
                    ab1_source_state=NOT_APPLICABLE,
                    review_pairing_state=NOT_APPLICABLE,
                    direct_sources=(RecordRef(dataset.parent_dataset_id, record.source_record_id),),
                )
    return nodes


def _sequence_provenance_node(
    ref: RecordRef,
    record: SequenceRecord,
    entry: ProjectDatasetEntry,
    *,
    workspace_root: Path | None,
) -> ProvenanceNode:
    metadata = record.metadata
    filepath = _text(metadata.get("source_filepath"))
    workspace_relative_path = _text(metadata.get("workspace_relative_path"))
    availability = _ab1_availability(
        filepath,
        workspace_relative_path,
        record.source_reference,
        workspace_root=workspace_root,
    )
    return ProvenanceNode(
        record_ref=ref,
        record_name=record.sequence_id,
        dataset_name=entry.display_name,
        source_batch=_text(metadata.get("source_batch") or entry.dataset.metadata.get("source_batch")),
        source_filename=_text(metadata.get("source_filename")),
        ab1_source_state=availability,
        review_pairing_state=_review_pairing_state(metadata),
        direct_sources=tuple(record.provenance.source_records),
    )


def _identifications(
    entries: tuple[ProjectDatasetEntry, ...],
    project: Project,
    repository: object | None,
) -> tuple[IdentificationSummary, ...]:
    result_ids_by_parent: dict[str, tuple[str, ...]] = {}
    for analysis_entry in project.analysis_results:
        if analysis_entry.result_type is AnalysisResultType.BLAST:
            result_ids_by_parent.setdefault(analysis_entry.parent_dataset_id, ())
            result_ids_by_parent[analysis_entry.parent_dataset_id] += (analysis_entry.result_id,)
    values: list[IdentificationSummary] = []
    for entry in entries:
        dataset = entry.dataset
        if not isinstance(dataset, SequenceDataset):
            continue
        entry_result_id = _text(entry.metadata.get("blast_result_id"))
        candidates = (entry_result_id,) if entry_result_id else result_ids_by_parent.get(dataset.dataset_id, ())
        result_id = candidates[0] if candidates else ""
        result_reference_state = AVAILABLE if result_id else NOT_RECORDED
        payload_state = _payload_state(repository, result_id) if result_id else NOT_RECORDED
        for record in dataset.records:
            metadata = record.metadata
            if not any(str(key).startswith("blast_") for key in metadata) and not result_id:
                continue
            values.append(IdentificationSummary(
                dataset_id=dataset.dataset_id,
                record_id=record.sequence_id,
                best_hit=_display_metadata(metadata, "blast_best_hit"),
                scientific_name=_display_metadata(metadata, "blast_scientific_name"),
                identity=_display_metadata(metadata, "blast_identity"),
                query_coverage=_display_metadata(metadata, "blast_query_coverage"),
                accession=_display_metadata(metadata, "blast_accession"),
                result_id=result_id or NOT_RECORDED,
                result_reference_state=result_reference_state,
                payload_state=payload_state,
            ))
    return tuple(values)


def _alignment_summary(entry: ProjectDatasetEntry) -> AlignmentPreparationSummary:
    dataset = entry.dataset
    assert isinstance(dataset, AlignmentDataset)
    metadata = dataset.metadata
    marker_regions = ", ".join(f"{region.name} ({region.start}–{region.end})" for region in dataset.marker_regions)
    invalidated = bool(metadata.get("marker_regions_invalidated_by_deleted_columns"))
    return AlignmentPreparationSummary(
        dataset_id=dataset.alignment_id,
        display_name=entry.display_name,
        sequence_count=dataset.sequence_count,
        alignment_length=dataset.length,
        parent_dataset_id=dataset.parent_dataset_id,
        revision=entry.revision_number,
        state=entry.revision_state.value,
        marker_regions=marker_regions or NO_RECORD,
        excluded_columns=_count_or_no_record(metadata.get("excluded_columns")),
        deleted_columns=_count_or_no_record(metadata.get("deleted_columns")),
        edited_positions=_count_or_no_record(metadata.get("edited_positions")),
        marker_region_state="Invalidated by column deletion" if invalidated else (AVAILABLE if dataset.marker_regions else NO_RECORD),
    )


def _dataset_id(entry: ProjectDatasetEntry) -> str:
    return entry.dataset.alignment_id if isinstance(entry.dataset, AlignmentDataset) else entry.dataset.dataset_id


def _payload_state(repository: object | None, result_id: str) -> str:
    if repository is None:
        return UNAVAILABLE
    has_result = getattr(repository, "has_result", None)
    if not callable(has_result):
        return UNAVAILABLE
    try:
        return AVAILABLE if bool(has_result(result_id)) else UNAVAILABLE
    except Exception:
        return UNAVAILABLE


def _ab1_availability(
    filepath: str,
    workspace_relative_path: str,
    source_reference: object | None,
    *,
    workspace_root: Path | None,
) -> str:
    if filepath:
        try:
            if Path(filepath).is_file():
                return AVAILABLE
        except OSError:
            pass
    workspace_path = resolve_workspace_source_path(workspace_root, workspace_relative_path)
    if workspace_path is not None:
        try:
            if workspace_path.is_file():
                return AVAILABLE
        except OSError:
            pass
    if filepath or workspace_relative_path:
        return UNAVAILABLE
    return AVAILABLE if source_reference is not None else NOT_RECORDED


def _count_or_no_record(value: object) -> str:
    if value is None:
        return NO_RECORD
    if isinstance(value, (tuple, list, set, frozenset)):
        return str(len(value))
    return NOT_RECORDED


def _display_metadata(metadata: Mapping[str, object], key: str) -> str:
    value = metadata.get(key)
    return str(value) if value not in (None, "") else NO_RECORD


def _review_pairing_state(metadata: Mapping[str, object]) -> str:
    """Summarize only persisted review/pairing declarations, never session state."""

    values: list[str] = []
    original = metadata.get("original_consensus")
    reviewed = metadata.get("reviewed_consensus")
    if isinstance(original, str) and isinstance(reviewed, str):
        changed = sum(left != right for left, right in zip(original, reviewed)) + abs(len(original) - len(reviewed))
        values.append(f"Reviewed consensus ({changed} change{'s' if changed != 1 else ''})")
    decisions = metadata.get("review_decisions")
    if isinstance(decisions, (tuple, list)):
        values.append(f"{len(decisions)} persisted decision{'s' if len(decisions) != 1 else ''}")
    resolution = _text(metadata.get("pairing_resolution"))
    if resolution:
        values.append("Manual pair" if resolution == "MANUAL" else "Automatic pair")
    return "; ".join(values) if values else NOT_RECORDED


def _text(value: object) -> str:
    return str(value).strip() if value not in (None, "") else ""
