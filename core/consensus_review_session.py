"""In-memory workflow container for decisions about one consensus candidate.

This prototype records ``HumanReviewDecision`` values without changing a
candidate, deriving a ``ReviewedConsensus``, or persisting/exporting data.
``candidate_reference`` is intentionally opaque so the session does not couple
the human-review core to a GUI or a particular candidate model.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from core.human_review import DecisionType, HumanReviewDecision


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ConsensusReviewSession:
    """Append-only review decisions for exactly one sample candidate.

    Positions remain 0-based because ``HumanReviewDecision`` uses the core
    consensus-position convention. The session deliberately retains its
    original candidate reference as an opaque value and never mutates it.
    """

    sample_id: str
    candidate_reference: object
    session_id: str = field(default_factory=lambda: str(uuid4()))
    decisions: list[HumanReviewDecision] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be a non-empty string")
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if not isinstance(self.created_at, datetime):
            raise ValueError("created_at must be a datetime")
        if not isinstance(self.updated_at, datetime):
            raise ValueError("updated_at must be a datetime")

        initial_decisions = tuple(self.decisions)
        self.decisions = []
        for decision in initial_decisions:
            self.add_decision(decision)

    def add_decision(self, decision: HumanReviewDecision) -> None:
        """Append one decision for this session's sample and refresh its timestamp."""

        if not isinstance(decision, HumanReviewDecision):
            raise ValueError("decision must be a HumanReviewDecision")
        if decision.sample_id != self.sample_id:
            raise ValueError("decision sample_id does not match the session sample_id")
        self.decisions.append(decision)
        self.updated_at = _utc_now()

    def get_decisions(self) -> tuple[HumanReviewDecision, ...]:
        """Return an immutable snapshot of the session decision history."""

        return tuple(self.decisions)

    def has_changes(self) -> bool:
        """Whether the session contains a base-changing review decision.

        ``ACCEPT`` and prototype ``REJECT`` entries are audit records only;
        they do not alter a candidate sequence. ``AMBIGUOUS`` can replace a
        base with an IUPAC code and is therefore treated as a change.
        """

        return any(
            decision.decision_type in (DecisionType.CHANGE, DecisionType.AMBIGUOUS)
            for decision in self.decisions
        )
