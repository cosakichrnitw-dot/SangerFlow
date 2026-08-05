"""Minimal file exports for reviewed consensus results and their audit trail.

These functions export existing review-only values. They do not create review
decisions, alter candidates or sessions, or connect to the application's
existing GUI/export workflow.
"""

import csv
from os import PathLike
from pathlib import Path

from core.consensus_review_session import ConsensusReviewSession
from core.human_review import ReviewedConsensus


def export_reviewed_consensus_fasta(
    reviewed_consensus: ReviewedConsensus,
    filepath: str | PathLike[str],
) -> None:
    """Write one reviewed sequence as a 60-base-line FASTA record.

    The record identifier is exactly ``{sample_id}_reviewed``. The function
    only reads the immutable ``ReviewedConsensus`` value.
    """

    if not isinstance(reviewed_consensus, ReviewedConsensus):
        raise ValueError("reviewed_consensus must be a ReviewedConsensus")
    output_path = Path(filepath)
    with output_path.open("w", encoding="utf-8", newline="\n") as output_file:
        output_file.write(f">{reviewed_consensus.sample_id}_reviewed\n")
        for start in range(0, len(reviewed_consensus.reviewed_sequence), 60):
            output_file.write(f"{reviewed_consensus.reviewed_sequence[start:start + 60]}\n")


def export_review_report(
    session: ConsensusReviewSession,
    filepath: str | PathLike[str],
) -> None:
    """Write one session's decision audit trail as UTF-8 TSV.

    ``consensus_position`` is deliberately exported as the existing 0-based
    core coordinate; the exporter does not silently translate positions for a
    different UI convention.
    """

    if not isinstance(session, ConsensusReviewSession):
        raise ValueError("session must be a ConsensusReviewSession")
    output_path = Path(filepath)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "sample_id",
                "consensus_position",
                "original_base",
                "reviewed_base",
                "decision_type",
                "reason",
            )
        )
        for decision in session.get_decisions():
            writer.writerow(
                (
                    decision.sample_id,
                    decision.consensus_position,
                    decision.original_base,
                    "" if decision.reviewed_base is None else decision.reviewed_base,
                    decision.decision_type.value,
                    decision.reason,
                )
            )
