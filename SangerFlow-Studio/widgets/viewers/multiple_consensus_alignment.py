"""Temporary MAFFT alignment mapping for the Studio multiple-review workspace.

This module is deliberately display-only.  It maps the output columns already
created by MAFFT back to an unchanged per-sample consensus position, then uses
the existing ``SingleConsensusViewModel`` / ``ReviewEvidence`` as the sole
source of F/R evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol

from core.sequence_dataset import SequenceDataset


class _ConsensusRow(Protocol):
    sample_id: str
    view_model: object


@dataclass(frozen=True)
class TemporaryAlignmentRow:
    """One MAFFT-aligned consensus row and its explicit coordinate table."""

    sample_id: str
    aligned_sequence: str
    consensus_positions: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(self.aligned_sequence, str) or not self.aligned_sequence:
            raise ValueError("aligned_sequence must be a non-empty string")
        positions = tuple(self.consensus_positions)
        if len(positions) != len(self.aligned_sequence):
            raise ValueError("consensus_positions must match aligned_sequence length")
        expected_position = 0
        for base, position in zip(self.aligned_sequence, positions):
            if base == "-":
                if position is not None:
                    raise ValueError("a MAFFT gap cannot have a consensus position")
                continue
            if position != expected_position:
                raise ValueError("non-gap MAFFT columns must map contiguously to consensus positions")
            expected_position += 1
        object.__setattr__(self, "consensus_positions", positions)

    def consensus_position_for_column(self, column: int) -> int | None:
        if not 0 <= int(column) < len(self.consensus_positions):
            return None
        return self.consensus_positions[int(column)]

    def column_for_consensus_position(self, position: int) -> int | None:
        for column, mapped_position in enumerate(self.consensus_positions):
            if mapped_position == int(position):
                return column
        return None


@dataclass(frozen=True)
class TemporaryConsensusAlignment:
    """Session-only MAFFT rows; never a Project dataset by itself."""

    rows: Mapping[str, TemporaryAlignmentRow]

    def __post_init__(self) -> None:
        rows = dict(self.rows)
        if len(rows) < 2:
            raise ValueError("temporary alignment requires at least two samples")
        if any(key != row.sample_id for key, row in rows.items()):
            raise ValueError("temporary alignment row keys must match sample IDs")
        lengths = {len(row.aligned_sequence) for row in rows.values()}
        if len(lengths) != 1:
            raise ValueError("temporary alignment rows must have the same length")
        object.__setattr__(self, "rows", MappingProxyType(rows))

    @property
    def length(self) -> int:
        return len(next(iter(self.rows.values())).aligned_sequence)

    def row_for(self, sample_id: str) -> TemporaryAlignmentRow:
        return self.rows[sample_id]

    @classmethod
    def from_mafft_dataset(
        cls,
        aligned_dataset: SequenceDataset,
        consensus_sequences: Mapping[str, str],
    ) -> "TemporaryConsensusAlignment":
        """Build a non-scientific MAFFT-column mapping from existing output."""

        if not isinstance(aligned_dataset, SequenceDataset):
            raise ValueError("aligned_dataset must be a SequenceDataset")
        source_sequences = dict(consensus_sequences)
        if len(source_sequences) < 2:
            raise ValueError("at least two source consensus sequences are required")
        aligned_by_id = {record.sequence_id: record.sequence for record in aligned_dataset.records}
        if set(aligned_by_id) != set(source_sequences):
            raise ValueError("MAFFT output sample IDs must match the selected consensus samples")

        rows: dict[str, TemporaryAlignmentRow] = {}
        for sample_id, source_sequence in source_sequences.items():
            aligned_sequence = aligned_by_id[sample_id]
            positions: list[int | None] = []
            position = 0
            for base in aligned_sequence:
                if base == "-":
                    positions.append(None)
                else:
                    positions.append(position)
                    position += 1
            if position != len(source_sequence):
                raise ValueError(
                    f"MAFFT non-gap length does not match consensus for sample {sample_id}"
                )
            rows[sample_id] = TemporaryAlignmentRow(
                sample_id=sample_id,
                aligned_sequence=aligned_sequence,
                consensus_positions=tuple(positions),
            )
        return cls(rows=rows)
