"""Immutable prototype models for human review of consensus candidates.

This module never changes a ConsensusCandidate, ReviewEvidence, consensus
algorithm, or export result. It records human decisions separately and derives
a review-only sequence from the original candidate plus those decisions.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Sequence


_DNA_IUPAC_SYMBOLS = frozenset("ACGTNRYSWKMBDHV")
# A multiple-alignment reviewer may record a proposed visual gap for one
# aligned cell.  This does not make a gap part of a ConsensusCandidate; it is
# only an append-only human-review record until a later reviewed-alignment
# workflow defines how such a decision is applied.
_REVIEWED_BASE_SYMBOLS = _DNA_IUPAC_SYMBOLS | frozenset("-")


class DecisionType(str, Enum):
    """The supported human-review outcomes for one consensus position."""

    ACCEPT = "ACCEPT"
    CHANGE = "CHANGE"
    AMBIGUOUS = "AMBIGUOUS"
    REJECT = "REJECT"


@dataclass(frozen=True)
class HumanReviewDecision:
    """One append-only human judgement about an existing consensus base.

    ``consensus_position`` is 0-based, matching current core and GUI model
    contracts. ``evidence_reference`` is opaque by design so this model does
    not couple itself to ReviewEvidence or a GUI implementation.
    """

    sample_id: str
    consensus_position: int
    original_base: str
    reviewed_base: Optional[str]
    decision_type: DecisionType
    reason: str
    evidence_reference: object | None
    reviewer: str
    timestamp: datetime

    def __post_init__(self) -> None:
        _validate_sample_id(self.sample_id)
        if not isinstance(self.consensus_position, int) or isinstance(
            self.consensus_position, bool
        ) or self.consensus_position < 0:
            raise ValueError("consensus_position must be a non-negative 0-based integer")
        _validate_base("original_base", self.original_base)
        if self.reviewed_base is not None:
            _validate_base("reviewed_base", self.reviewed_base, allow_gap=True)
        if not isinstance(self.decision_type, DecisionType):
            raise ValueError("decision_type must be a DecisionType")
        if not isinstance(self.reason, str):
            raise ValueError("reason must be a string")
        if not isinstance(self.reviewer, str) or not self.reviewer.strip():
            raise ValueError("reviewer must be a non-empty string")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("timestamp must be a datetime")

        if self.decision_type is DecisionType.ACCEPT:
            if self.reviewed_base != self.original_base:
                raise ValueError("ACCEPT must retain the original_base")
        elif self.decision_type in (DecisionType.CHANGE, DecisionType.AMBIGUOUS):
            if self.reviewed_base is None or self.reviewed_base == self.original_base:
                raise ValueError("CHANGE and AMBIGUOUS require a different reviewed_base")
        elif self.decision_type is DecisionType.REJECT:
            if self.reviewed_base not in (None, self.original_base):
                raise ValueError("REJECT must not change the original_base in this prototype")


@dataclass(frozen=True)
class ReviewedConsensus:
    """A derived review result that retains its original candidate sequence."""

    sample_id: str
    original_sequence: str
    reviewed_sequence: str
    applied_decisions: tuple[HumanReviewDecision, ...]

    def __post_init__(self) -> None:
        _validate_sample_id(self.sample_id)
        _validate_sequence("original_sequence", self.original_sequence)
        _validate_sequence("reviewed_sequence", self.reviewed_sequence)
        if len(self.original_sequence) != len(self.reviewed_sequence):
            raise ValueError("reviewed_sequence must preserve the original sequence length")
        decisions = tuple(self.applied_decisions)
        if any(not isinstance(decision, HumanReviewDecision) for decision in decisions):
            raise ValueError("applied_decisions must contain HumanReviewDecision values")
        if any(decision.sample_id != self.sample_id for decision in decisions):
            raise ValueError("all applied decisions must belong to sample_id")
        object.__setattr__(self, "applied_decisions", decisions)


def apply_review_decisions(
    sample_id: str,
    original_sequence: str,
    decisions: Sequence[HumanReviewDecision],
) -> ReviewedConsensus:
    """Derive a ReviewedConsensus without mutating the original sequence.

    CHANGE and AMBIGUOUS replace exactly one existing 0-based position. ACCEPT
    and REJECT remain in the audit trail but leave the prototype sequence
    unchanged. Duplicate decisions for one position are rejected rather than
    silently choosing an order.
    """

    _validate_sample_id(sample_id)
    _validate_sequence("original_sequence", original_sequence)
    decision_values = tuple(decisions)
    reviewed_bases = list(original_sequence)
    seen_positions = set()
    for decision in decision_values:
        if not isinstance(decision, HumanReviewDecision):
            raise ValueError("decisions must contain HumanReviewDecision values")
        if decision.sample_id != sample_id:
            raise ValueError("decision sample_id does not match sample_id")
        if decision.consensus_position >= len(original_sequence):
            raise ValueError("decision consensus_position is outside original_sequence")
        if decision.consensus_position in seen_positions:
            raise ValueError("only one decision per consensus_position is supported")
        seen_positions.add(decision.consensus_position)
        if original_sequence[decision.consensus_position] != decision.original_base:
            raise ValueError("decision original_base does not match original_sequence")
        if decision.decision_type in (DecisionType.CHANGE, DecisionType.AMBIGUOUS):
            reviewed_bases[decision.consensus_position] = decision.reviewed_base

    return ReviewedConsensus(
        sample_id=sample_id,
        original_sequence=original_sequence,
        reviewed_sequence="".join(reviewed_bases),
        applied_decisions=decision_values,
    )


def _validate_sample_id(sample_id: object) -> None:
    if not isinstance(sample_id, str) or not sample_id:
        raise ValueError("sample_id must be a non-empty string")


def _validate_base(name: str, base: object, *, allow_gap: bool = False) -> None:
    supported_symbols = _REVIEWED_BASE_SYMBOLS if allow_gap else _DNA_IUPAC_SYMBOLS
    if not isinstance(base, str) or len(base) != 1 or base not in supported_symbols:
        raise ValueError(f"{name} must be one supported DNA/IUPAC base")


def _validate_sequence(name: str, sequence: object) -> None:
    if not isinstance(sequence, str) or not sequence:
        raise ValueError(f"{name} must be a non-empty string")
    unsupported = set(sequence) - _DNA_IUPAC_SYMBOLS
    if unsupported:
        raise ValueError(f"{name} contains unsupported bases: {sorted(unsupported)}")
