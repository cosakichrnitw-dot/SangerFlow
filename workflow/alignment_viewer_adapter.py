"""Adapt an immutable alignment dataset to the legacy Alignment Viewer shape.

No GUI module is imported.  The returned input is iterable over records that
provide the existing viewer's ``record.id`` and ``record.seq`` attributes.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

from core.sequence_dataset import SequenceDataset, SourceType


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    return MappingProxyType(dict(value))


@dataclass(frozen=True)
class AlignmentViewerRecord:
    """One viewer-compatible immutable alignment row."""

    sequence_id: str
    sequence: str
    metadata: Mapping[str, object] | None = None
    source_reference: object | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def id(self) -> str:
        """Legacy ``AlignmentSequenceWindow`` record identifier interface."""

        return self.sequence_id

    @property
    def seq(self) -> str:
        """Legacy ``AlignmentSequenceWindow`` sequence interface."""

        return self.sequence


@dataclass(frozen=True)
class AlignmentViewerInput:
    """Iterable, immutable alignment payload for the existing sequence viewer."""

    records: tuple[AlignmentViewerRecord, ...]
    alignment_length: int
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not self.records:
            raise ValueError("AlignmentViewerInput requires at least one record")
        if any(len(record.sequence) != self.alignment_length for record in self.records):
            raise ValueError("viewer records must all have alignment_length")
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def __iter__(self) -> Iterable[AlignmentViewerRecord]:
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)


def create_alignment_viewer_input(
    alignment_dataset: SequenceDataset,
    *,
    metadata: Mapping[str, object] | None = None,
) -> AlignmentViewerInput:
    """Validate a gapped alignment dataset and create legacy-viewer input."""

    if not isinstance(alignment_dataset, SequenceDataset):
        raise ValueError("alignment_dataset must be a SequenceDataset")
    if alignment_dataset.source_type is not SourceType.IMPORTED_ALIGNMENT:
        raise ValueError("alignment_dataset must have SourceType.IMPORTED_ALIGNMENT")
    if alignment_dataset.sequence_count < 1:
        raise ValueError("alignment_dataset must contain at least one sequence")
    if not alignment_dataset.is_equal_length:
        raise ValueError("alignment_dataset sequences must have equal length")
    if not alignment_dataset.has_gaps:
        raise ValueError("alignment_dataset must contain at least one gap")

    combined_metadata = dict(alignment_dataset.metadata)
    if metadata is not None:
        if not isinstance(metadata, Mapping):
            raise ValueError("metadata must be a mapping")
        combined_metadata.update(metadata)
    return AlignmentViewerInput(
        records=tuple(
            AlignmentViewerRecord(
                sequence_id=record.sequence_id,
                sequence=record.sequence,
                metadata=record.metadata,
                source_reference=record.source_reference,
            )
            for record in alignment_dataset.records
        ),
        alignment_length=alignment_dataset.minimum_length,
        metadata=combined_metadata,
    )
