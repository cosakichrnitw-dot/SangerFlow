"""Explainable automated evaluation of pair-alignment consensus results.

This module evaluates existing ``PairAlignment`` and ``ConsensusResult``
values only.  It never modifies an alignment, a consensus base, or either
input value object.
"""

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from numbers import Integral, Real
from typing import Sequence, Tuple

from core.assembly_models import PairAlignment
from core.consensus import ConsensusResult, DecisionReason


_UNAMBIGUOUS_BASES = frozenset("ACGT")


class ReviewStatus(str, Enum):
    """Automated assessment state, ordered by severity outside this enum."""

    PASS = "PASS"
    REVIEW = "REVIEW"
    FAIL = "FAIL"


class ReviewReason(str, Enum):
    """Explainable conditions detected from current alignment and consensus data."""

    OVERLAP_TOO_SHORT = "OVERLAP_TOO_SHORT"
    IDENTITY_TOO_LOW = "IDENTITY_TOO_LOW"
    NO_UNAMBIGUOUS_OVERLAP = "NO_UNAMBIGUOUS_OVERLAP"
    TOO_MANY_CONFLICTS = "TOO_MANY_CONFLICTS"
    UNRESOLVED_BASES_PRESENT = "UNRESOLVED_BASES_PRESENT"
    TOO_MANY_UNRESOLVED_BASES = "TOO_MANY_UNRESOLVED_BASES"
    INTERNAL_GAP_PRESENT = "INTERNAL_GAP_PRESENT"
    TOO_MANY_INTERNAL_GAPS = "TOO_MANY_INTERNAL_GAPS"
    ONE_SIDED_COVERAGE_HIGH = "ONE_SIDED_COVERAGE_HIGH"
    LOW_QUALITY_CONSENSUS_BASES_PRESENT = "LOW_QUALITY_CONSENSUS_BASES_PRESENT"


class ReviewEvaluationSource(str, Enum):
    """Source of a status, kept distinct from a future human override."""

    AUTOMATED = "AUTOMATED"


@dataclass(frozen=True)
class ReviewCriteria:
    """Configurable, uncalibrated engineering defaults for automated review.

    These values are intentionally not scientific or biological thresholds.
    They must be benchmarked with curated Sanger read pairs before use as a
    scientific acceptance policy.
    """

    minimum_overlap_length: int = 100
    minimum_overlap_length_before_fail: int = 20
    minimum_overlap_identity: float = 0.95
    minimum_overlap_identity_before_fail: float = 0.80
    maximum_conflict_count_for_pass: int = 0
    maximum_conflict_count_before_fail: int = 10
    maximum_unresolved_base_count_for_pass: int = 0
    maximum_unresolved_base_count_before_fail: int = 10
    maximum_internal_gap_count_for_pass: int = 0
    maximum_internal_gap_count_before_fail: int = 3
    maximum_one_sided_coverage_fraction_for_pass: float = 0.10
    maximum_one_sided_coverage_fraction_before_fail: float = 0.50
    review_if_any_unresolved_base: bool = True
    review_if_any_internal_gap: bool = True
    review_if_resolved_conflicts_present: bool = True
    review_if_low_quality_consensus_bases_present: bool = True
    fail_if_no_unambiguous_overlap: bool = True

    def __post_init__(self) -> None:
        _require_non_negative_integer("minimum_overlap_length", self.minimum_overlap_length)
        _require_non_negative_integer(
            "minimum_overlap_length_before_fail", self.minimum_overlap_length_before_fail
        )
        _require_non_negative_integer(
            "maximum_conflict_count_for_pass", self.maximum_conflict_count_for_pass
        )
        _require_non_negative_integer(
            "maximum_conflict_count_before_fail", self.maximum_conflict_count_before_fail
        )
        _require_non_negative_integer(
            "maximum_unresolved_base_count_for_pass",
            self.maximum_unresolved_base_count_for_pass,
        )
        _require_non_negative_integer(
            "maximum_unresolved_base_count_before_fail",
            self.maximum_unresolved_base_count_before_fail,
        )
        _require_non_negative_integer(
            "maximum_internal_gap_count_for_pass",
            self.maximum_internal_gap_count_for_pass,
        )
        _require_non_negative_integer(
            "maximum_internal_gap_count_before_fail",
            self.maximum_internal_gap_count_before_fail,
        )
        _require_fraction("minimum_overlap_identity", self.minimum_overlap_identity)
        _require_fraction(
            "minimum_overlap_identity_before_fail",
            self.minimum_overlap_identity_before_fail,
        )
        _require_fraction(
            "maximum_one_sided_coverage_fraction_for_pass",
            self.maximum_one_sided_coverage_fraction_for_pass,
        )
        _require_fraction(
            "maximum_one_sided_coverage_fraction_before_fail",
            self.maximum_one_sided_coverage_fraction_before_fail,
        )
        if self.minimum_overlap_length_before_fail > self.minimum_overlap_length:
            raise ValueError("minimum_overlap_length_before_fail cannot exceed minimum_overlap_length")
        if self.minimum_overlap_identity_before_fail > self.minimum_overlap_identity:
            raise ValueError("minimum_overlap_identity_before_fail cannot exceed minimum_overlap_identity")
        for pass_name, fail_name in (
            ("maximum_conflict_count_for_pass", "maximum_conflict_count_before_fail"),
            (
                "maximum_unresolved_base_count_for_pass",
                "maximum_unresolved_base_count_before_fail",
            ),
            (
                "maximum_internal_gap_count_for_pass",
                "maximum_internal_gap_count_before_fail",
            ),
            (
                "maximum_one_sided_coverage_fraction_for_pass",
                "maximum_one_sided_coverage_fraction_before_fail",
            ),
        ):
            if getattr(self, pass_name) > getattr(self, fail_name):
                raise ValueError(f"{pass_name} cannot exceed {fail_name}")


