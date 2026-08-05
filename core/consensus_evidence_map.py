"""Immutable lookup adapter between sample consensus positions and evidence.

This module deliberately does not modify ``AlignedConsensusSet`` or create
trace coordinates.  It only indexes already-created ``ReviewEvidence`` values
for a Multiple Consensus Alignment Viewer or another read-only client.
"""

from dataclasses import dataclass
from typing import Optional, Sequence

from core.consensus_review_bridge import ReviewEvidence


@dataclass(frozen=True)
class ConsensusEvidenceEntry:
    """One sample consensus position and its existing review evidence."""

    sample_id: str
    consensus_position: int
    review_evidence: ReviewEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(self.consensus_position, int) or isinstance(
            self.consensus_position, bool
        ) or self.consensus_position < 0:
            raise ValueError("consensus_position must be a non-negative integer")
        if not isinstance(self.review_evidence, ReviewEvidence):
            raise ValueError("review_evidence must be a ReviewEvidence")
        evidence_sample_id = self.review_evidence.sample_identifier
        if evidence_sample_id is not None and evidence_sample_id != self.sample_id:
            raise ValueError("review_evidence sample_identifier does not match sample_id")


class ConsensusEvidenceMap:
    """Immutable, gap-free lookup of evidence by sample and consensus position."""

    def __init__(self, entries: Sequence[ConsensusEvidenceEntry]) -> None:
        entry_values = tuple(entries)
        if any(not isinstance(entry, ConsensusEvidenceEntry) for entry in entry_values):
            raise ValueError("entries must contain ConsensusEvidenceEntry values")
        lookup = {}
        for entry in entry_values:
            key = (entry.sample_id, entry.consensus_position)
            if key in lookup:
                raise ValueError("duplicate sample_id and consensus_position entry")
            lookup[key] = entry.review_evidence
        self._entries = entry_values
        self._lookup = lookup

    @property
    def entries(self) -> tuple[ConsensusEvidenceEntry, ...]:
        """Return entries in the caller-supplied stable order."""

        return self._entries

    def lookup(
        self,
        sample_id: str,
        consensus_position: Optional[int],
    ) -> Optional[ReviewEvidence]:
        """Return existing evidence, or ``None`` for a gap / unknown position.

        A ``None`` position represents a multiple-alignment gap and is never
        converted to a neighbouring sequence position.
        """

        if consensus_position is None:
            return None
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(consensus_position, int) or isinstance(
            consensus_position, bool
        ) or consensus_position < 0:
            raise ValueError("consensus_position must be a non-negative integer or None")
        return self._lookup.get((sample_id, consensus_position))
