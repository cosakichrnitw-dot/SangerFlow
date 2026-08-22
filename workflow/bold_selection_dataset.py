"""Adapter from an immutable BOLD query selection to a sequence dataset."""

from __future__ import annotations

from collections.abc import Mapping

from core.bold_filter import BoldResultSelection
from core.lineage import RecordProvenance, RecordRef
from core.sequence_dataset import SequenceDataset, SequenceRecord


def create_dataset_from_bold_selection(
    source_dataset: SequenceDataset,
    selection: BoldResultSelection,
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
) -> SequenceDataset:
    """Create an immutable dataset containing selected source records.

    Record order follows ``selection.selected_query_ids``.  The original
    records, including their source references and metadata, are reused as
    immutable values rather than reconstructed from BOLD result fields.
    """

    if not isinstance(source_dataset, SequenceDataset):
        raise ValueError("source_dataset must be a SequenceDataset")
    if not isinstance(selection, BoldResultSelection):
        raise ValueError("selection must be a BoldResultSelection")
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
            "derived_from": "BOLD_SELECTION",
            "bold_result_id": selection.source_result_id,
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
    selection: BoldResultSelection,
) -> None:
    """Validate a result link only when upstream metadata provides one."""

    source_result_id = source_dataset.metadata.get("bold_result_id")
    if source_result_id is not None and source_result_id != selection.source_result_id:
        raise ValueError(
            "selection.source_result_id does not match source_dataset "
            "bold_result_id metadata"
        )