@dataclass(frozen=True)
class ReviewMetricsSnapshot:
    """The complete set of current metrics used by the automated policy."""

    consensus_length: int
    overlap_length: int
    overlap_identity: float
    unambiguous_overlap_count: int
    conflict_count: int
    resolved_conflict_count: int
    unresolved_conflict_count: int
    unresolved_base_count: int
    one_sided_coverage_count: int
    one_sided_coverage_fraction: float
    internal_gap_column_count: int
    internal_gap_event_count: int
    low_quality_consensus_base_count: int


@dataclass(frozen=True)
class ReviewResult:
    """Immutable automated review result; it contains no human override state."""

    status: ReviewStatus
    reasons: Sequence[ReviewReason]
    criteria: ReviewCriteria
    metrics: ReviewMetricsSnapshot
    evaluation_source: ReviewEvaluationSource = ReviewEvaluationSource.AUTOMATED

    def __post_init__(self) -> None:
        if not isinstance(self.status, ReviewStatus):
            raise ValueError("status must be a ReviewStatus")
        reasons = tuple(self.reasons)
        if any(not isinstance(reason, ReviewReason) for reason in reasons):
            raise ValueError("reasons must contain ReviewReason values")
        if len(set(reasons)) != len(reasons):
            raise ValueError("reasons must not contain duplicates")
        if not isinstance(self.criteria, ReviewCriteria):
            raise ValueError("criteria must be a ReviewCriteria")
        if not isinstance(self.metrics, ReviewMetricsSnapshot):
            raise ValueError("metrics must be a ReviewMetricsSnapshot")
        if self.evaluation_source is not ReviewEvaluationSource.AUTOMATED:
            raise ValueError("only automated review results are supported")
        object.__setattr__(self, "reasons", reasons)


