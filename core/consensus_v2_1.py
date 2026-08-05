"""Shadow-only, evidence-preserving Forward/Reverse consensus v2.1.

This module does not replace or call ``build_pair_consensus``.  It is an
independent candidate calculation for benchmark comparison.  Only unambiguous
two-sided overlap columns use the v2.1 rules; all other columns reproduce the
current conservative v1 per-column behavior with v2.1 context metadata.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Integral, Real
from typing import Optional, Sequence

from core.assembly_models import PairAlignment


_UNAMBIGUOUS_BASES = frozenset("ACGT")


class ConsensusV21DecisionReason(str, Enum):
    """Explain a v2.1 base decision or conservative fallback."""

    TWO_SIDED_AGREEMENT = "TWO_SIDED_AGREEMENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    HIGHER_QUALITY_FORWARD = "HIGHER_QUALITY_FORWARD"
    HIGHER_QUALITY_REVERSE = "HIGHER_QUALITY_REVERSE"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    ONE_SIDED_FORWARD = "ONE_SIDED_FORWARD"
    ONE_SIDED_REVERSE = "ONE_SIDED_REVERSE"
    LOW_QUALITY = "LOW_QUALITY"
    GAP_ONLY = "GAP_ONLY"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"


class EvidenceContext(str, Enum):
    """Describe the alignment region and evidence shape for a decision."""

    OVERLAP = "OVERLAP"
    TERMINAL_ONE_SIDED_FORWARD = "TERMINAL_ONE_SIDED_FORWARD"
    TERMINAL_ONE_SIDED_REVERSE = "TERMINAL_ONE_SIDED_REVERSE"
    INTERNAL_GAP_FORWARD = "INTERNAL_GAP_FORWARD"
    INTERNAL_GAP_REVERSE = "INTERNAL_GAP_REVERSE"
    GAP_ONLY = "GAP_ONLY"
    IUPAC_AMBIGUITY = "IUPAC_AMBIGUITY"


class SelectedSource(str, Enum):
    """The read evidence selected for the v2.1 consensus base."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    BOTH = "BOTH"
    NONE = "NONE"


