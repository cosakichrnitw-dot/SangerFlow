"""Experimental shadow evidence for a future pair-consensus v2.

This module never changes ``build_pair_consensus`` or its returned
``ConsensusResult``.  It calculates a two-sided-agreement evidence model in
parallel so curated benchmarks can compare a possible v2 policy with v1.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log
from numbers import Real
from typing import Optional, Sequence, Tuple

from core.assembly_models import PairAlignment
from core.consensus import ConsensusDecision, ConsensusResult, DecisionReason, build_pair_consensus


_BASES = "ACGT"
_UNAMBIGUOUS_BASES = frozenset(_BASES)


class ExperimentalDecisionReason(str, Enum):
    """Reasons for v2 shadow evidence; existing v1 reasons remain unchanged."""

    OUT_OF_SCOPE_V1_UNCHANGED = "OUT_OF_SCOPE_V1_UNCHANGED"
    TWO_SIDED_AGREEMENT_COMBINED = "TWO_SIDED_AGREEMENT_COMBINED"
    TWO_SIDED_AGREEMENT_INSUFFICIENT_EVIDENCE = (
        "TWO_SIDED_AGREEMENT_INSUFFICIENT_EVIDENCE"
    )
    CONFLICT_HIGHER_LIKELIHOOD_FORWARD = "CONFLICT_HIGHER_LIKELIHOOD_FORWARD"
    CONFLICT_HIGHER_LIKELIHOOD_REVERSE = "CONFLICT_HIGHER_LIKELIHOOD_REVERSE"
    CONFLICT_HIGH_QUALITY_UNRESOLVED = "CONFLICT_HIGH_QUALITY_UNRESOLVED"
    TERMINAL_ONE_SIDED_FORWARD = "TERMINAL_ONE_SIDED_FORWARD"
    TERMINAL_ONE_SIDED_REVERSE = "TERMINAL_ONE_SIDED_REVERSE"
    TERMINAL_ONE_SIDED_INSUFFICIENT_EVIDENCE = (
        "TERMINAL_ONE_SIDED_INSUFFICIENT_EVIDENCE"
    )
    INTERNAL_GAP_ONE_SIDED_FORWARD = "INTERNAL_GAP_ONE_SIDED_FORWARD"
    INTERNAL_GAP_ONE_SIDED_REVERSE = "INTERNAL_GAP_ONE_SIDED_REVERSE"
    INTERNAL_GAP_INSUFFICIENT_EVIDENCE = "INTERNAL_GAP_INSUFFICIENT_EVIDENCE"
    IUPAC_AMBIGUITY_UNRESOLVED = "IUPAC_AMBIGUITY_UNRESOLVED"


@dataclass(frozen=True)
class ExperimentalPromotionPolicy:
    """Explicit benchmark-only gates for promoting a shadow v2 base.

    This class intentionally has no defaults.  Callers must choose and record
    values from a benchmark; the values are not Review criteria.
    """

    minimum_individual_quality: float
    minimum_evidence_margin: float

    def __post_init__(self) -> None:
        _require_non_negative_finite(
            "minimum_individual_quality", self.minimum_individual_quality
        )
        _require_non_negative_finite(
            "minimum_evidence_margin", self.minimum_evidence_margin
        )


@dataclass(frozen=True)
class ExperimentalConsensusParameters:
    """Versioned configuration for a shadow calculation, not production policy."""

    algorithm_version: str = "consensus-v2-shadow-0"
    promotion_policy: Optional[ExperimentalPromotionPolicy] = None

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm_version, str) or not self.algorithm_version:
            raise ValueError("algorithm_version must be a non-empty string")
        if self.promotion_policy is not None and not isinstance(
            self.promotion_policy, ExperimentalPromotionPolicy
        ):
            raise ValueError("promotion_policy must be an ExperimentalPromotionPolicy or None")


@dataclass(frozen=True)
class CombinedPhredEvidence:
    """Relative log-likelihood evidence for one two-sided A/C/G/T agreement.

    Scores are internal comparison values derived from the supplied Phred
    values.  They are not calibrated posterior probabilities.
    """

    candidate_log_likelihoods: Tuple[float, float, float, float]
    winner_base: str
    runner_up_base: str
    evidence_margin: float

    def __post_init__(self) -> None:
        if len(self.candidate_log_likelihoods) != len(_BASES):
            raise ValueError("candidate_log_likelihoods must contain A/C/G/T values")
        if any(not isfinite(value) for value in self.candidate_log_likelihoods):
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
        """Return a deterministic A/C/G/T score mapping for display code."""

        return dict(zip(_BASES, self.candidate_log_likelihoods))


@dataclass(frozen=True)
class ExperimentalConsensusDecision:
    """One shadow-v2 decision linked to an unchanged v1 decision."""

    alignment_index: int
    v1_decision: ConsensusDecision
    candidate_base: str
    proposed_base: Optional[str]
    reason: ExperimentalDecisionReason
    evidence: Optional[CombinedPhredEvidence]

    def __post_init__(self) -> None:
        if self.alignment_index != self.v1_decision.alignment_index:
            raise ValueError("alignment_index must match v1_decision")
        if not isinstance(self.candidate_base, str) or len(self.candidate_base) != 1:
            raise ValueError("candidate_base must be a one-character string")
        if self.proposed_base is not None and self.proposed_base not in _UNAMBIGUOUS_BASES:
            raise ValueError("proposed_base must be A/C/G/T or None")
        if not isinstance(self.reason, ExperimentalDecisionReason):
            raise ValueError("reason must be an ExperimentalDecisionReason")
        if self.evidence is not None and not isinstance(
            self.evidence, CombinedPhredEvidence
        ):
            raise ValueError("evidence must be a CombinedPhredEvidence or None")

    @property
    def changed_from_v1(self) -> bool:
        """Whether a configured experimental policy changed this candidate base."""

        return self.candidate_base != self.v1_decision.consensus_base


@dataclass(frozen=True)
class ExperimentalConsensusCandidateResult:
    """Immutable shadow comparison container; never a production consensus."""

    v1_result: ConsensusResult
    candidate_sequence: str
    decisions: Sequence[ExperimentalConsensusDecision]
    parameters: ExperimentalConsensusParameters

    def __post_init__(self) -> None:
        decisions = tuple(self.decisions)
        if len(self.candidate_sequence) != len(decisions):
            raise ValueError("candidate_sequence and decisions lengths differ")
        if len(self.v1_result.sequence) != len(decisions):
            raise ValueError("v1_result and decisions lengths differ")
        for index, decision in enumerate(decisions):
            if decision.alignment_index != index:
                raise ValueError("decision alignment indexes must be contiguous and 0-based")
            if self.candidate_sequence[index] != decision.candidate_base:
                raise ValueError("candidate_sequence must match decision candidate bases")
        if not isinstance(self.parameters, ExperimentalConsensusParameters):
            raise ValueError("parameters must be ExperimentalConsensusParameters")
        object.__setattr__(self, "decisions", decisions)

    @property
    def changed_positions(self):
        """Return 0-based columns where the shadow candidate differs from v1."""

        return tuple(
            decision.alignment_index
            for decision in self.decisions
            if decision.changed_from_v1
        )


def evaluate_two_sided_agreement_candidate(
    forward_base: str,
    forward_quality: float,
    reverse_base: str,
    reverse_quality: float,
    parameters: Optional[ExperimentalConsensusParameters] = None,
) -> CombinedPhredEvidence:
    """Calculate relative evidence for one same-base two-sided observation.

    This function deliberately makes no base-call decision.  It accepts only
    same, unambiguous A/C/G/T observations because conflicts, IUPAC, gaps,
    and one-sided coverage are outside the first shadow scope.
    """

    _validate_same_unambiguous_observations(
        forward_base, forward_quality, reverse_base, reverse_quality
    )
    if parameters is not None and not isinstance(
        parameters, ExperimentalConsensusParameters
    ):
        raise ValueError("parameters must be ExperimentalConsensusParameters or None")

    forward_base = forward_base.upper()
    reverse_base = reverse_base.upper()

    scores = tuple(
        _observation_log_likelihood(forward_base, forward_quality, candidate)
        + _observation_log_likelihood(reverse_base, reverse_quality, candidate)
        for candidate in _BASES
    )
    ranking = sorted(range(len(_BASES)), key=lambda index: (-scores[index], index))
    winner_index, runner_up_index = ranking[:2]
    return CombinedPhredEvidence(
        candidate_log_likelihoods=scores,
        winner_base=_BASES[winner_index],
        runner_up_base=_BASES[runner_up_index],
        evidence_margin=scores[winner_index] - scores[runner_up_index],
    )


def build_pair_consensus_v2_candidate(
    pair_alignment: PairAlignment,
    parameters: Optional[ExperimentalConsensusParameters] = None,
) -> ExperimentalConsensusCandidateResult:
    """Build an isolated v2 shadow candidate without altering v1 behavior.

    By default, no base is promoted: ``candidate_sequence`` equals v1.  A
    caller may supply an explicit benchmark-only promotion policy to compare
    hypothetical N-to-base changes for eligible two-sided agreements.
    """

    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if parameters is None:
        parameters = ExperimentalConsensusParameters()
    if not isinstance(parameters, ExperimentalConsensusParameters):
        raise ValueError("parameters must be ExperimentalConsensusParameters")

    v1_result = build_pair_consensus(pair_alignment)
    decisions = []
    for v1_decision in v1_result.decisions:
        if _is_shadow_scope(v1_decision):
            evidence = evaluate_two_sided_agreement_candidate(
                v1_decision.forward_base,
                v1_decision.forward_quality,
                v1_decision.reverse_base,
                v1_decision.reverse_quality,
                parameters,
            )
            candidate_base = v1_decision.consensus_base
            reason = ExperimentalDecisionReason.TWO_SIDED_AGREEMENT_COMBINED
            if parameters.promotion_policy is not None:
                if _promotion_allowed(v1_decision, evidence, parameters.promotion_policy):
                    candidate_base = evidence.winner_base
                else:
                    reason = (
                        ExperimentalDecisionReason.TWO_SIDED_AGREEMENT_INSUFFICIENT_EVIDENCE
                    )
            decisions.append(
                ExperimentalConsensusDecision(
                    alignment_index=v1_decision.alignment_index,
                    v1_decision=v1_decision,
                    candidate_base=candidate_base,
                    proposed_base=evidence.winner_base,
                    reason=reason,
                    evidence=evidence,
                )
            )
        else:
            decisions.append(
                ExperimentalConsensusDecision(
                    alignment_index=v1_decision.alignment_index,
                    v1_decision=v1_decision,
                    candidate_base=v1_decision.consensus_base,
                    proposed_base=None,
                    reason=ExperimentalDecisionReason.OUT_OF_SCOPE_V1_UNCHANGED,
                    evidence=None,
                )
            )
    return ExperimentalConsensusCandidateResult(
        v1_result=v1_result,
        candidate_sequence="".join(decision.candidate_base for decision in decisions),
        decisions=decisions,
        parameters=parameters,
    )


def _is_shadow_scope(decision: ConsensusDecision) -> bool:
    return (
        decision.consensus_base == "N"
        and decision.reason is DecisionReason.LOW_QUALITY
        and decision.forward_base in _UNAMBIGUOUS_BASES
        and decision.reverse_base in _UNAMBIGUOUS_BASES
        and decision.forward_base == decision.reverse_base
    )


def _promotion_allowed(decision, evidence, policy) -> bool:
    return (
        decision.forward_quality >= policy.minimum_individual_quality
        and decision.reverse_quality >= policy.minimum_individual_quality
        and evidence.evidence_margin >= policy.minimum_evidence_margin
    )


def _observation_log_likelihood(observed_base, quality, candidate_base) -> float:
    """Return an uncalibrated observation score; Q0 is uninformative."""

    if quality == 0:
        return log(0.25)
    error_probability = 10 ** (-quality / 10)
    probability = 1 - error_probability if observed_base == candidate_base else error_probability / 3
    return log(probability)


def _validate_same_unambiguous_observations(
    forward_base, forward_quality, reverse_base, reverse_quality
) -> None:
    if not isinstance(forward_base, str) or forward_base.upper() not in _UNAMBIGUOUS_BASES:
        raise ValueError("forward_base must be an unambiguous A/C/G/T base")
    if not isinstance(reverse_base, str) or reverse_base.upper() not in _UNAMBIGUOUS_BASES:
        raise ValueError("reverse_base must be an unambiguous A/C/G/T base")
    if forward_base.upper() != reverse_base.upper():
        raise ValueError("two-sided agreement requires equal Forward and Reverse bases")
    _require_non_negative_finite("forward_quality", forward_quality)
    _require_non_negative_finite("reverse_quality", reverse_quality)


def _require_non_negative_finite(name, value) -> None:
    if not isinstance(value, Real) or not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite number greater than or equal to zero")
