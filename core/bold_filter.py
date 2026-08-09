"""Immutable query-selection criteria for already-obtained BOLD results."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping

from core.bold_result import BoldHit, BoldResultDataset


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


def _optional_similarity(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("min_similarity must be a number between 0 and 100 or None")
    normalized = float(value)
    if not isfinite(normalized) or not 0.0 <= normalized <= 100.0:
        raise ValueError("min_similarity must be between 0 and 100")
    return normalized


@dataclass(frozen=True)
class BoldResultFilter:
    """Criteria used to select query IDs from immutable BOLD results.

    The default ``top_hit_only=True`` evaluates each query's first stored BOLD
    hit.  With ``False``, a query is selected when any stored hit satisfies all
    configured criteria, preserving a future-compatible policy boundary.
    """

    species_name: str | None = None
    genus: str | None = None
    family: str | None = None
    bin_uri: str | None = None
    country: str | None = None
    min_similarity: float | None = None
    top_hit_only: bool = True

    def __post_init__(self) -> None:
        for field_name in ("species_name", "genus", "family", "bin_uri", "country"):
            object.__setattr__(self, field_name, _optional_text(getattr(self, field_name), field_name))
        object.__setattr__(self, "min_similarity", _optional_similarity(self.min_similarity))
        if not isinstance(self.top_hit_only, bool):
            raise ValueError("top_hit_only must be a bool")

    def metadata(self) -> Mapping[str, object]:
        """Return a read-only criteria snapshot for a selection result."""

        return MappingProxyType(
            {
                "species_name": self.species_name,
                "genus": self.genus,
                "family": self.family,
                "bin_uri": self.bin_uri,
                "country": self.country,
                "min_similarity": self.min_similarity,
                "top_hit_only": self.top_hit_only,
            }
        )


@dataclass(frozen=True)
class BoldResultSelection:
    """Query IDs selected from one immutable BOLD result dataset."""

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


def apply_bold_filter(
    bold_result: BoldResultDataset,
    criteria: BoldResultFilter,
) -> BoldResultSelection:
    """Return query IDs matching BOLD criteria in source query order."""

    if not isinstance(bold_result, BoldResultDataset):
        raise ValueError("bold_result must be a BoldResultDataset")
    if not bold_result.hits:
        raise ValueError("bold_result must contain at least one hit to filter")
    if not isinstance(criteria, BoldResultFilter):
        raise ValueError("criteria must be a BoldResultFilter")

    selected_query_ids = tuple(
        query_id
        for query_id in bold_result.query_ids()
        if _query_matches(bold_result.get_hits(query_id), criteria)
    )
    return BoldResultSelection(
        source_result_id=bold_result.result_id,
        selected_query_ids=selected_query_ids,
        filter_metadata=criteria.metadata(),
    )


def _query_matches(hits: tuple[BoldHit, ...], criteria: BoldResultFilter) -> bool:
    candidate_hits = hits[:1] if criteria.top_hit_only else hits
    return any(_hit_matches(hit, criteria) for hit in candidate_hits)


def _hit_matches(hit: BoldHit, criteria: BoldResultFilter) -> bool:
    if criteria.species_name is not None and hit.species_name != criteria.species_name:
        return False
    if criteria.genus is not None and hit.genus != criteria.genus:
        return False
    if criteria.family is not None and hit.family != criteria.family:
        return False
    if criteria.bin_uri is not None and hit.bin_uri != criteria.bin_uri:
        return False
    if criteria.country is not None:
        if hit.country is None or criteria.country.casefold() not in hit.country.casefold():
            return False
    if criteria.min_similarity is not None:
        if hit.similarity is None or hit.similarity < criteria.min_similarity:
            return False
    return True