def evaluate_pair_consensus(
    pair_alignment: PairAlignment,
    consensus_result: ConsensusResult,
    criteria: ReviewCriteria = None,
) -> ReviewResult:
    """Classify a pre-existing pair consensus as PASS, REVIEW, or FAIL.

    FAIL conditions take precedence over REVIEW conditions, which take
    precedence over PASS.  The function is deterministic and does not mutate
    either input.
    """

    _validate_inputs(pair_alignment, consensus_result)
    if criteria is None:
        criteria = ReviewCriteria()
    if not isinstance(criteria, ReviewCriteria):
        raise ValueError("criteria must be a ReviewCriteria")

    metrics = _build_metrics_snapshot(pair_alignment, consensus_result)
    fail_reasons = []
    review_reasons = []

    if criteria.fail_if_no_unambiguous_overlap and metrics.unambiguous_overlap_count == 0:
        fail_reasons.append(ReviewReason.NO_UNAMBIGUOUS_OVERLAP)
    if metrics.overlap_length < criteria.minimum_overlap_length_before_fail:
        fail_reasons.append(ReviewReason.OVERLAP_TOO_SHORT)
    elif metrics.overlap_length < criteria.minimum_overlap_length:
        review_reasons.append(ReviewReason.OVERLAP_TOO_SHORT)
    if metrics.overlap_identity < criteria.minimum_overlap_identity_before_fail:
        fail_reasons.append(ReviewReason.IDENTITY_TOO_LOW)
    elif metrics.overlap_identity < criteria.minimum_overlap_identity:
        review_reasons.append(ReviewReason.IDENTITY_TOO_LOW)
    _evaluate_conflicts(metrics, criteria, fail_reasons, review_reasons)
    _evaluate_unresolved_bases(metrics, criteria, fail_reasons, review_reasons)
    _evaluate_internal_gaps(metrics, criteria, fail_reasons, review_reasons)
    _evaluate_one_sided_coverage(metrics, criteria, fail_reasons, review_reasons)
    if (
        criteria.review_if_low_quality_consensus_bases_present
        and metrics.low_quality_consensus_base_count > 0
    ):
        review_reasons.append(ReviewReason.LOW_QUALITY_CONSENSUS_BASES_PRESENT)

    if fail_reasons:
        return ReviewResult(ReviewStatus.FAIL, _combine_reasons(fail_reasons, review_reasons), criteria, metrics)
    if review_reasons:
        return ReviewResult(ReviewStatus.REVIEW, tuple(review_reasons), criteria, metrics)
    return ReviewResult(ReviewStatus.PASS, (), criteria, metrics)


def _validate_inputs(pair_alignment, consensus_result) -> None:
    if not isinstance(pair_alignment, PairAlignment):
        raise ValueError("pair_alignment must be a PairAlignment")
    if not isinstance(consensus_result, ConsensusResult):
        raise ValueError("consensus_result must be a ConsensusResult")
    if not consensus_result.sequence:
        raise ValueError("consensus_result sequence must not be empty")
    if pair_alignment.length != len(consensus_result.decisions):
        raise ValueError("PairAlignment and ConsensusResult lengths differ")
    for column, decision in zip(pair_alignment.columns, consensus_result.decisions):
        forward_base, forward_quality = _side_evidence(pair_alignment.forward_view, column.forward)
        reverse_base, reverse_quality = _side_evidence(pair_alignment.reverse_view, column.reverse)
        if (
            decision.alignment_index != column.alignment_index
            or decision.forward_base != forward_base
            or decision.reverse_base != reverse_base
            or decision.forward_quality != forward_quality
            or decision.reverse_quality != reverse_quality
        ):
            raise ValueError("ConsensusResult decision evidence does not match PairAlignment")


def _build_metrics_snapshot(pair_alignment, consensus_result) -> ReviewMetricsSnapshot:
    metrics = consensus_result.metrics
    internal_gap_columns, internal_gap_events = _internal_gap_counts(pair_alignment)
    unambiguous_overlap_count = 0
    unresolved_conflict_count = 0
    low_quality_count = 0
    for decision in consensus_result.decisions:
        if (
            decision.forward_base in _UNAMBIGUOUS_BASES
            and decision.reverse_base in _UNAMBIGUOUS_BASES
        ):
            unambiguous_overlap_count += 1
        if decision.reason is DecisionReason.UNRESOLVED_CONFLICT:
            unresolved_conflict_count += 1
        if decision.reason is DecisionReason.LOW_QUALITY:
            low_quality_count += 1
    return ReviewMetricsSnapshot(
        consensus_length=len(consensus_result.sequence),
        overlap_length=metrics.overlap_length,
        overlap_identity=metrics.overlap_identity,
        unambiguous_overlap_count=unambiguous_overlap_count,
        conflict_count=metrics.conflict_count,
        resolved_conflict_count=metrics.resolved_conflict_count,
        unresolved_conflict_count=unresolved_conflict_count,
        unresolved_base_count=metrics.unresolved_base_count,
        one_sided_coverage_count=metrics.one_sided_coverage_count,
        one_sided_coverage_fraction=(
            metrics.one_sided_coverage_count / len(consensus_result.sequence)
        ),
        internal_gap_column_count=internal_gap_columns,
        internal_gap_event_count=internal_gap_events,
        low_quality_consensus_base_count=low_quality_count,
    )


