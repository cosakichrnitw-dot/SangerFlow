"""Human-readable labels for immutable consensus-v2.1 decision evidence.

This module deliberately translates existing decision codes only.  It does
not inspect qualities, recalculate confidence, or alter the consensus result.
"""

from __future__ import annotations


_REASON_LABELS = {
    "TWO_SIDED_AGREEMENT": "Forward and reverse reads agree",
    "INSUFFICIENT_EVIDENCE": "Insufficient evidence from both reads",
    "HIGHER_QUALITY_FORWARD": "Forward read has stronger evidence",
    "HIGHER_QUALITY_REVERSE": "Reverse read has stronger evidence",
    "UNRESOLVED_CONFLICT": "Forward and reverse reads disagree without enough evidence to choose one base",
    "ONE_SIDED_FORWARD": "Forward read only",
    "ONE_SIDED_REVERSE": "Reverse read only",
    "LOW_QUALITY": "Available evidence is too low quality",
    "GAP_ONLY": "No base is available from either read at this alignment column",
    "AMBIGUOUS_INPUT": "Ambiguous input evidence",
}

_SOURCE_LABELS = {
    "FORWARD": "Forward read",
    "REVERSE": "Reverse read",
    "BOTH": "Both reads",
    "NONE": "No read",
}


def decision_reason_label(reason: object | None) -> str:
    """Return a safe researcher-facing description of existing evidence."""

    value = getattr(reason, "value", reason)
    if value is None:
        return "Decision reason unavailable"
    return _REASON_LABELS.get(str(value), "Decision reason unavailable")


def decision_source_label(source: object | None) -> str:
    """Return the existing selected-source value without scientific inference."""

    value = getattr(source, "value", source)
    if value is None:
        return "Unavailable"
    return _SOURCE_LABELS.get(str(value), "Unavailable")
