"""Build one immutable SequenceDataset from records across Project datasets.

This module is deliberately GUI-independent.  It resolves Project-local
``RecordRef`` values, diagnoses selection problems without guessing biological
identity, and creates a new dataset.  Project registration remains a caller
responsibility so controllers can publish an immutable updated Project.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType
from typing import Iterable, Mapping

from core.lineage import (
    LineageRelation,
    LineageRelationType,
    LineageSourceKind,
    RecordProvenance,
    RecordRef,
)
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


def _freeze_mapping(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping or None")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class SharedDirectSourceWarning:
    """A mechanically provable common direct source; not a sample-identity claim."""

    first_record: RecordRef
    second_record: RecordRef
    shared_source_records: tuple[RecordRef, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.first_record, RecordRef) or not isinstance(self.second_record, RecordRef):
            raise ValueError("warning records must be RecordRef values")
        sources = tuple(self.shared_source_records)
        if not sources or any(not isinstance(source, RecordRef) for source in sources):
            raise ValueError("shared_source_records must contain RecordRef values")
        object.__setattr__(self, "shared_source_records", sources)


@dataclass(frozen=True)
class CrossDatasetSelectionValidation:
    """Structured, immutable diagnostics suitable for a future selection GUI."""

    record_refs: tuple[RecordRef, ...]
    duplicate_refs: tuple[RecordRef, ...] = ()
    missing_datasets: tuple[RecordRef, ...] = ()
    unsupported_datasets: tuple[RecordRef, ...] = ()
    missing_records: tuple[RecordRef, ...] = ()
    output_id_collisions: Mapping[str, tuple[RecordRef, ...]] | None = None
    shared_direct_source_warnings: tuple[SharedDirectSourceWarning, ...] = ()
    existing_dataset_id: str | None = None

    def __post_init__(self) -> None:
        refs = tuple(self.record_refs)
        if any(not isinstance(record_ref, RecordRef) for record_ref in refs):
            raise ValueError("record_refs must contain RecordRef values")
        object.__setattr__(self, "record_refs", refs)
        for field_name in (
            "duplicate_refs",
            "missing_datasets",
            "unsupported_datasets",
            "missing_records",
        ):
            values = tuple(getattr(self, field_name))
            if any(not isinstance(record_ref, RecordRef) for record_ref in values):
                raise ValueError(f"{field_name} must contain RecordRef values")
            object.__setattr__(self, field_name, values)
        warnings = tuple(self.shared_direct_source_warnings)
        if any(not isinstance(warning, SharedDirectSourceWarning) for warning in warnings):
            raise ValueError("shared_direct_source_warnings must contain warning values")
        object.__setattr__(self, "shared_direct_source_warnings", warnings)
        collisions = dict(self.output_id_collisions or {})
        normalized_collisions: dict[str, tuple[RecordRef, ...]] = {}
        for sequence_id, collision_refs in collisions.items():
            if not isinstance(sequence_id, str) or not sequence_id:
                raise ValueError("output collision IDs must be non-empty strings")
            values = tuple(collision_refs)
            if len(values) < 2 or any(not isinstance(record_ref, RecordRef) for record_ref in values):
                raise ValueError("output collisions must contain at least two RecordRef values")
            normalized_collisions[sequence_id] = values
        object.__setattr__(self, "output_id_collisions", MappingProxyType(normalized_collisions))
        if self.existing_dataset_id is not None and (
            not isinstance(self.existing_dataset_id, str) or not self.existing_dataset_id
        ):
            raise ValueError("existing_dataset_id must be a non-empty string or None")

    @property
    def is_valid(self) -> bool:
        return bool(self.record_refs) and not any(
            (
                self.duplicate_refs,
                self.missing_datasets,
                self.unsupported_datasets,
                self.missing_records,
                self.output_id_collisions,
                self.existing_dataset_id,
            )
        )


class CrossDatasetSelectionError(ValueError):
    """A validation failure that retains structured diagnostics for callers."""

    def __init__(self, validation: CrossDatasetSelectionValidation) -> None:
        self.validation = validation
        super().__init__(_validation_message(validation))


@dataclass(frozen=True)
class CrossDatasetBuild:
    """The immutable output Dataset and its typed source relations."""

    dataset: SequenceDataset
    lineage_relations: tuple[LineageRelation, ...]
    validation: CrossDatasetSelectionValidation

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, SequenceDataset):
            raise ValueError("dataset must be a SequenceDataset")
        relations = tuple(self.lineage_relations)
        if not relations or any(not isinstance(relation, LineageRelation) for relation in relations):
            raise ValueError("lineage_relations must contain at least one LineageRelation")
        object.__setattr__(self, "lineage_relations", relations)
        if not isinstance(self.validation, CrossDatasetSelectionValidation):
            raise ValueError("validation must be a CrossDatasetSelectionValidation")


def validate_record_refs(
    project: Project,
    record_refs: tuple[RecordRef, ...] | list[RecordRef],
    *,
    dataset_id: str | None = None,
    output_record_ids: Mapping[RecordRef, str] | None = None,
) -> CrossDatasetSelectionValidation:
    """Resolve and diagnose a proposed cross-dataset record selection.

    Invalid references are reported without silent skipping.  Valid references
    retain caller order for a later build operation.
    """

    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    refs = tuple(record_refs)
    if any(not isinstance(record_ref, RecordRef) for record_ref in refs):
        raise ValueError("record_refs must contain RecordRef values")
    if dataset_id is not None and (not isinstance(dataset_id, str) or not dataset_id.strip()):
        raise ValueError("dataset_id must be a non-empty string or None")

    duplicate_refs = _duplicates(refs)
    missing_datasets: list[RecordRef] = []
    unsupported_datasets: list[RecordRef] = []
    missing_records: list[RecordRef] = []
    resolved: list[tuple[RecordRef, SequenceRecord]] = []
    for record_ref in refs:
        if not project.has_dataset(record_ref.dataset_id):
            missing_datasets.append(record_ref)
            continue
        source_dataset = project.get_dataset(record_ref.dataset_id)
        if not isinstance(source_dataset, SequenceDataset):
            unsupported_datasets.append(record_ref)
            continue
        try:
            record = source_dataset.get_record(record_ref.sequence_id)
        except KeyError:
            missing_records.append(record_ref)
            continue
        resolved.append((record_ref, record))

    resolved_output_ids = _normalize_output_record_ids(
        output_record_ids,
        selected_refs=refs,
    )
    output_id_collisions = _output_id_collisions(resolved, resolved_output_ids)
    return CrossDatasetSelectionValidation(
        record_refs=refs,
        duplicate_refs=duplicate_refs,
        missing_datasets=tuple(missing_datasets),
        unsupported_datasets=tuple(unsupported_datasets),
        missing_records=tuple(missing_records),
        output_id_collisions=output_id_collisions,
        shared_direct_source_warnings=_shared_direct_source_warnings(resolved),
        existing_dataset_id=(dataset_id if dataset_id is not None and project.has_dataset(dataset_id) else None),
    )


def build_dataset_from_record_refs(
    project: Project,
    record_refs: tuple[RecordRef, ...] | list[RecordRef],
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
    output_record_ids: Mapping[RecordRef, str] | None = None,
) -> CrossDatasetBuild:
    """Create a new immutable Dataset and typed Dataset-level provenance."""

    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise ValueError("dataset_id must be a non-empty string")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    user_metadata = _freeze_mapping(metadata)
    selected_refs = tuple(record_refs)
    resolved_output_ids = _normalize_output_record_ids(
        output_record_ids,
        selected_refs=selected_refs,
    )
    validation = validate_record_refs(
        project,
        selected_refs,
        dataset_id=dataset_id,
        output_record_ids=resolved_output_ids,
    )
    if not validation.is_valid:
        raise CrossDatasetSelectionError(validation)

    records = tuple(
        _copy_with_direct_provenance(
            project,
            record_ref,
            output_sequence_id=resolved_output_ids.get(record_ref),
        )
        for record_ref in validation.record_refs
    )
    source_dataset_ids = _ordered_unique(record_ref.dataset_id for record_ref in validation.record_refs)
    relation_type = (
        LineageRelationType.SUBSET_FROM_DATASET
        if len(source_dataset_ids) == 1
        else LineageRelationType.MERGED_FROM_DATASETS
    )
    relations = tuple(
        LineageRelation(
            source_kind=LineageSourceKind.DATASET,
            source_id=source_dataset_id,
            relation_type=relation_type,
            metadata={
                "selected_record_count": sum(
                    record_ref.dataset_id == source_dataset_id
                    for record_ref in validation.record_refs
                )
            },
        )
        for source_dataset_id in source_dataset_ids
    )
    dataset_metadata = dict(user_metadata)
    dataset_metadata.update(
        {
            "derived_from": "CROSS_DATASET_RECORD_SELECTION",
            "source_dataset_ids": source_dataset_ids,
            "selected_record_count": len(records),
        }
    )
    dataset = SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        # A cross-dataset selection has no single source type.  It is an
        # explicitly derived collection, independent of selection order.
        source_type=SourceType.DERIVED,
        records=records,
        metadata=dataset_metadata,
    )
    return CrossDatasetBuild(dataset, relations, validation)


def create_dataset_from_record_refs(
    project: Project,
    record_refs: tuple[RecordRef, ...] | list[RecordRef],
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
    output_record_ids: Mapping[RecordRef, str] | None = None,
) -> SequenceDataset:
    """Compatibility convenience API returning only the built Dataset."""

    return build_dataset_from_record_refs(
        project,
        record_refs,
        dataset_id=dataset_id,
        name=name,
        metadata=metadata,
        output_record_ids=output_record_ids,
    ).dataset


def _copy_with_direct_provenance(
    project: Project,
    record_ref: RecordRef,
    *,
    output_sequence_id: str | None = None,
) -> SequenceRecord:
    source_dataset = project.get_dataset(record_ref.dataset_id)
    assert isinstance(source_dataset, SequenceDataset)  # validated before build
    record = source_dataset.get_record(record_ref.sequence_id)
    sequence_id = output_sequence_id or record.sequence_id
    metadata = dict(record.metadata)
    if sequence_id != record.sequence_id:
        # This is an output-only presentation identifier.  The immutable
        # source record remains identified by RecordRef in provenance.
        metadata.setdefault("original_record_id", record.sequence_id)
    return SequenceRecord(
        sequence_id=sequence_id,
        sequence=record.sequence,
        description=record.description,
        source_reference=record.source_reference,
        metadata=metadata,
        provenance=RecordProvenance((record_ref,)),
    )


def _duplicates(values: tuple[RecordRef, ...]) -> tuple[RecordRef, ...]:
    seen: set[RecordRef] = set()
    duplicates: list[RecordRef] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return tuple(duplicates)


def _output_id_collisions(
    resolved: list[tuple[RecordRef, SequenceRecord]],
    output_record_ids: Mapping[RecordRef, str],
) -> Mapping[str, tuple[RecordRef, ...]]:
    by_id: dict[str, list[RecordRef]] = {}
    for record_ref, record in resolved:
        by_id.setdefault(output_record_ids.get(record_ref, record.sequence_id), []).append(record_ref)
    return {
        sequence_id: tuple(refs)
        for sequence_id, refs in by_id.items()
        if len(refs) > 1
    }


def _normalize_output_record_ids(
    value: Mapping[RecordRef, str] | None,
    *,
    selected_refs: tuple[RecordRef, ...],
) -> Mapping[RecordRef, str]:
    """Validate explicit output-only names without changing source identity."""

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("output_record_ids must be a mapping or None")
    selected = set(selected_refs)
    normalized: dict[RecordRef, str] = {}
    for record_ref, sequence_id in value.items():
        if not isinstance(record_ref, RecordRef):
            raise ValueError("output_record_ids keys must be RecordRef values")
        if record_ref not in selected:
            raise ValueError("output_record_ids may only name selected records")
        if not isinstance(sequence_id, str) or not sequence_id.strip():
            raise ValueError("output record IDs must be non-empty strings")
        normalized[record_ref] = sequence_id.strip()
    return MappingProxyType(normalized)


def _shared_direct_source_warnings(
    resolved: list[tuple[RecordRef, SequenceRecord]],
) -> tuple[SharedDirectSourceWarning, ...]:
    warnings: list[SharedDirectSourceWarning] = []
    for (first_ref, first_record), (second_ref, second_record) in combinations(resolved, 2):
        shared = tuple(
            source
            for source in first_record.provenance.source_records
            if source in second_record.provenance.source_records
        )
        if shared:
            warnings.append(SharedDirectSourceWarning(first_ref, second_ref, shared))
    return tuple(warnings)


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values:
        if value not in ordered:
            ordered.append(value)
    return tuple(ordered)


def _validation_message(validation: CrossDatasetSelectionValidation) -> str:
    if not validation.record_refs:
        return "record selection must not be empty"
    if validation.duplicate_refs:
        return f"duplicate RecordRef selection: {validation.duplicate_refs}"
    if validation.missing_datasets:
        return f"selected Dataset does not exist: {validation.missing_datasets}"
    if validation.unsupported_datasets:
        return f"selected Dataset is not a SequenceDataset: {validation.unsupported_datasets}"
    if validation.missing_records:
        return f"selected sequence_id does not exist: {validation.missing_records}"
    if validation.output_id_collisions:
        return f"output sequence_id collisions: {dict(validation.output_id_collisions)}"
    if validation.existing_dataset_id:
        return f"dataset_id already exists in project: {validation.existing_dataset_id}"
    return "invalid cross-dataset record selection"
