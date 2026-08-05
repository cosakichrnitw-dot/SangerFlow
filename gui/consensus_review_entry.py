"""GUI-facing orchestration for opening a review window from loaded reads.

This module only selects clear filename pairs and invokes existing core APIs.
It does not implement alignment, consensus, coordinate mapping, or review
criteria.
"""

from dataclasses import dataclass
from typing import Iterable, Optional

from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from core.consensus_v2_1 import build_pair_consensus_v2_1
from core.consensus_evidence_map import ConsensusEvidenceEntry, ConsensusEvidenceMap
from core.pair_alignment import align_pair
from core.samples import PairingStatus, Sample, classify_reads_by_filename
from core.trimming import trim_sequence
from gui.consensus_review_manager import ConsensusReviewCandidate
from gui.consensus_viewer import build_single_consensus_view_model


@dataclass(frozen=True)
class ConsensusReviewPairRow:
    """Display-only information for one clear pair in the GUI selector."""

    sample: Sample
    sample_id: str
    forward_filename: str
    reverse_filename: str
    forward_input_length: Optional[int]
    reverse_input_length: Optional[int]


@dataclass(frozen=True)
class ConsensusReviewManagerInputs:
    """Candidate and evidence inputs required by the existing review manager.

    The Main Viewer passes loaded reads to this entry layer. This value keeps
    candidate construction and evidence indexing outside the Main Viewer while
    retaining the existing single-review models for both review modes.
    """

    candidates: tuple[ConsensusReviewCandidate, ...]
    evidence_map: ConsensusEvidenceMap

    def __post_init__(self) -> None:
        if not self.candidates:
            raise ValueError("at least one consensus review candidate is required")
        if any(
            not isinstance(candidate, ConsensusReviewCandidate)
            for candidate in self.candidates
        ):
            raise ValueError("candidates must contain ConsensusReviewCandidate values")
        if not isinstance(self.evidence_map, ConsensusEvidenceMap):
            raise ValueError("evidence_map must be a ConsensusEvidenceMap")


def discover_clear_pairs(reads: Iterable[object]) -> tuple[Sample, ...]:
    """Return only unambiguous filename-derived Forward/Reverse pairs."""

    return tuple(
        sample
        for sample in classify_reads_by_filename(reads)
        if sample.pairing_status is PairingStatus.CLEAR_PAIR
    )


def build_consensus_review_pair_rows(
    clear_pairs: Iterable[Sample],
) -> tuple[ConsensusReviewPairRow, ...]:
    """Expose clear-pair filenames and available consensus-input lengths.

    A length is taken from the existing trimmed read when available. For an
    untrimmed read, the raw sequence length is shown as the only currently
    available input length; this function neither trims nor mutates a read.
    """

    rows = []
    for sample in clear_pairs:
        if not isinstance(sample, Sample) or not sample.is_clear_pair:
            raise ValueError("clear_pairs must contain clear Forward/Reverse pairs")
        forward_read = sample.forward_read
        reverse_read = sample.reverse_read
        if forward_read is None or reverse_read is None:
            raise ValueError("clear pair is missing a read")
        rows.append(
            ConsensusReviewPairRow(
                sample=sample,
                sample_id=sample.sample_id,
                forward_filename=forward_read.filename,
                reverse_filename=reverse_read.filename,
                forward_input_length=_available_input_length(forward_read),
                reverse_input_length=_available_input_length(reverse_read),
            )
        )
    return tuple(rows)


def build_review_view_model(sample: Sample):
    """Run the existing pair workflow for one selected clear pair."""

    if not isinstance(sample, Sample) or not sample.is_clear_pair:
        raise ValueError("sample must be a clear Forward/Reverse pair")
    forward_read = sample.forward_read
    reverse_read = sample.reverse_read
    if forward_read is None or reverse_read is None:
        raise ValueError("clear pair is missing a read")

    _ensure_trimmed(forward_read)
    _ensure_trimmed(reverse_read)
    pair_alignment = align_pair(
        build_forward_assembly_view(forward_read),
        build_reverse_assembly_view(reverse_read),
    )
    consensus_result = build_pair_consensus_v2_1(pair_alignment)
    return build_single_consensus_view_model(
        sample.sample_id,
        pair_alignment,
        consensus_result,
    )


def build_consensus_review_manager_inputs(
    clear_pairs: Iterable[Sample],
) -> ConsensusReviewManagerInputs:
    """Build manager candidates from filename-derived pairs via existing APIs.

    This is the Main Viewer bridge's only workflow construction point. It
    invokes the already established trim, AssemblyReadView, pair alignment,
    consensus-v2.1, and single-review model route; it does not duplicate those
    implementations or alter a loaded read beyond existing derived trim data.
    """

    pair_values = tuple(clear_pairs)
    if not pair_values:
        raise ValueError("at least one clear Forward/Reverse pair is required")

    candidates = []
    evidence_entries = []
    for sample in pair_values:
        if not isinstance(sample, Sample) or not sample.is_clear_pair:
            raise ValueError("clear_pairs must contain clear Forward/Reverse pairs")
        forward_read = sample.forward_read
        reverse_read = sample.reverse_read
        if forward_read is None or reverse_read is None:
            raise ValueError("clear pair is missing a read")
        view_model = build_review_view_model(sample)
        candidates.append(
            ConsensusReviewCandidate(
                sample_id=sample.sample_id,
                sequence=view_model.consensus_sequence,
                single_review_input=view_model,
                metadata={
                    "forward_filename": forward_read.filename,
                    "reverse_filename": reverse_read.filename,
                    "algorithm_version": "consensus-v2.1-shadow",
                },
            )
        )
        for column in view_model.columns:
            evidence_entries.append(
                ConsensusEvidenceEntry(
                    sample_id=sample.sample_id,
                    consensus_position=column.consensus_position,
                    review_evidence=column.review_evidence,
                )
            )

    return ConsensusReviewManagerInputs(
        candidates=tuple(candidates),
        evidence_map=ConsensusEvidenceMap(evidence_entries),
    )


def _ensure_trimmed(read) -> None:
    """Use the existing trim result, or derive it once for a loaded raw read."""

    if not read.trimmed_sequence:
        trim_sequence(read)


def _available_input_length(read) -> Optional[int]:
    """Return an existing trimmed length, or the available raw length."""

    trimmed_sequence = getattr(read, "trimmed_sequence", "")
    if trimmed_sequence:
        return len(trimmed_sequence)
    sequence = getattr(read, "sequence", None)
    if sequence is None:
        return None
    return len(sequence)
