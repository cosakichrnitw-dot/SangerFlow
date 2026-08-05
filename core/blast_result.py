"""Immutable in-memory BLAST result values for future Project management.

This module models already-obtained results only.  It performs no NCBI or
BLAST+ communication and has no GUI dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from core.analysis_result import AnalysisResult, AnalysisResultType


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


def _percentage(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number between 0 and 100")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 100.0:
        raise ValueError(f"{field_name} must be between 0 and 100")
    return normalized


class BlastAnalysisMode(str, Enum):
    """Purpose of an already-obtained BLAST result collection."""

    QC = "QC"
    IDENTIFICATION = "IDENTIFICATION"


@dataclass(frozen=True)
class BlastHit:
    """One validated hit for one query sequence."""

    query_id: str
    hit_accession: str
    scientific_name: str
    organism: str
    identity: float
    query_coverage: float
    evalue: float
    alignment_length: int
    database: str

    def __post_init__(self) -> None:
        _required_text(self.query_id, "query_id")
        _required_text(self.hit_accession, "hit_accession")
        _required_text(self.scientific_name, "scientific_name")
        _required_text(self.organism, "organism")
        _required_text(self.database, "database")
        object.__setattr__(self, "identity", _percentage(self.identity, "identity"))
        object.__setattr__(self, "query_coverage", _percentage(self.query_coverage, "query_coverage"))
        if isinstance(self.evalue, bool) or not isinstance(self.evalue, (int, float)):
            raise ValueError("evalue must be a non-negative number")
        normalized_evalue = float(self.evalue)
        if not isfinite(normalized_evalue) or normalized_evalue < 0.0:
            raise ValueError("evalue must be a non-negative number")
        if isinstance(self.alignment_length, bool) or not isinstance(self.alignment_length, int):
            raise ValueError("alignment_length must be a positive integer")
        if self.alignment_length <= 0:
            raise ValueError("alignment_length must be a positive integer")
        object.__setattr__(self, "evalue", normalized_evalue)


@dataclass(frozen=True)
class BlastResultDataset:
    """Ordered hits from one BLAST analysis of one parent sequence dataset."""

    result_id: str
    name: str
    hits: tuple[BlastHit, ...]
    parent_dataset_id: str
    metadata: Mapping[str, object] | None = None
    analysis_mode: BlastAnalysisMode = BlastAnalysisMode.IDENTIFICATION
    marker: str | None = None
    database: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.result_id, "result_id")
        _required_text(self.name, "name")
        _required_text(self.parent_dataset_id, "parent_dataset_id")
        if not isinstance(self.analysis_mode, BlastAnalysisMode):
            raise ValueError("analysis_mode must be a BlastAnalysisMode")
        if self.marker is not None:
            _required_text(self.marker, "marker")
        if self.database is not None:
            _required_text(self.database, "database")
        hits = tuple(self.hits)
        if any(not isinstance(hit, BlastHit) for hit in hits):
            raise ValueError("hits must contain only BlastHit values")
        object.__setattr__(self, "hits", hits)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def query_ids(self) -> tuple[str, ...]:
        """Return query IDs once each, in first-hit order."""

        return tuple(dict.fromkeys(hit.query_id for hit in self.hits))

    def hit_count(self) -> int:
        return len(self.hits)

    def get_hits(self, query_id: str) -> tuple[BlastHit, ...]:
        """Return ordered hits for a query; unknown queries yield an empty tuple."""

        return tuple(hit for hit in self.hits if hit.query_id == query_id)

    @property
    def analysis_result(self) -> AnalysisResult:
        """Expose this BLAST payload through the common result abstraction.

        The existing BLAST-specific model remains the owner of hits and BLAST
        metadata.  This adapter value provides the shared result identity and
        input-dataset lineage expected by future project result management.
        """

        return AnalysisResult(
            result_id=self.result_id,
            name=self.name,
            result_type=AnalysisResultType.BLAST,
            parent_dataset_id=self.parent_dataset_id,
            metadata=self.metadata,
        )
