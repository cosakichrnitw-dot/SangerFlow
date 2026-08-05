"""SequenceDataset-to-MAFFT workflow adapter.

The workflow delegates all alignment execution and validation to the existing
``core.consensus_alignment`` MAFFT implementation.  It neither changes that
implementation nor imports GUI code.
"""

from __future__ import annotations

from typing import Callable, Optional

from core.consensus_alignment import AlignedConsensusSet, run_consensus_alignment
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


def align_sequence_dataset(
    dataset: SequenceDataset,
    *,
    dataset_id: str | None = None,
    name: str | None = None,
    alignment_id: str | None = None,
    mafft_executable: str = "mafft",
    runner: Optional[Callable[..., object]] = None,
) -> SequenceDataset:
    """Run existing MAFFT core logic and return a new alignment dataset.

    Only unaligned, gap-free datasets may enter this workflow.  Existing
    alignment datasets remain unchanged and must not be silently realigned by
    this minimal entry point.
    """

    if not isinstance(dataset, SequenceDataset):
        raise ValueError("dataset must be a SequenceDataset")
    if dataset.has_gaps:
        raise ValueError("MAFFT workflow requires an unaligned dataset without gaps")

    alignment_inputs = tuple(
        {
            "sample_id": record.sequence_id,
            "sequence": record.sequence,
            "metadata": record.metadata,
        }
        for record in dataset.records
    )
    result = run_consensus_alignment(
        alignment_inputs,
        mafft_executable=mafft_executable,
        alignment_id=alignment_id,
        runner=runner,
    )
    return _alignment_dataset_from_result(
        dataset,
        result,
        dataset_id=dataset_id,
        name=name,
    )


def _alignment_dataset_from_result(
    input_dataset: SequenceDataset,
    alignment: AlignedConsensusSet,
    *,
    dataset_id: str | None,
    name: str | None,
) -> SequenceDataset:
    original_records = {record.sequence_id: record for record in input_dataset.records}
    records = tuple(
        SequenceRecord(
            sequence_id=aligned_sequence.sample_id,
            sequence=aligned_sequence.aligned_sequence,
            description=original_records[aligned_sequence.sample_id].description,
            source_reference=original_records[aligned_sequence.sample_id],
            metadata=aligned_sequence.metadata,
        )
        for aligned_sequence in alignment.sequences
    )
    return SequenceDataset(
        dataset_id=dataset_id or f"{input_dataset.dataset_id}_mafft",
        name=name or f"{input_dataset.name} (MAFFT alignment)",
        source_type=SourceType.IMPORTED_ALIGNMENT,
        records=records,
        metadata={
            "parent_dataset_id": input_dataset.dataset_id,
            "derivation_type": "ALIGNED_WITH_MAFFT",
            "input_source_type": input_dataset.source_type.value,
            "mafft_alignment_id": alignment.alignment_id,
            "alignment_length": alignment.alignment_length,
            "gap_count": alignment.gap_count,
            "gap_percentage": alignment.gap_percentage,
        },
    )
