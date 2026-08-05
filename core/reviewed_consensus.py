"""Build a reviewed consensus from one review session.

This module deliberately reuses the existing ``ReviewedConsensus`` value
object and decision application logic. It adds only the workflow boundary from
``ConsensusReviewSession`` to that established core API.
"""

from core.consensus_review_session import ConsensusReviewSession
from core.human_review import ReviewedConsensus, apply_review_decisions


def build_reviewed_consensus(
    sample_id: str,
    original_sequence: str,
    session: ConsensusReviewSession,
) -> ReviewedConsensus:
    """Derive a review-only sequence from decisions held by one session.

    The function never changes ``original_sequence``, the session, its opaque
    candidate reference, or any decision. Existing validation in
    ``apply_review_decisions`` remains the authority for base and coordinate
    consistency.
    """

    if not isinstance(session, ConsensusReviewSession):
        raise ValueError("session must be a ConsensusReviewSession")
    if sample_id != session.sample_id:
        raise ValueError("sample_id does not match the session sample_id")
    return apply_review_decisions(
        sample_id,
        original_sequence,
        session.get_decisions(),
    )
