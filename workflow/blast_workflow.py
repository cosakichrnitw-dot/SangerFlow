"""SequenceDataset-to-BLAST result workflow adapter.

The workflow deliberately delegates BLAST execution to either an injected
runner or the existing :func:`core.blast.blast_sequence` implementation.  It
does not perform network work itself and only converts the established raw
dictionary result shape into immutable project result values.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Callable

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.sequence_dataset import SequenceDataset


BlastRunner = Callable[[str], Iterable[Mapping[str, object]]]


def run_blast_workflow(
    dataset: SequenceDataset,
    *,
    analysis_mode: BlastAnalysisMode,
    marker: str | None = None,
    database: str = "nt",
    runner: BlastRunner | None = None,
) -> BlastResultDataset:
    """Run BLAST for each ordered sequence record and return immutable hits.

    ``runner`` is intentionally injectable for callers that supply an
    existing BLAST service or tests.  When omitted, the established
    NCBI BLAST Common URL API runner is called with the selected database.
    A runner returns the existing raw hit mapping shape, e.g.
    ``species``, ``identity``, ``coverage``, ``e_value``, ``accession``, and
    ``title``.
    """

    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    if not dataset.records:
        raise ValueError("dataset must contain at least one sequence record")
    if not isinstance(analysis_mode, BlastAnalysisMode):
        raise ValueError("analysis_mode must be a BlastAnalysisMode")
    _required_text(database, "database")
    if marker is not None:
        _required_text(marker, "marker")
    if runner is not None and not callable(runner):
        raise ValueError("runner must be callable or None")

    active_runner = _default_runner(database) if runner is None else runner
    hits: list[BlastHit] = []
    for record in dataset.records:
        raw_hits = active_runner(record.sequence)
        hits.extend(
            _blast_hit_from_raw(record.sequence_id, raw_hit, database)
            for raw_hit in _validate_runner_result(raw_hits)
        )

    if not hits:
        raise ValueError("BLAST workflow returned no hits")

    return BlastResultDataset(
        result_id=f"{dataset.dataset_id}_blast_{analysis_mode.value.lower()}",
        name=f"{dataset.name} BLAST ({analysis_mode.value})",
        hits=tuple(hits),
        parent_dataset_id=dataset.dataset_id,
        analysis_mode=analysis_mode,
        marker=marker,
        database=database,
        metadata={
            "workflow": "BLAST",
            "input_source_type": dataset.source_type.value,
            "input_sequence_count": dataset.sequence_count,
        },
    )


def _default_runner(database: str) -> BlastRunner:
    """Use the workflow-level NCBI BLAST URL API executor."""

    from workflow.ncbi_blast_service import NcbiBlastRunner, NcbiBlastSettings

    ncbi_runner = NcbiBlastRunner(NcbiBlastSettings(database=database))

    def runner(sequence: str) -> Iterable[Mapping[str, object]]:
        return ncbi_runner(sequence)

    return runner


def _validate_runner_result(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError("runner must return an iterable of BLAST hit mappings")
    raw_hits = tuple(value)
    if any(not isinstance(raw_hit, Mapping) for raw_hit in raw_hits):
        raise ValueError("runner must return only BLAST hit mappings")
    return raw_hits


def _blast_hit_from_raw(
    query_id: str,
    raw_hit: Mapping[str, object],
    database: str,
) -> BlastHit:
    """Convert the established ``core.blast.blast_sequence`` result shape."""

    species = _raw_text(raw_hit, "scientific_name", fallback="species")
    organism = _raw_text(raw_hit, "organism", fallback="species")
    if organism is None:
        organism = species
    if species is None:
        species = organism
    return BlastHit(
        query_id=query_id,
        hit_accession=_raw_text(raw_hit, "accession", fallback="hit_accession"),
        scientific_name=species,
        organism=organism,
        identity=_raw_value(raw_hit, "identity"),
        query_coverage=_raw_value(raw_hit, "coverage", fallback="query_coverage"),
        evalue=_raw_value(raw_hit, "e_value", fallback="evalue"),
        alignment_length=_raw_value(raw_hit, "alignment_length"),
        database=_raw_text(raw_hit, "database") or database,
        bit_score=_raw_optional_number(raw_hit, "bit_score"),
        description=_raw_text(raw_hit, "description", fallback="title"),
    )


def _raw_value(raw_hit: Mapping[str, object], key: str, *, fallback: str | None = None) -> object:
    if key in raw_hit:
        return raw_hit[key]
    if fallback is not None and fallback in raw_hit:
        return raw_hit[fallback]
    raise ValueError(f"BLAST hit is missing required field: {key}")


def _raw_text(
    raw_hit: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str | None:
    try:
        value = _raw_value(raw_hit, key, fallback=fallback)
    except ValueError:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _raw_optional_number(raw_hit: Mapping[str, object], key: str) -> object | None:
    return raw_hit.get(key)