class ConfidenceLevel(str, Enum):
    """Qualitative, uncalibrated internal evidence label."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class ConsensusV21Scoring:
    """Versioned, uncalibrated v2.1 and legacy-equivalent defaults.

    ``extreme_low_quality`` is the only v2.1 gate for two-sided agreement.
    It is an engineering default based on the Q2/Q3 design example, not a
    scientific or calibrated threshold.  The legacy values reproduce v1's
    default fallback policy and are used only to calculate an internal change
    count without invoking v1.
    """

    extreme_low_quality: float = 3.0
    legacy_minimum_usable_quality: float = 20.0
    legacy_minimum_quality_difference: float = 10.0
    confidence_reference_quality: float = 20.0
    algorithm_version: str = "consensus-v2.1-shadow-0"

    def __post_init__(self) -> None:
        for name in (
            "extreme_low_quality",
            "legacy_minimum_usable_quality",
            "legacy_minimum_quality_difference",
            "confidence_reference_quality",
        ):
            value = getattr(self, name)
            if not isinstance(value, Real) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite number greater than or equal to zero")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise ValueError("algorithm_version must be a non-empty string")


@dataclass(frozen=True)
class ConsensusV21Decision:
    """One coordinate-addressable v2.1 decision for a pair-alignment column.

    Raw trace positions are intentionally not copied: callers recover them
    through ``PairAlignment.column_at(alignment_index)`` and ``ReadCoordinate``.
    Confidence is a qualitative internal label, never an absolute probability.
    """

    alignment_index: int
    forward_base: Optional[str]
    forward_quality: Optional[float]
    reverse_base: Optional[str]
    reverse_quality: Optional[float]
    consensus_base: str
    decision_reason: ConsensusV21DecisionReason
    evidence_context: EvidenceContext
    selected_source: SelectedSource
    quality_difference: Optional[float]
    confidence_level: ConfidenceLevel

    def __post_init__(self) -> None:
        if isinstance(self.alignment_index, bool) or not isinstance(
            self.alignment_index, Integral
        ) or self.alignment_index < 0:
            raise ValueError("alignment_index must be a non-negative integer")
        if not isinstance(self.consensus_base, str) or len(self.consensus_base) != 1:
            raise ValueError("consensus_base must be a one-character string")
        if not isinstance(self.decision_reason, ConsensusV21DecisionReason):
            raise ValueError("decision_reason must be a ConsensusV21DecisionReason")
        if not isinstance(self.evidence_context, EvidenceContext):
            raise ValueError("evidence_context must be an EvidenceContext")
        if not isinstance(self.selected_source, SelectedSource):
            raise ValueError("selected_source must be a SelectedSource")
        if not isinstance(self.confidence_level, ConfidenceLevel):
            raise ValueError("confidence_level must be a ConfidenceLevel")
        for name in ("forward_base", "reverse_base"):
            base = getattr(self, name)
            if base is not None and (not isinstance(base, str) or len(base) != 1):
                raise ValueError(f"{name} must be a one-character string or None")
        for name in ("forward_quality", "reverse_quality", "quality_difference"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, Real) or not isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number or None")
        for name in ("forward_quality", "reverse_quality"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be greater than or equal to zero")


@dataclass(frozen=True)
class ConsensusV21Metrics:
    """Descriptive shadow metrics; no PASS/REVIEW/FAIL interpretation."""

    total_columns: int
    changed_from_v1_count: int
    n_count: int
    conflict_count: int
    agreement_count: int

    def __post_init__(self) -> None:
        for name in (
            "total_columns",
            "changed_from_v1_count",
            "n_count",
            "conflict_count",
            "agreement_count",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")


@dataclass(frozen=True)
class ConsensusV21Result:
    """Independent v2.1 shadow sequence, decisions, metrics, and settings."""

    consensus_sequence: str
    decisions: Sequence[ConsensusV21Decision]
    metrics: ConsensusV21Metrics
    algorithm_version: str
    scoring_parameters: ConsensusV21Scoring

    def __post_init__(self) -> None:
        if not isinstance(self.consensus_sequence, str):
            raise ValueError("consensus_sequence must be a string")
        decisions = tuple(self.decisions)
        if len(self.consensus_sequence) != len(decisions):
            raise ValueError("consensus_sequence and decisions lengths differ")
        for index, decision in enumerate(decisions):
            if not isinstance(decision, ConsensusV21Decision):
                raise ValueError("decisions must contain ConsensusV21Decision values")
            if decision.alignment_index != index:
                raise ValueError("decision alignment indexes must be contiguous and 0-based")
            if self.consensus_sequence[index] != decision.consensus_base:
                raise ValueError("consensus_sequence must match decision bases")
        if not isinstance(self.metrics, ConsensusV21Metrics):
            raise ValueError("metrics must be a ConsensusV21Metrics")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise ValueError("algorithm_version must be a non-empty string")
        if not isinstance(self.scoring_parameters, ConsensusV21Scoring):
            raise ValueError("scoring_parameters must be a ConsensusV21Scoring")
        object.__setattr__(self, "decisions", decisions)


def build_pair_consensus_v2_1(
    pair_alignment: PairAlignment,
    scoring: Optional[ConsensusV21Scoring] = None,
) -> ConsensusV21Result:
    """Build an independent v2.1 candidate without changing production consensus.

    The function does not call v1.  ``changed_from_v1_count`` compares each
    v2.1 outcome to the embedded, default-equivalent v1 column policy recorded
    in ``ConsensusV21Scoring``.  A future comparison CLI remains responsible
    for comparing this result to an actual v1 invocation.
    """

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if scoring is None:
        scoring = ConsensusV21Scoring()
    if not isinstance(scoring, ConsensusV21Scoring):
        raise ValueError("scoring must be a ConsensusV21Scoring")

    contexts = _column_contexts(pair_alignment)
    decisions = []
    legacy_bases = []
    for column, context in zip(pair_alignment.columns, contexts):
        forward_base, forward_quality = _column_evidence(
            pair_alignment.forward_view, column.forward
        )
        reverse_base, reverse_quality = _column_evidence(
            pair_alignment.reverse_view, column.reverse
        )
        legacy_base, _ = _legacy_decision(
            forward_base, forward_quality, reverse_base, reverse_quality, scoring
        )
        decisions.append(
            _v21_decision(
                column.alignment_index,
                forward_base,
                forward_quality,
                reverse_base,
                reverse_quality,
                context,
                legacy_base,
                scoring,
            )
        )
        legacy_bases.append(legacy_base)

    return ConsensusV21Result(
        consensus_sequence="".join(decision.consensus_base for decision in decisions),
        decisions=decisions,
        metrics=ConsensusV21Metrics(
            total_columns=len(decisions),
            changed_from_v1_count=sum(
                decision.consensus_base != legacy_base
                for decision, legacy_base in zip(decisions, legacy_bases)
            ),
            n_count=sum(decision.consensus_base == "N" for decision in decisions),
            conflict_count=sum(
                decision.evidence_context is EvidenceContext.OVERLAP
                and decision.forward_base != decision.reverse_base
                for decision in decisions
            ),
            agreement_count=sum(
                decision.evidence_context is EvidenceContext.OVERLAP
                and decision.forward_base == decision.reverse_base
                for decision in decisions
            ),
        ),
        algorithm_version=scoring.algorithm_version,
        scoring_parameters=scoring,
    )


def _v21_decision(
    alignment_index,
    forward_base,
    forward_quality,
    reverse_base,
    reverse_quality,
    context,
    legacy_base,
    scoring,
):
    if (
        forward_base is not None
        and reverse_base is not None
        and (forward_base not in _UNAMBIGUOUS_BASES or reverse_base not in _UNAMBIGUOUS_BASES)
    ):
        context = EvidenceContext.IUPAC_AMBIGUITY
    if context is EvidenceContext.OVERLAP and (
        forward_base in _UNAMBIGUOUS_BASES and reverse_base in _UNAMBIGUOUS_BASES
    ):
        difference = forward_quality - reverse_quality
        if forward_base == reverse_base:
            if (
                forward_quality <= scoring.extreme_low_quality
                and reverse_quality <= scoring.extreme_low_quality
            ):
                return _decision(
                    alignment_index, forward_base, forward_quality, reverse_base,
                    reverse_quality, "N", ConsensusV21DecisionReason.INSUFFICIENT_EVIDENCE,
                    context, SelectedSource.NONE, difference, ConfidenceLevel.LOW,
                )
            confidence = (
                ConfidenceLevel.HIGH
                if min(forward_quality, reverse_quality)
                >= scoring.confidence_reference_quality
                else ConfidenceLevel.MEDIUM
            )
            return _decision(
                alignment_index, forward_base, forward_quality, reverse_base,
                reverse_quality, forward_base, ConsensusV21DecisionReason.TWO_SIDED_AGREEMENT,
                context, SelectedSource.BOTH, difference, confidence,
            )
        if difference == 0:
            return _decision(
                alignment_index, forward_base, forward_quality, reverse_base,
                reverse_quality, "N", ConsensusV21DecisionReason.UNRESOLVED_CONFLICT,
                context, SelectedSource.NONE, difference, ConfidenceLevel.LOW,
            )
        selected_forward = difference > 0
        selected_quality = forward_quality if selected_forward else reverse_quality
        return _decision(
            alignment_index, forward_base, forward_quality, reverse_base,
            reverse_quality,
            forward_base if selected_forward else reverse_base,
            (
                ConsensusV21DecisionReason.HIGHER_QUALITY_FORWARD
                if selected_forward
                else ConsensusV21DecisionReason.HIGHER_QUALITY_REVERSE
            ),
            context,
            SelectedSource.FORWARD if selected_forward else SelectedSource.REVERSE,
            difference,
            (
                ConfidenceLevel.HIGH
                if selected_quality >= scoring.confidence_reference_quality
                else ConfidenceLevel.LOW
            ),
        )

    legacy_base, legacy_reason = _legacy_decision(
        forward_base, forward_quality, reverse_base, reverse_quality, scoring
    )
    return _decision(
        alignment_index, forward_base, forward_quality, reverse_base, reverse_quality,
        legacy_base, legacy_reason, context, _legacy_selected_source(legacy_base, forward_base, reverse_base),
        None, ConfidenceLevel.LOW,
    )


def _legacy_decision(forward_base, forward_quality, reverse_base, reverse_quality, scoring):
    """Reproduce v1's default per-column decision without calling v1."""

    usable = scoring.legacy_minimum_usable_quality
    if forward_base is None and reverse_base is None:
        return "-", ConsensusV21DecisionReason.GAP_ONLY
    if forward_base is None:
        if reverse_base in _UNAMBIGUOUS_BASES and reverse_quality >= usable:
            return reverse_base, ConsensusV21DecisionReason.ONE_SIDED_REVERSE
        return (
            "N",
            (
                ConsensusV21DecisionReason.AMBIGUOUS_INPUT
                if reverse_base not in _UNAMBIGUOUS_BASES
                else ConsensusV21DecisionReason.LOW_QUALITY
            ),
        )
    if reverse_base is None:
        if forward_base in _UNAMBIGUOUS_BASES and forward_quality >= usable:
            return forward_base, ConsensusV21DecisionReason.ONE_SIDED_FORWARD
        return (
            "N",
            (
                ConsensusV21DecisionReason.AMBIGUOUS_INPUT
                if forward_base not in _UNAMBIGUOUS_BASES
                else ConsensusV21DecisionReason.LOW_QUALITY
            ),
        )
    if forward_base not in _UNAMBIGUOUS_BASES or reverse_base not in _UNAMBIGUOUS_BASES:
        return "N", ConsensusV21DecisionReason.AMBIGUOUS_INPUT
    if forward_base == reverse_base:
        if forward_quality >= usable or reverse_quality >= usable:
            return forward_base, ConsensusV21DecisionReason.TWO_SIDED_AGREEMENT
        return "N", ConsensusV21DecisionReason.LOW_QUALITY
    if forward_quality < usable and reverse_quality < usable:
        return "N", ConsensusV21DecisionReason.LOW_QUALITY
    difference = forward_quality - reverse_quality
    if abs(difference) < scoring.legacy_minimum_quality_difference:
        return "N", ConsensusV21DecisionReason.UNRESOLVED_CONFLICT
    if difference > 0 and forward_quality >= usable:
        return forward_base, ConsensusV21DecisionReason.HIGHER_QUALITY_FORWARD
    if difference < 0 and reverse_quality >= usable:
        return reverse_base, ConsensusV21DecisionReason.HIGHER_QUALITY_REVERSE
    return "N", ConsensusV21DecisionReason.LOW_QUALITY


