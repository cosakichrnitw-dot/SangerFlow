"""Immutable, GUI-independent sequence dataset value objects.

This module is deliberately limited to in-memory validation and grouping of
sequence values.  It does not read files, run aligners, or modify the source
objects referenced by records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping


_VALID_SEQUENCE_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")


class SourceType(str, Enum):
    """Origin category for the sequence values held by a dataset."""

    AB1_RAW = "AB1_RAW"
    AB1_TRIMMED = "AB1_TRIMMED"
    CONSENSUS_CANDIDATE = "CONSENSUS_CANDIDATE"
    REVIEWED_CONSENSUS = "REVIEWED_CONSENSUS"
    IMPORTED_FASTA = "IMPORTED_FASTA"
    IMPORTED_ALIGNMENT = "IMPORTED_ALIGNMENT"


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    """Copy metadata into a read-only mapping owned by the value object."""

    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class SequenceRecord:
    """One validated DNA/IUPAC sequence with an optional opaque source link."""

    sequence_id: str
    sequence: str
    description: str | None = None
    source_reference: object | None = None
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.sequence_id, str) or not self.sequence_id.strip():
            raise ValueError("sequence_id must be a non-empty string")
        if not isinstance(self.sequence, str):
            raise ValueError("sequence must be a string")

        normalized_sequence = self.sequence.upper()
        if not normalized_sequence:
            raise ValueError("sequence must not be empty")

        invalid_symbols = set(normalized_sequence) - _VALID_SEQUENCE_SYMBOLS
        if invalid_symbols:
            raise ValueError(
                "sequence contains invalid DNA/IUPAC symbols: "
                f"{sorted(invalid_symbols)}"
            )

        if self.description is not None and not isinstance(self.description, str):
            raise ValueError("description must be a string or None")

        object.__setattr__(self, "sequence", normalized_sequence)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class SequenceDataset:
    """An ordered, immutable, non-empty collection of ``SequenceRecord`` values.

    Empty datasets are intentionally rejected in this first prototype.  A
    dataset represents an analysis-ready input collection; callers with no
    accepted sequences should not silently continue as if a dataset existed.
    """

    dataset_id: str
    name: str
    source_type: SourceType
    records: tuple[SequenceRecord, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a non-empty string")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be a SourceType")

        records = tuple(self.records)
        if not records:
            raise ValueError("SequenceDataset must contain at least one record")
        if any(not isinstance(record, SequenceRecord) for record in records):
            raise ValueError("records must contain only SequenceRecord values")

        object.__setattr__(self, "records", records)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))
        self.validate_unique_ids()

    @property
    def sequence_count(self) -> int:
        return len(self.records)

    @property
    def sequence_ids(self) -> tuple[str, ...]:
        return tuple(record.sequence_id for record in self.records)

    @property
    def lengths(self) -> tuple[int, ...]:
        return tuple(len(record.sequence) for record in self.records)

    @property
    def minimum_length(self) -> int:
        return min(self.lengths)

    @property
    def maximum_length(self) -> int:
        return max(self.lengths)

    @property
    def has_gaps(self) -> bool:
        return any("-" in record.sequence for record in self.records)

    @property
    def is_equal_length(self) -> bool:
        return len(set(self.lengths)) == 1

    def validate_unique_ids(self) -> None:
        if len(set(self.sequence_ids)) != self.sequence_count:
            raise ValueError("duplicate sequence_id values are not allowed")

    def get_record(self, sequence_id: str) -> SequenceRecord:
        for record in self.records:
            if record.sequence_id == sequence_id:
                return record
        raise KeyError(sequence_id)

    def selected_records(self, sequence_ids: Iterable[str]) -> "SequenceDataset":
        """Return a new dataset in exactly the caller's requested ID order."""

        selected = tuple(self.get_record(sequence_id) for sequence_id in sequence_ids)
        return SequenceDataset(
            dataset_id=self.dataset_id,
            name=self.name,
            source_type=self.source_type,
            records=selected,
            metadata=self.metadata,
        )

    @classmethod
    def from_sequence_pairs(
        cls,
        dataset_id: str,
        name: str,
        source_type: SourceType,
        sequences: Iterable[tuple[str, str]],
    ) -> "SequenceDataset":
        """Build a dataset from ordered ``(sequence_id, sequence)`` pairs."""

        records = tuple(
            SequenceRecord(sequence_id=sequence_id, sequence=sequence)
            for sequence_id, sequence in sequences
        )
        return cls(
            dataset_id=dataset_id,
            name=name,
            source_type=source_type,
            records=records,
        )
