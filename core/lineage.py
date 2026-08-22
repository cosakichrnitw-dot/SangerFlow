"""Immutable Project provenance primitives shared by datasets and Projects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class LineageSourceKind(str, Enum):
    """The Project object type used as a provenance source."""

    DATASET = "DATASET"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"


class LineageRelationType(str, Enum):
    """The documented operation that connected a source to its target."""

    SUBSET_FROM_DATASET = "SUBSET_FROM_DATASET"
    MERGED_FROM_DATASETS = "MERGED_FROM_DATASETS"
    ALIGNMENT_FROM_DATASET = "ALIGNMENT_FROM_DATASET"
    CONSENSUS_FROM_READS = "CONSENSUS_FROM_READS"
    REVIEWED_FROM_CONSENSUS = "REVIEWED_FROM_CONSENSUS"
    METADATA_MERGE = "METADATA_MERGE"
    SELECTED_FROM_BLAST = "SELECTED_FROM_BLAST"
    SELECTED_FROM_BOLD = "SELECTED_FROM_BOLD"
    LEGACY_PARENT_DATASET = "LEGACY_PARENT_DATASET"


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class LineageRelation:
    """One typed, immutable source edge for a Project dataset."""

    source_kind: LineageSourceKind
    source_id: str
    relation_type: LineageRelationType
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, LineageSourceKind):
            raise ValueError("source_kind must be a LineageSourceKind")
        _required_text(self.source_id, "source_id")
        if not isinstance(self.relation_type, LineageRelationType):
            raise ValueError("relation_type must be a LineageRelationType")
        if self.source_kind is LineageSourceKind.DATASET and self.relation_type in {
            LineageRelationType.SELECTED_FROM_BLAST,
            LineageRelationType.SELECTED_FROM_BOLD,
        }:
            raise ValueError("BLAST/BOLD selection relations require an ANALYSIS_RESULT source")
        if self.source_kind is LineageSourceKind.ANALYSIS_RESULT and self.relation_type not in {
            LineageRelationType.SELECTED_FROM_BLAST,
            LineageRelationType.SELECTED_FROM_BOLD,
        }:
            raise ValueError("ANALYSIS_RESULT sources require a BLAST or BOLD selection relation")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def identity(self) -> tuple[LineageSourceKind, str, LineageRelationType]:
        """Stable edge identity; metadata does not create a second edge."""

        return (self.source_kind, self.source_id, self.relation_type)


@dataclass(frozen=True)
class RecordRef:
    """Project-local identity of one record without relying on file paths."""

    dataset_id: str
    sequence_id: str

    def __post_init__(self) -> None:
        _required_text(self.dataset_id, "dataset_id")
        _required_text(self.sequence_id, "sequence_id")


@dataclass(frozen=True)
class RecordProvenance:
    """Direct source records from which an output record was derived."""

    source_records: tuple[RecordRef, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.source_records)
        if any(not isinstance(record, RecordRef) for record in records):
            raise ValueError("source_records must contain only RecordRef values")
        if len(set(records)) != len(records):
            raise ValueError("source_records must not contain duplicates")
        object.__setattr__(self, "source_records", records)