def _column_contexts(pair_alignment):
    overlap_indexes = [
        column.alignment_index
        for column in pair_alignment.columns
        if column.forward is not None and column.reverse is not None
    ]
    first_overlap, last_overlap = overlap_indexes[0], overlap_indexes[-1]
    contexts = []
    for column in pair_alignment.columns:
        if column.forward is not None and column.reverse is not None:
            contexts.append(EvidenceContext.OVERLAP)
        elif column.forward is None and column.reverse is None:
            contexts.append(EvidenceContext.GAP_ONLY)
        else:
            side = "FORWARD" if column.forward is not None else "REVERSE"
            if column.alignment_index < first_overlap or column.alignment_index > last_overlap:
                contexts.append(EvidenceContext[f"TERMINAL_ONE_SIDED_{side}"])
            else:
                contexts.append(EvidenceContext[f"INTERNAL_GAP_{side}"])
    return tuple(contexts)


def _column_evidence(view, coordinate):
    if coordinate is None:
        return None, None
    index = coordinate.assembly_index
    return view.sequence[index].upper(), float(view.quality[index])


def _legacy_selected_source(consensus_base, forward_base, reverse_base):
    if consensus_base in ("N", "-"):
        return SelectedSource.NONE
    if forward_base == consensus_base and reverse_base == consensus_base:
        return SelectedSource.BOTH
    if forward_base == consensus_base:
        return SelectedSource.FORWARD
    return SelectedSource.REVERSE


def _decision(
    alignment_index, forward_base, forward_quality, reverse_base, reverse_quality,
    consensus_base, decision_reason, evidence_context, selected_source,
    quality_difference, confidence_level,
):
    return ConsensusV21Decision(
        alignment_index=alignment_index,
        forward_base=forward_base,
        forward_quality=forward_quality,
        reverse_base=reverse_base,
        reverse_quality=reverse_quality,
        consensus_base=consensus_base,
        decision_reason=decision_reason,
        evidence_context=evidence_context,
        selected_source=selected_source,
        quality_difference=quality_difference,
        confidence_level=confidence_level,
    )
