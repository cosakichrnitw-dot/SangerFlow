"""SequenceDataset-to-BOLD result workflow adapter.

The adapter is intentionally runner-injected: no BOLD API communication is
implemented here.  It converts caller-supplied raw hit mappings into immutable
``BoldResultDataset`` values while preserving input sequence order.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Callable

from core.bold_result import BoldHit, BoldResultDataset
from core.sequence_dataset import SequenceDataset


class BoldWorkflowError(ValueError):
    """A safe failure at the BOLD workflow boundary."""


BoldRunner = Callable[[str], Mapping[str, object] | Iterable[Mapping[str, object]]]


def run_bold_workflow(
    dataset: SequenceDataset,
    *,
    marker: str | None = None,
    database: str = "BOLD",
    runner: BoldRunner | None = None,
) -> BoldResultDataset:
    """Run an injected BOLD runner for each source record and build results."""

    if not isinstance(dataset, SequenceDataset):
        raise BoldWorkflowError("dataset must be a SequenceDataset")
    if not dataset.records:
        raise BoldWorkflowError("dataset must contain at least one sequence record")
    _required_text(database, "database")
    if marker is not None:
        _required_text(marker, "marker")
    if runner is None:
        raise BoldWorkflowError(
            "BOLD runner is not configured; BOLD API communication is not implemented"
        )
    if not callable(runner):
        raise BoldWorkflowError("runner must be callable or None")

    hits: list[BoldHit] = []
    for record in dataset.records:
        raw_result = runner(record.sequence)
        for raw_hit in _normalise_raw_hits(raw_result):
            hits.append(_bold_hit_from_raw(record.sequence_id, raw_hit, database))

    if not hits:
        raise BoldWorkflowError("BOLD workflow returned no hits")

    return BoldResultDataset(
        result_id=f"{dataset.dataset_id}_bold",
        name=f"{dataset.name} BOLD",
        parent_dataset_id=dataset.dataset_id,
        marker=marker,
        database=database,
        hits=tuple(hits),
        metadata={
            "parent_dataset_id": dataset.dataset_id,
            "marker": marker,
            "database": database,
            "workflow": "BOLD",
            "input_source_type": dataset.source_type.value,
            "input_sequence_count": dataset.sequence_count,
        },
    )


def _normalise_raw_hits(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise BoldWorkflowError("runner must return a BOLD hit mapping or iterable of mappings")
    raw_hits = tuple(value)
    if any(not isinstance(raw_hit, Mapping) for raw_hit in raw_hits):
        raise BoldWorkflowError("runner must return only BOLD hit mappings")
    return raw_hits


def _bold_hit_from_raw(
    expected_query_id: str,
    raw_hit: Mapping[str, object],
    default_database: str,
) -> BoldHit:
    raw_query_id = raw_hit.get("query_id", expected_query_id)
    if raw_query_id != expected_query_id:
        raise BoldWorkflowError(
            f"BOLD hit query_id does not match input record: {raw_query_id!r} != {expected_query_id!r}"
        )
    return BoldHit(
        query_id=expected_query_id,
        process_id=raw_hit.get("process_id"),
        record_id=raw_hit.get("record_id"),
        species_name=raw_hit.get("species_name"),
        genus=raw_hit.get("genus"),
        family=raw_hit.get("family"),
        order=raw_hit.get("order"),
        phylum=raw_hit.get("phylum"),
        bin_uri=raw_hit.get("bin_uri"),
        similarity=raw_hit.get("similarity"),
        database=raw_hit.get("database", default_database),
        country=raw_hit.get("country"),
        institution=raw_hit.get("institution"),
        specimen_id=raw_hit.get("specimen_id"),
        collection_date=raw_hit.get("collection_date"),
    )


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoldWorkflowError(f"{field_name} must be a non-empty string")
    return value
