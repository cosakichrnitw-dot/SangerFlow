"""Pure Studio presentation adapter for one reviewed F/R consensus.

This keeps the Studio packaging boundary independent of the legacy Tkinter
viewer while continuing to consume the same immutable pair-alignment and
consensus-v2.1 evidence objects. It contains no assembly or consensus logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from core.assembly_models import PairAlignment
from core.consensus_review_bridge import ReviewEvidence, create_review_evidence
from core.consensus_v2_1 import ConsensusV21Result


@dataclass(frozen=True)
class SingleConsensusColumn:
    """Immutable display representation of one consensus base."""

    consensus_position: int
    base: str
    status: str
    confidence_level: str
    selected_source: str
    review_evidence: ReviewEvidence


@dataclass(frozen=True)
class SingleConsensusViewModel:
    """Display-only adapter for the existing consensus review evidence."""

    sample_identifier: str
    consensus_sequence: str
    columns: Sequence[SingleConsensusColumn]

    def __post_init__(self) -> None:
        if not isinstance(self.sample_identifier, str) or not self.sample_identifier:
            raise ValueError("sample_identifier must be a non-empty string")
        if not isinstance(self.consensus_sequence, str):
            raise ValueError("consensus_sequence must be a string")
        columns = tuple(self.columns)
        if len(columns) != len(self.consensus_sequence):
            raise ValueError("columns and consensus_sequence lengths differ")
        for index, column in enumerate(columns):
            if not isinstance(column, SingleConsensusColumn):
                raise ValueError("columns must contain SingleConsensusColumn values")
            if column.consensus_position != index:
                raise ValueError("consensus positions must be contiguous and 0-based")
            if column.base != self.consensus_sequence[index]:
                raise ValueError("column base must match consensus_sequence")
        object.__setattr__(self, "columns", columns)

    def column_at(self, consensus_position: int) -> SingleConsensusColumn:
        if isinstance(consensus_position, bool) or not isinstance(consensus_position, int):
            raise ValueError("consensus_position must be an integer")
        if not 0 <= consensus_position < len(self.columns):
            raise IndexError("consensus_position is outside the view model")
        return self.columns[consensus_position]


def build_single_consensus_view_model(
    sample_identifier: str,
    pair_alignment: PairAlignment,
    consensus_result: ConsensusV21Result,
    *,
    v1_bases: Sequence[str] | None = None,
) -> SingleConsensusViewModel:
    """Adapt immutable v2.1 evidence without recalculating consensus."""

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if not isinstance(consensus_result, ConsensusV21Result):
        raise ValueError("consensus_result must be a ConsensusV21Result")
    if pair_alignment.length != len(consensus_result.decisions):
        raise ValueError("pair_alignment and consensus_result lengths differ")
    if v1_bases is not None and len(v1_bases) != pair_alignment.length:
        raise ValueError("v1_bases and pair_alignment lengths differ")

    columns = []
    for decision in consensus_result.decisions:
        v1_base = None if v1_bases is None else v1_bases[decision.alignment_index]
        evidence = create_review_evidence(
            decision,
            pair_alignment,
            sample_identifier=sample_identifier,
            v1_base=v1_base,
        )
        columns.append(
            SingleConsensusColumn(
                consensus_position=decision.alignment_index,
                base=decision.consensus_base,
                status=_display_status(decision.decision_reason.value, decision.consensus_base),
                confidence_level=decision.confidence_level.value,
                selected_source=decision.selected_source.value,
                review_evidence=evidence,
            )
        )
    return SingleConsensusViewModel(
        sample_identifier=sample_identifier,
        consensus_sequence=consensus_result.consensus_sequence,
        columns=columns,
    )


def _display_status(decision_reason: str, consensus_base: str) -> str:
    if consensus_base == "N":
        return "N"
    if decision_reason == "TWO_SIDED_AGREEMENT":
        return "TWO_SIDED_AGREEMENT"
    if decision_reason in ("HIGHER_QUALITY_FORWARD", "HIGHER_QUALITY_REVERSE"):
        return decision_reason
    if decision_reason in ("UNRESOLVED_CONFLICT", "INSUFFICIENT_EVIDENCE"):
        return "UNRESOLVED"
    return "NORMAL"
