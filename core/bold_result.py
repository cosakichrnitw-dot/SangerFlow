"""Immutable in-memory BOLD barcode-identification result values.

This module only models results already obtained from a BOLD-compatible
source.  It has no network, GUI, filtering, or Project-registration behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or None")
    return value


def _optional_similarity(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("similarity must be a number between 0 and 100 or None")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 100.0:
        raise ValueError("similarity must be between 0 and 100")
    return normalized


@dataclass(frozen=True)
class BoldHit:
    """One BOLD reference hit with optional taxonomy and specimen context."""

    query_id: str
    process_id: str | None = None
    record_id: str | None = None
    species_name: str | None = None
    genus: str | None = None
    family: str | None = None
    order: str | None = None
    phylum: str | None = None
    bin_uri: str | None = None
    similarity: float | None = None
    database: str = ""
    country: str | None = None
    institution: str | None = None
    specimen_id: str | None = None
    collection_date: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.query_id, "query_id")
        _required_text(self.database, "database")
        for field_name in (
            "process_id",
            "record_id",
            "species_name",
            "genus",
            "family",
            "order",
            "phylum",
            "bin_uri",
            "country",
            "institution",
            "specimen_id",
            "collection_date",
        ):
            object.__setattr__(self, field_name, _optional_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "similarity", _optional_similarity(self.similarity))

    @property
    def identity_key(self) -> tuple[str, str | None, str | None]:
        """Stable per-query key used to reject duplicate BOLD reference hits."""

        return (self.query_id, self.process_id, self.record_id)


@dataclass(frozen=True)
class BoldResultDataset:
    """Ordered BOLD hits for one parent sequence dataset."""

    result_id: str
    name: str
    parent_dataset_id: str
    marker: str | None
    database: str
    hits: tuple[BoldHit, ...]
    metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _required_text(self.result_id, "result_id")
        _required_text(self.name, "name")
        _required_text(self.parent_dataset_id, "parent_dataset_id")
        if self.marker is not None:
            _optional_text(self.marker, "marker")
        _required_text(self.database, "database")
        hits = tuple(self.hits)
        if any(not isinstance(hit, BoldHit) for hit in hits):
            raise ValueError("hits must contain only BoldHit values")
        identity_keys = tuple(hit.identity_key for hit in hits)
        if len(set(identity_keys)) != len(identity_keys):
            raise ValueError("duplicate BOLD hit IDs are not allowed for the same query")
        object.__setattr__(self, "hits", hits)
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    def query_ids(self) -> tuple[str, ...]:
        """Return query IDs once each in first-hit order."""

        return tuple(dict.fromkeys(hit.query_id for hit in self.hits))

    def hit_count(self) -> int:
        return len(self.hits)

    def get_hits(self, query_id: str) -> tuple[BoldHit, ...]:
        """Return ordered BOLD hits for a query; unknown queries yield empty."""

        return tuple(hit for hit in self.hits if hit.query_id == query_id)

    @property
    def analysis_result(self) -> AnalysisResult:
        """Expose common immutable result lineage without duplicating BOLD hits."""

        return AnalysisResult(
            result_id=self.result_id,
            name=self.name,
            result_type=AnalysisResultType.BOLD,
            parent_dataset_id=self.parent_dataset_id,
            metadata=self.metadata,
        )
