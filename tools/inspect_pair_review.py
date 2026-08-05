#!/usr/bin/env python3
"""Inspect the automated Review Engine result for two AB1 files.

Usage:
    python tools/inspect_pair_review.py forward.ab1 reverse.ab1
"""

import argparse
from pathlib import Path
import sys
import warnings


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.ab1_reader import read_ab1
from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from core.consensus import build_pair_consensus
from core.pair_alignment import (
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)
from core.review import evaluate_pair_consensus
from core.trimming import trim_sequence


_SEPARATOR = "=" * 50


def inspect_pair_review(forward_path, reverse_path):
    """Load, trim, align, build consensus, and evaluate the default review policy."""

    forward_read = read_ab1(forward_path)
    reverse_read = read_ab1(reverse_path)
    trim_sequence(forward_read)
    trim_sequence(reverse_read)
    forward_view = build_forward_assembly_view(forward_read)
    reverse_view = build_reverse_assembly_view(reverse_read)
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always", AmbiguousAlignmentWarning)
        alignment = align_pair(forward_view, reverse_view)
    consensus = build_pair_consensus(alignment)
    review = evaluate_pair_consensus(alignment, consensus)
    ambiguity_warning = any(
        issubclass(item.category, AmbiguousAlignmentWarning)
        for item in captured_warnings
    )
    return format_pair_review_inspection(
        forward_read, reverse_read, review, ambiguity_warning=ambiguity_warning
    )


def format_pair_review_inspection(
    forward_read, reverse_read, review_result, *, ambiguity_warning=False
):
    """Format an existing automated ``ReviewResult`` without re-evaluation."""

    metrics = review_result.metrics
    criteria = review_result.criteria
    reasons = [reason.value for reason in review_result.reasons]
    lines = [
        _SEPARATOR,
        "Pair Review Summary",
        _SEPARATOR,
        "Forward:",
        f"filename: {forward_read.filename}",
        f"raw length: {len(forward_read.sequence)}",
        f"trim length: {len(forward_read.trimmed_sequence)}",
        "",
        "Reverse:",
        f"filename: {reverse_read.filename}",
        f"raw length: {len(reverse_read.sequence)}",
        f"trim length: {len(reverse_read.trimmed_sequence)}",
        "",
        "Automated review:",
        f"status: {review_result.status.value}",
        f"evaluation source: {review_result.evaluation_source.value}",
        "reasons: " + (", ".join(reasons) if reasons else "none"),
        "alignment ambiguity warning during this run: "
        f"{'yes' if ambiguity_warning else 'no'} "
        "(not persisted or used by the current Review Engine)",
        "",
        "Metrics snapshot:",
        f"consensus length: {metrics.consensus_length}",
        f"overlap length: {metrics.overlap_length}",
        f"overlap identity: {metrics.overlap_identity * 100:.2f}%",
        f"unambiguous overlap count: {metrics.unambiguous_overlap_count}",
        f"conflict count: {metrics.conflict_count}",
        f"resolved conflict count: {metrics.resolved_conflict_count}",
        f"unresolved conflict count: {metrics.unresolved_conflict_count}",
        f"unresolved base count: {metrics.unresolved_base_count}",
        f"one-sided coverage count: {metrics.one_sided_coverage_count}",
        f"one-sided coverage fraction: {metrics.one_sided_coverage_fraction:.4f}",
        f"internal gap columns: {metrics.internal_gap_column_count}",
        f"internal gap events: {metrics.internal_gap_event_count}",
        f"low-quality consensus bases: {metrics.low_quality_consensus_base_count}",
        "",
        "Engineering-default criteria (not scientifically calibrated):",
        f"minimum overlap length: {criteria.minimum_overlap_length}",
        "minimum overlap length before FAIL: "
        f"{criteria.minimum_overlap_length_before_fail}",
        f"minimum overlap identity: {criteria.minimum_overlap_identity:.2f}",
        "minimum overlap identity before FAIL: "
        f"{criteria.minimum_overlap_identity_before_fail:.2f}",
        "maximum conflict count for PASS: "
        f"{criteria.maximum_conflict_count_for_pass}",
        "maximum conflict count before FAIL: "
        f"{criteria.maximum_conflict_count_before_fail}",
        "maximum unresolved bases for PASS: "
        f"{criteria.maximum_unresolved_base_count_for_pass}",
        "maximum unresolved bases before FAIL: "
        f"{criteria.maximum_unresolved_base_count_before_fail}",
        "maximum internal gap events for PASS: "
        f"{criteria.maximum_internal_gap_count_for_pass}",
        "maximum internal gap events before FAIL: "
        f"{criteria.maximum_internal_gap_count_before_fail}",
        "maximum one-sided coverage fraction for PASS: "
        f"{criteria.maximum_one_sided_coverage_fraction_for_pass:.2f}",
        "maximum one-sided coverage fraction before FAIL: "
        f"{criteria.maximum_one_sided_coverage_fraction_before_fail:.2f}",
        f"review if any unresolved base: {criteria.review_if_any_unresolved_base}",
        f"review if any internal gap: {criteria.review_if_any_internal_gap}",
        "review if resolved conflicts present: "
        f"{criteria.review_if_resolved_conflicts_present}",
        "review if low-quality consensus bases present: "
        f"{criteria.review_if_low_quality_consensus_bases_present}",
        f"fail if no unambiguous overlap: {criteria.fail_if_no_unambiguous_overlap}",
        _SEPARATOR,
    ]
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect automated pair-review results using the current defaults."
    )
    parser.add_argument("forward_ab1", help="Forward AB1 file path")
    parser.add_argument("reverse_ab1", help="Reverse AB1 file path")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        print(inspect_pair_review(args.forward_ab1, args.reverse_ab1))
    except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
        print(f"Pair review inspection failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
