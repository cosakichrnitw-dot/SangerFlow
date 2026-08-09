"""Adapt existing MAFFT output into the immutable AlignmentDataset model.

This module does not execute MAFFT.  Existing MAFFT workflows can pass their
already-aligned records here while retaining the original unaligned
``SequenceDataset`` as the explicit lineage parent.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import DerivationType
from core.sequence_dataset import SequenceDataset, SequenceRecord


def create_alignment_dataset_from_mafft(
    source_dataset: SequenceDataset,
    aligned_records: Iterable[AlignmentRecord | SequenceRecord | Mapping[str, object]],
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
) -> AlignmentDataset:
    """Create an immutable MAFFT-derived AlignmentDataset from aligned rows.

    ``aligned_records`` accepts ``AlignmentRecord`` values directly, legacy
    aligned ``SequenceRecord`` values, or mappings with ``record_id`` and
    ``aligned_sequence`` (``sequence`` is also accepted).  Each row's source
    record defaults to its record ID and is verified against ``source_dataset``.
    """
    if not isinstance(source_dataset, SequenceDataset):
        raise ValueError("source_dataset must be a SequenceDataset")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")

    records = tuple(_coerce_alignment_record(item) for item in aligned_records)
    alignment_metadata = dict(metadata or {})
    alignment_metadata.update(
        {
            "alignment_method": "MAFFT",
            "software": "MAFFT",
            "parent_dataset_id": source_dataset.dataset_id,
            "derivation_type": DerivationType.ALIGNMENT_FROM_DATASET.value,
            "input_source_type": source_dataset.source_type.value,
        }
    )
    return AlignmentDataset.from_sequence_dataset(
        alignment_id=dataset_id,
        name=name,
        parent_dataset=source_dataset,
        records=records,
        metadata=alignment_metadata,
    )


def _coerce_alignment_record(
    value: AlignmentRecord | SequenceRecord | Mapping[str, object],
) -> AlignmentRecord:
    if isinstance(value, AlignmentRecord):
        return value
    if isinstance(value, SequenceRecord):
        return AlignmentRecord(
            record_id=value.sequence_id,
            source_record_id=value.sequence_id,
            aligned_sequence=value.sequence,
            metadata=value.metadata,
        )
    if isinstance(value, Mapping):
        record_id = value.get("record_id", value.get("sequence_id"))
        source_record_id = value.get("source_record_id", record_id)
        aligned_sequence = value.get("aligned_sequence", value.get("sequence"))
        return AlignmentRecord(
            record_id=record_id,
            source_record_id=source_record_id,
            aligned_sequence=aligned_sequence,
            metadata=value.get("metadata"),
        )
    raise ValueError(
        "aligned_records must contain AlignmentRecord, SequenceRecord, or mapping values"
    )