def _internal_gap_counts(pair_alignment: PairAlignment) -> Tuple[int, int]:
    paired_indexes = [
        index
        for index, column in enumerate(pair_alignment.columns)
        if column.forward is not None and column.reverse is not None
    ]
    first_paired = paired_indexes[0]
    last_paired = paired_indexes[-1]
    internal_gap_columns = 0
    internal_gap_events = 0
    inside_gap = False
    for index in range(first_paired + 1, last_paired):
        column = pair_alignment.columns[index]
        is_gap = column.forward is None or column.reverse is None
        if is_gap:
            internal_gap_columns += 1
            if not inside_gap:
                internal_gap_events += 1
                inside_gap = True
        else:
            inside_gap = False
    return internal_gap_columns, internal_gap_events


def _side_evidence(view, coordinate):
    if coordinate is None:
        return None, None
    index = coordinate.assembly_index
    return view.sequence[index].upper(), float(view.quality[index])


def _evaluate_conflicts(metrics, criteria, fail_reasons, review_reasons) -> None:
    if metrics.conflict_count > criteria.maximum_conflict_count_before_fail:
        fail_reasons.append(ReviewReason.TOO_MANY_CONFLICTS)
    elif metrics.conflict_count > criteria.maximum_conflict_count_for_pass:
        review_reasons.append(ReviewReason.TOO_MANY_CONFLICTS)
    elif (
        criteria.review_if_resolved_conflicts_present
        and metrics.resolved_conflict_count > 0
    ):
        review_reasons.append(ReviewReason.TOO_MANY_CONFLICTS)


def _evaluate_unresolved_bases(metrics, criteria, fail_reasons, review_reasons) -> None:
    if metrics.unresolved_base_count > criteria.maximum_unresolved_base_count_before_fail:
        fail_reasons.append(ReviewReason.TOO_MANY_UNRESOLVED_BASES)
    elif metrics.unresolved_base_count > criteria.maximum_unresolved_base_count_for_pass:
        review_reasons.append(ReviewReason.UNRESOLVED_BASES_PRESENT)
    elif criteria.review_if_any_unresolved_base and metrics.unresolved_base_count > 0:
        review_reasons.append(ReviewReason.UNRESOLVED_BASES_PRESENT)


def _evaluate_internal_gaps(metrics, criteria, fail_reasons, review_reasons) -> None:
    if metrics.internal_gap_event_count > criteria.maximum_internal_gap_count_before_fail:
        fail_reasons.append(ReviewReason.TOO_MANY_INTERNAL_GAPS)
    elif metrics.internal_gap_event_count > criteria.maximum_internal_gap_count_for_pass:
        review_reasons.append(ReviewReason.INTERNAL_GAP_PRESENT)
    elif criteria.review_if_any_internal_gap and metrics.internal_gap_event_count > 0:
        review_reasons.append(ReviewReason.INTERNAL_GAP_PRESENT)


def _evaluate_one_sided_coverage(metrics, criteria, fail_reasons, review_reasons) -> None:
    if (
        metrics.one_sided_coverage_fraction
        > criteria.maximum_one_sided_coverage_fraction_before_fail
    ):
        fail_reasons.append(ReviewReason.ONE_SIDED_COVERAGE_HIGH)
    elif (
        metrics.one_sided_coverage_fraction
        > criteria.maximum_one_sided_coverage_fraction_for_pass
    ):
        review_reasons.append(ReviewReason.ONE_SIDED_COVERAGE_HIGH)


def _combine_reasons(fail_reasons, review_reasons):
    return tuple(dict.fromkeys((*fail_reasons, *review_reasons)))


def _require_non_negative_integer(name, value) -> None:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_fraction(name, value) -> None:
    if not isinstance(value, Real) or not isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be a finite value from 0.0 to 1.0")
