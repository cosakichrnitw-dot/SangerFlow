"""Adapter from an immutable BLAST query selection to a sequence dataset."""

from __future__ import annotations

from collections.abc import Mapping

from core.blast_filter import BlastResultSelection
from core.lineage import RecordProvenance, RecordRef
from core.sequence_dataset import SequenceDataset, SequenceRecord


def create_dataset_from_blast_selection(
    source_dataset: SequenceDataset,
    selection: BlastResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
) -> SequenceDataset:
    """Create a new immutable dataset containing the selected source records.

    Sequence-record order follows ``selection.selected_query_ids``.  This
    preserves the BLAST-query selection order rather than silently changing it
    to source-dataset order.
    """

    if not isinstance(source_dataset, SequenceDataset):
        raise ValueError("source_dataset must be a SequenceDataset")
    if not isinstance(selection, BlastResultSelection):
        raise ValueError("selection must be a BlastResultSelection")
    if not selection.selected_query_ids:
        raise ValueError("selection must contain at least one query_id")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    _validate_optional_result_link(source_dataset, selection)
    try:
        source_records = tuple(
            source_dataset.get_record(query_id) for query_id in selection.selected_query_ids
        )
    except KeyError as error:
        raise ValueError(
            f"selection contains query_id absent from source_dataset: {error.args[0]}"
        ) from error

    selected_records = tuple(
        SequenceRecord(
            sequence_id=record.sequence_id,
            sequence=record.sequence,
            description=record.description,
            source_reference=record.source_reference,
            metadata=record.metadata,
            provenance=RecordProvenance(
                (RecordRef(source_dataset.dataset_id, record.sequence_id),)
            ),
        )
        for record in source_records
    )

    dataset_metadata = dict(metadata or {})
    dataset_metadata.update(
        {
            "source_dataset_id": source_dataset.dataset_id,
            "derived_from": "BLAST_SELECTION",
            "blast_result_id": selection.source_result_id,
            "selected_query_count": len(selection.selected_query_ids),
        }
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=source_dataset.source_type,
        records=selected_records,
        metadata=dataset_metadata,
    )


def _validate_optional_result_link(
    source_dataset: SequenceDataset,
    selection: BlastResultSelection,
) -> None:
    """Validate a result link when upstream workflow metadata provides one.

    The public adapter receives a source dataset and a selection, not the
    ``BlastResultDataset`` itself.  A direct result-ID equality check is only
    possible when a producing workflow recorded ``blast_result_id`` on the
    source dataset; otherwise query-ID validation remains the available
    integrity check at this boundary.
    """

    source_result_id = source_dataset.metadata.get("blast_result_id")
    if source_result_id is not None and source_result_id != selection.source_result_id:
        raise ValueError(
            "selection.source_result_id does not match source_dataset "
            "blast_result_id metadata"
        )
