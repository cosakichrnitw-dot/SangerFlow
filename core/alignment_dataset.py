"""Immutable models for already aligned sequence datasets.

Unlike :mod:`core.sequence_dataset`, these values represent a shared alignment
coordinate system.  They retain source-record lineage without changing the
unaligned parent dataset or generating an alignment themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from core.sequence_dataset import SequenceDataset


_VALID_ALIGNMENT_SYMBOLS = frozenset("ACGTNRYSWKMBDHV-")


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True)
class AlignmentRecord:
    """One aligned sequence and its source record identity."""

    record_id: str
    source_record_id: str
    aligned_sequence: str
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _required_text(self.record_id, "record_id")
        _required_text(self.source_record_id, "source_record_id")
        if not isinstance(self.aligned_sequence, str) or not self.aligned_sequence:
            raise ValueError("aligned_sequence must be a non-empty string")
        sequence = self.aligned_sequence.upper()
        invalid_symbols = set(sequence) - _VALID_ALIGNMENT_SYMBOLS
        if invalid_symbols:
            raise ValueError(
                "aligned_sequence contains invalid DNA/IUPAC symbols: "
                f"{sorted(invalid_symbols)}"
            )
        object.__setattr__(self, "aligned_sequence", sequence)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))


@dataclass(frozen=True)
class MarkerRegion:
    """A named 1-based inclusive interval in alignment-column coordinates."""

    name: str
    start: int
    end: int

    def __post_init__(self) -> None:
        _required_text(self.name, "marker region name")
        if (
            not isinstance(self.start, int)
            or isinstance(self.start, bool)
            or not isinstance(self.end, int)
            or isinstance(self.end, bool)
        ):
            raise ValueError("marker region start and end must be integers")
        if self.start < 1 or self.end < self.start:
            raise ValueError("marker region must use a valid 1-based inclusive range")


@dataclass(frozen=True)
class AlignmentDataset:
    """An immutable collection of sequences sharing one alignment length.

    ``parent_dataset_id`` records the original unaligned dataset identity.
    Use :meth:`from_sequence_dataset` when source-record existence needs to be
    validated against an in-memory ``SequenceDataset`` at construction time.
    """

    alignment_id: str
    name: str
    parent_dataset_id: str
    records: tuple[AlignmentRecord, ...]
    marker_regions: tuple[MarkerRegion, ...] = ()
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _required_text(self.alignment_id, "alignment_id")
        _required_text(self.name, "name")
        _required_text(self.parent_dataset_id, "parent_dataset_id")
        records = tuple(self.records)
        if not records:
            raise ValueError("AlignmentDataset must contain at least one AlignmentRecord")
        if any(not isinstance(record, AlignmentRecord) for record in records):
            raise ValueError("records must contain only AlignmentRecord values")
        record_ids = tuple(record.record_id for record in records)
        if len(set(record_ids)) != len(record_ids):
            raise ValueError("duplicate alignment record_id values are not allowed")
        lengths = {len(record.aligned_sequence) for record in records}
        if len(lengths) != 1:
            raise ValueError("all aligned_sequence values must have the same alignment length")

        marker_regions = tuple(_coerce_marker_region(region) for region in self.marker_regions)
        region_names = tuple(region.name for region in marker_regions)
        if len(set(region_names)) != len(region_names):
            raise ValueError("marker region names must be unique")
        alignment_length = next(iter(lengths))
        for region in marker_regions:
            if region.end > alignment_length:
                raise ValueError("marker region end is outside alignment length")

        object.__setattr__(self, "records", records)
        object.__setattr__(self, "marker_regions", marker_regions)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def length(self) -> int:
        """The common number of alignment columns, including gap columns."""
        return len(self.records[0].aligned_sequence)

    @property
    def sequence_count(self) -> int:
        return len(self.records)

    def record_ids(self) -> tuple[str, ...]:
        return tuple(record.record_id for record in self.records)

    def get_record(self, record_id: str) -> AlignmentRecord:
        for record in self.records:
            if record.record_id == record_id:
                return record
        raise KeyError(record_id)

    @classmethod
    def from_sequence_dataset(
        cls,
        *,
        alignment_id: str,
        name: str,
        parent_dataset: SequenceDataset,
        records: Iterable[AlignmentRecord],
        marker_regions: Iterable[MarkerRegion] = (),
        metadata: Mapping[str, object] | None = None,
    ) -> "AlignmentDataset":
        """Build an AlignmentDataset after validating source-record lineage.

        The parent dataset is only consulted for ID validation.  It is not
        copied, stored, or mutated; the resulting model keeps its dataset ID.
        """
        if not isinstance(parent_dataset, SequenceDataset):
            raise ValueError("parent_dataset must be a SequenceDataset")
        record_values = tuple(records)
        known_source_ids = set(parent_dataset.sequence_ids)
        missing_source_ids = sorted(
            {
                record.source_record_id
                for record in record_values
                if isinstance(record, AlignmentRecord)
                and record.source_record_id not in known_source_ids
            }
        )
        if missing_source_ids:
            raise ValueError(
                "source_record_id does not exist in parent_dataset: "
                + ", ".join(missing_source_ids)
            )
        return cls(
            alignment_id=alignment_id,
            name=name,
            parent_dataset_id=parent_dataset.dataset_id,
            records=record_values,
            marker_regions=tuple(marker_regions),
            metadata=metadata,
        )


def _coerce_marker_region(value: object) -> MarkerRegion:
    """Accept immutable MarkerRegion values or simple JSON-like declarations."""
    if isinstance(value, MarkerRegion):
        return value
    if isinstance(value, Mapping):
        try:
            return MarkerRegion(
                name=value["name"],
                start=value["start"],
                end=value["end"],
            )
        except KeyError as error:
            raise ValueError("marker region mapping requires name, start, and end") from error
    raise ValueError("marker_regions must contain MarkerRegion values or mappings")
