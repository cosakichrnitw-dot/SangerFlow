"""Experimental, evidence-preserving pair consensus v2.

This module is deliberately separate from :mod:`core.consensus`.  It keeps
the v1 API and Review Engine intact while making a second, inspectable
consensus result for benchmark and human chromatogram review.

The Phred-derived likelihood values in this module are relative internal
evidence scores.  They are not calibrated posterior probabilities or a
sample-level quality decision.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log
from numbers import Integral, Real
from typing import Optional, Sequence, Tuple

from core.assembly_models import PairAlignment
from core.consensus import AssemblyMetrics, DecisionReason, build_pair_consensus


_BASES = "ACGT"
_UNAMBIGUOUS_BASES = frozenset(_BASES)


class ConsensusV2DecisionReason(str, Enum):
    """Explain a v2 base selection without changing v1 reason values."""

    TWO_SIDED_AGREEMENT = "TWO_SIDED_AGREEMENT"
    TWO_SIDED_AGREEMENT_LOW_CONFIDENCE = "TWO_SIDED_AGREEMENT_LOW_CONFIDENCE"
    HIGHER_QUALITY_FORWARD = "HIGHER_QUALITY_FORWARD"
    HIGHER_QUALITY_REVERSE = "HIGHER_QUALITY_REVERSE"
    UNRESOLVED_CONFLICT_TIE = "UNRESOLVED_CONFLICT_TIE"
    INHERITED_ONE_SIDED = "INHERITED_ONE_SIDED"
    INHERITED_GAP = "INHERITED_GAP"
    INHERITED_AMBIGUOUS_INPUT = "INHERITED_AMBIGUOUS_INPUT"


class EvidenceContext(str, Enum):
    """The evidence shape at one alignment column."""

    TWO_SIDED_AGREEMENT = "TWO_SIDED_AGREEMENT"
    TWO_SIDED_CONFLICT = "TWO_SIDED_CONFLICT"
    ONE_SIDED = "ONE_SIDED"
    GAP_ONLY = "GAP_ONLY"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"


class ConfidenceLevel(str, Enum):
    """Qualitative, uncalibrated evidence label for human review."""

    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"
    UNRESOLVED = "UNRESOLVED"
    INHERITED = "INHERITED"


class SelectedSource(str, Enum):
    """Which read evidence supplied the reported v2 base."""

    FORWARD = "FORWARD"
    REVERSE = "REVERSE"
    BOTH = "BOTH"
    NONE = "NONE"


@dataclass(frozen=True)
class ConsensusV2Scoring:
    """Versioned engineering defaults for the isolated v2 candidate.

    ``extreme_low_quality`` is intentionally limited to a two-sided agreement
    safety case.  Its default makes the supplied Q2/Q3 example unresolved;
    it is not a validated scientific threshold.  ``confidence_reference``
    only labels evidence for display and never determines whether a two-sided
    base is returned.
    """

    extreme_low_quality: float = 3.0
    confidence_reference_quality: float = 20.0
    algorithm_version: str = "consensus-v2-experimental-0"

    def __post_init__(self) -> None:
        for name in ("extreme_low_quality", "confidence_reference_quality"):
            value = getattr(self, name)
            if not isinstance(value, Real) or not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be a finite number greater than or equal to zero")
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise ValueError("algorithm_version must be a non-empty string")


@dataclass(frozen=True)
class RelativePhredEvidence:
    """Relative log-likelihoods for A/C/G/T from two non-gap observations."""

    candidate_log_likelihoods: Tuple[float, float, float, float]
    winner_base: str
    runner_up_base: str
    evidence_margin: float

    def __post_init__(self) -> None:
        if len(self.candidate_log_likelihoods) != len(_BASES):
            raise ValueError("candidate_log_likelihoods must contain A/C/G/T values")
        if any(not isfinite(score) for score in self.candidate_log_likelihoods):
            raise ValueError("candidate_log_likelihoods must be finite")
        if self.winner_base not in _UNAMBIGUOUS_BASES:
            raise ValueError("winner_base must be A/C/G/T")
        if self.runner_up_base not in _UNAMBIGUOUS_BASES:
            raise ValueError("runner_up_base must be A/C/G/T")
        if self.winner_base == self.runner_up_base:
            raise ValueError("winner_base and runner_up_base must differ")
        if not isfinite(self.evidence_margin) or self.evidence_margin < 0:
            raise ValueError("evidence_margin must be a finite non-negative number")

    @property
    def scores_by_base(self):
        """Return a deterministic base-to-score display mapping."""

        return dict(zip(_BASES, self.candidate_log_likelihoods))


@dataclass(frozen=True)
class ConsensusV2Decision:
    """One v2 decision with all per-column evidence needed for review."""

    alignment_index: int
    consensus_base: str
    reason: ConsensusV2DecisionReason
    forward_base: Optional[str]
    reverse_base: Optional[str]
    forward_quality: Optional[float]
    reverse_quality: Optional[float]
    evidence_context: EvidenceContext
    confidence_level: ConfidenceLevel
    selected_source: SelectedSource
    quality_difference: Optional[float]
    evidence_margin: Optional[float]
    evidence: Optional[RelativePhredEvidence]
    legacy_reason: DecisionReason

    def __post_init__(self) -> None:
        if isinstance(self.alignment_index, bool) or not isinstance(
            self.alignment_index, Integral
        ) or self.alignment_index < 0:
            raise ValueError("alignment_index must be a non-negative integer")
        if not isinstance(self.consensus_base, str) or len(self.consensus_base) != 1:
            raise ValueError("consensus_base must be a one-character string")
        if not isinstance(self.reason, ConsensusV2DecisionReason):
            raise ValueError("reason must be a ConsensusV2DecisionReason")
        if not isinstance(self.evidence_context, EvidenceContext):
            raise ValueError("evidence_context must be an EvidenceContext")
        if not isinstance(self.confidence_level, ConfidenceLevel):
            raise ValueError("confidence_level must be a ConfidenceLevel")
        if not isinstance(self.selected_source, SelectedSource):
            raise ValueError("selected_source must be a SelectedSource")
        if not isinstance(self.legacy_reason, DecisionReason):
            raise ValueError("legacy_reason must be a DecisionReason")
        for name in ("forward_base", "reverse_base"):
            base = getattr(self, name)
            if base is not None and (not isinstance(base, str) or len(base) != 1):
                raise ValueError(f"{name} must be a one-character string or None")
        for name in ("forward_quality", "reverse_quality"):
            _validate_optional_non_negative_finite(name, getattr(self, name))
        _validate_optional_finite("quality_difference", self.quality_difference)
        _validate_optional_finite("evidence_margin", self.evidence_margin)
        if self.evidence is not None and not isinstance(
            self.evidence, RelativePhredEvidence
        ):
            raise ValueError("evidence must be a RelativePhredEvidence or None")
        if self.evidence is None and self.evidence_margin is not None:
            raise ValueError("evidence_margin requires evidence")
        if self.evidence is not None and self.evidence_margin != self.evidence.evidence_margin:
            raise ValueError("evidence_margin must match evidence")


@dataclass(frozen=True)
class ConsensusV2Result:
    """Immutable v2 sequence and decisions, separate from ``ConsensusResult``."""

    sequence: str
    decisions: Sequence[ConsensusV2Decision]
    metrics: AssemblyMetrics
    scoring: ConsensusV2Scoring

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, str):
            raise ValueError("sequence must be a string")
        decisions = tuple(self.decisions)
        if len(self.sequence) != len(decisions):
            raise ValueError("sequence and decisions lengths differ")
        for index, decision in enumerate(decisions):
            if not isinstance(decision, ConsensusV2Decision):
                raise ValueError("decisions must contain ConsensusV2Decision values")
            if decision.alignment_index != index:
                raise ValueError("decision alignment indexes must be contiguous and 0-based")
            if self.sequence[index] != decision.consensus_base:
                raise ValueError("sequence must match decision consensus bases")
        if not isinstance(self.metrics, AssemblyMetrics):
            raise ValueError("metrics must be an AssemblyMetrics")
        if not isinstance(self.scoring, ConsensusV2Scoring):
            raise ValueError("scoring must be a ConsensusV2Scoring")
        object.__setattr__(self, "decisions", decisions)


def build_pair_consensus_v2(
    pair_alignment: PairAlignment,
    scoring: Optional[ConsensusV2Scoring] = None,
) -> ConsensusV2Result:
    """Build an experimental two-sided evidence consensus without touching v1.

    Agreement and conflict columns with two unambiguous bases are evaluated by
    v2.  One-sided, gap-only, and IUPAC columns retain their existing v1
    outcomes, avoiding a policy change outside this implementation scope.
    """

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if scoring is None:
        scoring = ConsensusV2Scoring()
    if not isinstance(scoring, ConsensusV2Scoring):
        raise ValueError("scoring must be a ConsensusV2Scoring")

    legacy_result = build_pair_consensus(pair_alignment)
    decisions = []
    for column, legacy_decision in zip(pair_alignment.columns, legacy_result.decisions):
        forward_base, forward_quality = _column_evidence(
            pair_alignment.forward_view, column.forward
        )
        reverse_base, reverse_quality = _column_evidence(
            pair_alignment.reverse_view, column.reverse
        )
        decisions.append(
            _build_decision(
                column.alignment_index,
                forward_base,
                forward_quality,
                reverse_base,
                reverse_quality,
                legacy_decision.reason,
                legacy_decision.consensus_base,
                scoring,
            )
        )
    return ConsensusV2Result(
        sequence="".join(decision.consensus_base for decision in decisions),
        decisions=decisions,
        metrics=_build_metrics(decisions),
        scoring=scoring,
    )


def _build_decision(
    alignment_index,
    forward_base,
    forward_quality,
    reverse_base,
    reverse_quality,
    legacy_reason,
    legacy_base,
    scoring,
):
    if forward_base is None and reverse_base is None:
        return _inherited_decision(
            alignment_index, legacy_base, legacy_reason, forward_base, forward_quality,
            reverse_base, reverse_quality, EvidenceContext.GAP_ONLY,
            ConsensusV2DecisionReason.INHERITED_GAP, ConfidenceLevel.UNRESOLVED,
        )
    if forward_base is None or reverse_base is None:
        return _inherited_decision(
            alignment_index, legacy_base, legacy_reason, forward_base, forward_quality,
            reverse_base, reverse_quality, EvidenceContext.ONE_SIDED,
            ConsensusV2DecisionReason.INHERITED_ONE_SIDED, ConfidenceLevel.INHERITED,
        )
    if forward_base not in _UNAMBIGUOUS_BASES or reverse_base not in _UNAMBIGUOUS_BASES:
        return _inherited_decision(
            alignment_index, legacy_base, legacy_reason, forward_base, forward_quality,
            reverse_base, reverse_quality, EvidenceContext.AMBIGUOUS_INPUT,
            ConsensusV2DecisionReason.INHERITED_AMBIGUOUS_INPUT,
            ConfidenceLevel.UNRESOLVED,
        )

    evidence = _relative_phred_evidence(
        forward_base, forward_quality, reverse_base, reverse_quality
    )
    difference = forward_quality - reverse_quality
    if forward_base == reverse_base:
        if (
            forward_quality <= scoring.extreme_low_quality
            and reverse_quality <= scoring.extreme_low_quality
        ):
            return _two_sided_decision(
                alignment_index, "N", ConsensusV2DecisionReason.TWO_SIDED_AGREEMENT_LOW_CONFIDENCE,
                forward_base, forward_quality, reverse_base, reverse_quality, evidence,
                ConfidenceLevel.UNRESOLVED, SelectedSource.NONE, legacy_reason,
            )
        confidence = (
            ConfidenceLevel.HIGH
            if min(forward_quality, reverse_quality) >= scoring.confidence_reference_quality
            else ConfidenceLevel.MODERATE
        )
        return _two_sided_decision(
            alignment_index, forward_base, ConsensusV2DecisionReason.TWO_SIDED_AGREEMENT,
            forward_base, forward_quality, reverse_base, reverse_quality, evidence,
            confidence, SelectedSource.BOTH, legacy_reason,
        )

    if evidence.evidence_margin == 0:
        return _two_sided_decision(
            alignment_index, "N", ConsensusV2DecisionReason.UNRESOLVED_CONFLICT_TIE,
            forward_base, forward_quality, reverse_base, reverse_quality, evidence,
            ConfidenceLevel.UNRESOLVED, SelectedSource.NONE, legacy_reason,
        )
    selected_source = (
        SelectedSource.FORWARD
        if evidence.winner_base == forward_base
        else SelectedSource.REVERSE
    )
    selected_quality = (
        forward_quality if selected_source is SelectedSource.FORWARD else reverse_quality
    )
    reason = (
        ConsensusV2DecisionReason.HIGHER_QUALITY_FORWARD
        if selected_source is SelectedSource.FORWARD
        else ConsensusV2DecisionReason.HIGHER_QUALITY_REVERSE
    )
    confidence = (
        ConfidenceLevel.HIGH
        if selected_quality >= scoring.confidence_reference_quality
        else ConfidenceLevel.LOW
    )
    return _two_sided_decision(
        alignment_index, evidence.winner_base, reason, forward_base, forward_quality,
        reverse_base, reverse_quality, evidence, confidence, selected_source, legacy_reason,
    )


def _inherited_decision(
    alignment_index, consensus_base, legacy_reason, forward_base, forward_quality,
    reverse_base, reverse_quality, context, reason, confidence,
):
    selected_source = SelectedSource.NONE
    if consensus_base != "N" and consensus_base != "-":
        selected_source = (
            SelectedSource.FORWARD if forward_base is not None else SelectedSource.REVERSE
        )
    return ConsensusV2Decision(
        alignment_index=alignment_index,
        consensus_base=consensus_base,
        reason=reason,
        forward_base=forward_base,
        reverse_base=reverse_base,
        forward_quality=forward_quality,
        reverse_quality=reverse_quality,
        evidence_context=context,
        confidence_level=confidence,
        selected_source=selected_source,
        quality_difference=None,
        evidence_margin=None,
        evidence=None,
        legacy_reason=legacy_reason,
    )


def _two_sided_decision(
    alignment_index, consensus_base, reason, forward_base, forward_quality,
    reverse_base, reverse_quality, evidence, confidence, selected_source, legacy_reason,
):
    return ConsensusV2Decision(
        alignment_index=alignment_index,
        consensus_base=consensus_base,
        reason=reason,
        forward_base=forward_base,
        reverse_base=reverse_base,
        forward_quality=forward_quality,
        reverse_quality=reverse_quality,
        evidence_context=(
            EvidenceContext.TWO_SIDED_AGREEMENT
            if forward_base == reverse_base
            else EvidenceContext.TWO_SIDED_CONFLICT
        ),
        confidence_level=confidence,
        selected_source=selected_source,
        quality_difference=forward_quality - reverse_quality,
        evidence_margin=evidence.evidence_margin,
        evidence=evidence,
        legacy_reason=legacy_reason,
    )


def _relative_phred_evidence(forward_base, forward_quality, reverse_base, reverse_quality):
    scores = tuple(
        _observation_log_likelihood(forward_base, forward_quality, candidate)
        + _observation_log_likelihood(reverse_base, reverse_quality, candidate)
        for candidate in _BASES
    )
    ranking = sorted(range(len(_BASES)), key=lambda index: (-scores[index], index))
    winner, runner_up = ranking[:2]
    return RelativePhredEvidence(
        candidate_log_likelihoods=scores,
        winner_base=_BASES[winner],
        runner_up_base=_BASES[runner_up],
        evidence_margin=scores[winner] - scores[runner_up],
    )


def _observation_log_likelihood(observed_base, quality, candidate_base):
    if quality == 0:
        return log(0.25)
    error_probability = 10 ** (-quality / 10)
    probability = 1 - error_probability if observed_base == candidate_base else error_probability / 3
    return log(probability)


def _column_evidence(view, coordinate):
    if coordinate is None:
        return None, None
    index = coordinate.assembly_index
    return view.sequence[index].upper(), float(view.quality[index])


def _build_metrics(decisions):
    overlap_length = 0
    comparisons = 0
    matches = 0
    conflict_count = 0
    resolved_conflicts = 0
    one_sided = 0
    for decision in decisions:
        forward_base = decision.forward_base
        reverse_base = decision.reverse_base
        if forward_base is not None and reverse_base is not None:
            overlap_length += 1
            if forward_base in _UNAMBIGUOUS_BASES and reverse_base in _UNAMBIGUOUS_BASES:
                comparisons += 1
                if forward_base == reverse_base:
                    matches += 1
            if forward_base != reverse_base:
                conflict_count += 1
                if decision.consensus_base != "N":
                    resolved_conflicts += 1
        elif forward_base is not None or reverse_base is not None:
            one_sided += 1
    return AssemblyMetrics(
        overlap_length=overlap_length,
        overlap_identity=matches / comparisons if comparisons else 0.0,
        conflict_count=conflict_count,
        resolved_conflict_count=resolved_conflicts,
        unresolved_base_count=sum(decision.consensus_base == "N" for decision in decisions),
        one_sided_coverage_count=one_sided,
    )


def _validate_optional_non_negative_finite(name, value):
    if value is not None and (
        not isinstance(value, Real) or not isfinite(value) or value < 0
    ):
        raise ValueError(f"{name} must be a finite number greater than or equal to zero or None")


def _validate_optional_finite(name, value):
    if value is not None and (not isinstance(value, Real) or not isfinite(value)):
        raise ValueError(f"{name} must be a finite number or None")
