"""Adapter from one immutable reviewed consensus to a sequence dataset."""

from __future__ import annotations

from collections.abc import Mapping

from core.human_review import ReviewedConsensus
from core.lineage import RecordProvenance
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


def create_dataset_from_reviewed_consensus(
    reviewed_consensus: ReviewedConsensus,
    *,
    dataset_id: str,
    name: str,
    metadata: Mapping[str, object] | None = None,
    provenance: RecordProvenance | None = None,
) -> SequenceDataset:
    """Project a reviewed consensus into a one-record immutable dataset.

    A ``ReviewedConsensus`` with no applied decisions is deliberately not
    promoted: it represents an unreviewed candidate, not a reviewed result.
    The adapter never modifies either the reviewed value or its decisions.
    """

    if not isinstance(reviewed_consensus, ReviewedConsensus):
        raise ValueError("reviewed_consensus must be a ReviewedConsensus")
    if not reviewed_consensus.applied_decisions:
        raise ValueError("reviewed_consensus must contain at least one applied decision")
    if metadata is not None and not isinstance(metadata, Mapping):
        raise ValueError("metadata must be a mapping or None")
    if provenance is not None and not isinstance(provenance, RecordProvenance):
        raise ValueError("provenance must be a RecordProvenance or None")

    user_metadata = dict(metadata or {})
    consensus_method = user_metadata.get("consensus_method", "human_review")
    original_read_count = user_metadata.get("original_read_count")
    if not isinstance(consensus_method, str) or not consensus_method.strip():
        raise ValueError("metadata consensus_method must be a non-empty string")
    if original_read_count is not None and (
        not isinstance(original_read_count, int)
        or isinstance(original_read_count, bool)
        or original_read_count < 0
    ):
        raise ValueError("metadata original_read_count must be a non-negative integer or None")

    user_metadata.update(
        {
            "source": "Reviewed Consensus",
            "reviewed": True,
            "consensus_method": consensus_method,
            "original_read_count": original_read_count,
            "source_sample_id": reviewed_consensus.sample_id,
            "original_sequence_length": len(reviewed_consensus.original_sequence),
            "applied_decision_count": len(reviewed_consensus.applied_decisions),
        }
    )
    record = SequenceRecord(
        sequence_id=reviewed_consensus.sample_id,
        sequence=reviewed_consensus.reviewed_sequence,
        source_reference=reviewed_consensus,
        metadata={
            "source": "Reviewed Consensus",
            "reviewed": True,
            "original_sequence_length": len(reviewed_consensus.original_sequence),
            "applied_decision_count": len(reviewed_consensus.applied_decisions),
        },
        provenance=provenance,
    )
    return SequenceDataset(
        dataset_id=dataset_id,
        name=name,
        source_type=SourceType.REVIEWED_CONSENSUS,
        records=(record,),
        metadata=user_metadata,
    )
