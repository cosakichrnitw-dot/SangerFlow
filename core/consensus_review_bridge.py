"""Diagnostic bridge from a v2.1 decision to existing trace coordinates.

This module reads immutable ``PairAlignment`` and ``ConsensusV21Decision``
values.  It neither imports GUI modules nor changes consensus, review, or
export behavior.  A future GUI adapter may consume ``TraceJumpTarget``.
"""

from dataclasses import dataclass
from math import isclose
from numbers import Real
from typing import Optional

from core.assembly_models import PairAlignment, ReadCoordinate
from core.consensus_v2_1 import ConsensusV21Decision


@dataclass(frozen=True)
class TraceJumpTarget:
    """A GUI-neutral request to open one read at its raw trace position."""

    read_identifier: str
    raw_trace_position: int


@dataclass(frozen=True)
class ReviewEvidence:
    """Traceable diagnostic evidence for one v2.1 consensus decision.

    Every coordinate is copied directly from the corresponding
    ``ReadCoordinate``.  A ``None`` side represents a gap or missing source
    coordinate and deliberately produces no jump target.
    """

    sample_identifier: Optional[str]
    alignment_column: int
    decision_reason: str
    consensus_base: str
    v1_base: Optional[str]
    forward_read_identifier: str
    forward_base: Optional[str]
    forward_quality: Optional[float]
    forward_raw_index: Optional[int]
    forward_trimmed_index: Optional[int]
    forward_raw_trace_position: Optional[int]
    forward_trimmed_trace_position: Optional[int]
    reverse_read_identifier: str
    reverse_base: Optional[str]
    reverse_quality: Optional[float]
    reverse_raw_index: Optional[int]
    reverse_trimmed_index: Optional[int]
    reverse_raw_trace_position: Optional[int]
    reverse_trimmed_trace_position: Optional[int]
    forward_jump_target: Optional[TraceJumpTarget]
    reverse_jump_target: Optional[TraceJumpTarget]


def create_review_evidence(
    decision: ConsensusV21Decision,
    pair_alignment: PairAlignment,
    *,
    sample_identifier: Optional[str] = None,
    v1_base: Optional[str] = None,
) -> ReviewEvidence:
    """Return v2.1 review evidence without calculating any new coordinate.

    ``sample_identifier`` is optional because ``PairAlignment`` contains read
    filenames but no sample-level identifier.  ``v1_base`` is optional so a
    comparison caller can attach an independently calculated v1 value without
    coupling this bridge to the v1 implementation.
    """

    if not isinstance(decision, ConsensusV21Decision):
        raise ValueError("decision must be a ConsensusV21Decision")
    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if sample_identifier is not None and (
        not isinstance(sample_identifier, str) or not sample_identifier
    ):
        raise ValueError("sample_identifier must be a non-empty string or None")
    if v1_base is not None and (not isinstance(v1_base, str) or len(v1_base) != 1):
        raise ValueError("v1_base must be a one-character string or None")

    column = pair_alignment.column_at(decision.alignment_index)
    forward = _side_evidence(
        pair_alignment.forward_view.source_filename,
        pair_alignment.forward_view.sequence,
        pair_alignment.forward_view.quality,
        column.forward,
        decision.forward_base,
        decision.forward_quality,
        "forward",
    )
    reverse = _side_evidence(
        pair_alignment.reverse_view.source_filename,
        pair_alignment.reverse_view.sequence,
        pair_alignment.reverse_view.quality,
        column.reverse,
        decision.reverse_base,
        decision.reverse_quality,
        "reverse",
    )
    return ReviewEvidence(
        sample_identifier=sample_identifier,
        alignment_column=decision.alignment_index,
        decision_reason=decision.decision_reason.value,
        consensus_base=decision.consensus_base,
        v1_base=v1_base,
        forward_read_identifier=forward["read_identifier"],
        forward_base=forward["base"],
        forward_quality=forward["quality"],
        forward_raw_index=forward["raw_index"],
        forward_trimmed_index=forward["trimmed_index"],
        forward_raw_trace_position=forward["raw_trace_position"],
        forward_trimmed_trace_position=forward["trimmed_trace_position"],
        reverse_read_identifier=reverse["read_identifier"],
        reverse_base=reverse["base"],
        reverse_quality=reverse["quality"],
        reverse_raw_index=reverse["raw_index"],
        reverse_trimmed_index=reverse["trimmed_index"],
        reverse_raw_trace_position=reverse["raw_trace_position"],
        reverse_trimmed_trace_position=reverse["trimmed_trace_position"],
        forward_jump_target=forward["jump_target"],
        reverse_jump_target=reverse["jump_target"],
    )


def _side_evidence(
    read_identifier,
    sequence,
    quality_values,
    coordinate: Optional[ReadCoordinate],
    decision_base,
    decision_quality,
    side_name,
):
    if coordinate is None:
        if decision_base is not None or decision_quality is not None:
            raise ValueError(f"{side_name} decision evidence must be None for a gap")
        return {
            "read_identifier": read_identifier,
            "base": None,
            "quality": None,
            "raw_index": None,
            "trimmed_index": None,
            "raw_trace_position": None,
            "trimmed_trace_position": None,
            "jump_target": None,
        }
    expected_base = sequence[coordinate.assembly_index].upper()
    expected_quality = float(quality_values[coordinate.assembly_index])
    if decision_base != expected_base:
        raise ValueError(f"{side_name} decision base does not match PairAlignment")
    if not isinstance(decision_quality, Real) or not isclose(
        float(decision_quality), expected_quality
    ):
        raise ValueError(f"{side_name} decision quality does not match PairAlignment")
    return {
        "read_identifier": read_identifier,
        "base": decision_base,
        "quality": float(decision_quality),
        "raw_index": coordinate.raw_index,
        "trimmed_index": coordinate.trimmed_index,
        "raw_trace_position": coordinate.raw_trace_position,
        "trimmed_trace_position": coordinate.trimmed_trace_position,
        "jump_target": TraceJumpTarget(read_identifier, coordinate.raw_trace_position),
    }
