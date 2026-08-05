"""Immutable query selection criteria for already-obtained BLAST results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from core.blast_result import BlastHit, BlastResultDataset


def _freeze_metadata(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ValueError("filter_metadata must be a mapping")
    return MappingProxyType(dict(value))


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or None")
    return value


def _optional_percentage(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number between 0 and 100 or None")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 100.0:
        raise ValueError(f"{field_name} must be between 0 and 100")
    return normalized


def _optional_evalue(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("max_evalue must be a non-negative number or None")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0.0:
        raise ValueError("max_evalue must be a non-negative number")
    return normalized


@dataclass(frozen=True)
class BlastResultFilter:
    """Criteria used to select query IDs from an immutable BLAST result.

    With ``top_hit_only=True`` (the default), all criteria apply to each
    query's first stored hit.  Setting it to ``False`` opts into the future-
    compatible policy of accepting a query when any one of its hits satisfies
    every configured criterion.
    """

    scientific_name: str | None = None
    organism: str | None = None
    min_identity: float | None = None
    min_coverage: float | None = None
    max_evalue: float | None = None
    top_hit_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "scientific_name", _optional_text(self.scientific_name, "scientific_name"))
        object.__setattr__(self, "organism", _optional_text(self.organism, "organism"))
        object.__setattr__(self, "min_identity", _optional_percentage(self.min_identity, "min_identity"))
        object.__setattr__(self, "min_coverage", _optional_percentage(self.min_coverage, "min_coverage"))
        object.__setattr__(self, "max_evalue", _optional_evalue(self.max_evalue))
        if not isinstance(self.top_hit_only, bool):
            raise ValueError("top_hit_only must be a bool")

    def metadata(self) -> Mapping[str, object]:
        """Return a read-only snapshot suitable for a selection record."""

        return MappingProxyType(
            {
                "scientific_name": self.scientific_name,
                "organism": self.organism,
                "min_identity": self.min_identity,
                "min_coverage": self.min_coverage,
                "max_evalue": self.max_evalue,
                "top_hit_only": self.top_hit_only,
            }
        )


@dataclass(frozen=True)
class BlastResultSelection:
    """A query-ID selection derived from one immutable BLAST result dataset."""

    source_result_id: str
    selected_query_ids: tuple[str, ...]
    filter_metadata: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_result_id, str) or not self.source_result_id.strip():
            raise ValueError("source_result_id must be a non-empty string")
        selected_query_ids = tuple(self.selected_query_ids)
        if any(not isinstance(query_id, str) or not query_id.strip() for query_id in selected_query_ids):
            raise ValueError("selected_query_ids must contain only non-empty strings")
        if len(set(selected_query_ids)) != len(selected_query_ids):
            raise ValueError("selected_query_ids must not contain duplicates")
        object.__setattr__(self, "selected_query_ids", selected_query_ids)
        object.__setattr__(self, "filter_metadata", _freeze_metadata(self.filter_metadata))


def apply_blast_filter(
    blast_result: BlastResultDataset,
    criteria: BlastResultFilter,
) -> BlastResultSelection:
    """Return selected query IDs in the source result's first-hit order."""

    if not isinstance(blast_result, BlastResultDataset):
        raise ValueError("blast_result must be a BlastResultDataset")
    if not blast_result.hits:
        raise ValueError("blast_result must contain at least one hit to filter")
    if not isinstance(criteria, BlastResultFilter):
        raise ValueError("criteria must be a BlastResultFilter")

    selected_query_ids = tuple(
        query_id
        for query_id in blast_result.query_ids()
        if _query_matches(blast_result.get_hits(query_id), criteria)
    )
    return BlastResultSelection(
        source_result_id=blast_result.result_id,
        selected_query_ids=selected_query_ids,
        filter_metadata=criteria.metadata(),
    )


def _query_matches(hits: tuple[BlastHit, ...], criteria: BlastResultFilter) -> bool:
    candidate_hits = hits[:1] if criteria.top_hit_only else hits
    return any(_hit_matches(hit, criteria) for hit in candidate_hits)


def _hit_matches(hit: BlastHit, criteria: BlastResultFilter) -> bool:
    if criteria.scientific_name is not None and hit.scientific_name != criteria.scientific_name:
        return False
    if criteria.organism is not None and criteria.organism.casefold() not in hit.organism.casefold():
        return False
    if criteria.min_identity is not None and hit.identity < criteria.min_identity:
        return False
    if criteria.min_coverage is not None and hit.query_coverage < criteria.min_coverage:
        return False
    if criteria.max_evalue is not None and hit.evalue > criteria.max_evalue:
        return False
    return True
