#!/usr/bin/env python3
"""Inspect per-column pair-consensus decisions for two AB1 files.

Usage:
    python tools/inspect_pair_consensus.py forward.ab1 reverse.ab1
"""

import argparse
from collections import Counter
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
from core.consensus import DecisionReason, build_pair_consensus
from core.pair_alignment import (
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)
from core.trimming import trim_sequence
from tools.inspect_pair_alignment import summarize_alignment


_DISPLAY_REASONS = (
    DecisionReason.BOTH_AGREE,
    DecisionReason.HIGHER_QUALITY_FORWARD,
    DecisionReason.HIGHER_QUALITY_REVERSE,
    DecisionReason.ONE_SIDED_FORWARD,
    DecisionReason.ONE_SIDED_REVERSE,
    DecisionReason.UNRESOLVED_CONFLICT,
    DecisionReason.LOW_QUALITY,
    DecisionReason.AMBIGUOUS_INPUT,
    DecisionReason.GAP_ONLY,
)
_SEPARATOR = "=" * 50
_DECISION_SEPARATOR = "-" * 36


def inspect_pair_consensus(forward_path, reverse_path, show_decisions=False, only_conflicts=False):
    """Load, trim, align, build consensus, and return diagnostic text only."""

    forward_read = read_ab1(forward_path)
    reverse_read = read_ab1(reverse_path)
    trim_sequence(forward_read)
    trim_sequence(reverse_read)
    forward_view = build_forward_assembly_view(forward_read)
    reverse_view = build_reverse_assembly_view(reverse_read)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AmbiguousAlignmentWarning)
        alignment = align_pair(forward_view, reverse_view)
    consensus = build_pair_consensus(alignment)
    return format_pair_consensus_inspection(
        forward_read,
        reverse_read,
        alignment,
        consensus,
        show_decisions=show_decisions,
        only_conflicts=only_conflicts,
    )


def format_pair_consensus_inspection(
    forward_read,
    reverse_read,
    alignment,
    consensus,
    *,
    show_decisions=False,
    only_conflicts=False,
):
    """Format diagnostics from public alignment and consensus result values."""

    if only_conflicts:
        show_decisions = True
    alignment_summary = summarize_alignment(alignment)
    metrics = consensus.metrics
    reason_counts = Counter(decision.reason for decision in consensus.decisions)
    lines = [
        _SEPARATOR,
        "Pair Summary",
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
        "Alignment:",
        f"alignment length: {alignment_summary['alignment_length']}",
        f"overlap length: {metrics.overlap_length}",
        f"identity: {metrics.overlap_identity * 100:.2f}%",
        f"internal gaps: {alignment_summary['internal_gap_count']}",
        "terminal overhang: "
        f"Forward={alignment_summary['forward_terminal_overhang_length']}, "
        f"Reverse={alignment_summary['reverse_terminal_overhang_length']}",
        "",
        "Consensus:",
        f"consensus length: {len(consensus.sequence)}",
        f"conflict count: {metrics.conflict_count}",
        f"resolved conflicts: {metrics.resolved_conflict_count}",
        f"unresolved bases (N): {metrics.unresolved_base_count}",
        f"one-sided coverage: {metrics.one_sided_coverage_count}",
        "",
        "DecisionReason counts:",
    ]
    lines.extend(
        f"{reason.value}: {reason_counts[reason]}" for reason in _DISPLAY_REASONS
    )
    lines.append(_SEPARATOR)

    if show_decisions:
        selected_decisions = (
            decision
            for decision in consensus.decisions
            if not only_conflicts or decision.reason is not DecisionReason.BOTH_AGREE
        )
        for decision in selected_decisions:
            lines.extend(("", format_decision(decision), _DECISION_SEPARATOR))
    return "\n".join(lines)


def format_decision(decision):
    """Format one ``ConsensusDecision`` without reading trace data."""

    return "\n".join(
        (
            f"Column {decision.alignment_index}",
            "",
            "Forward",
            f"base={_format_base(decision.forward_base)}",
            f"Q={_format_quality(decision.forward_quality)}",
            "",
            "Reverse",
            f"base={_format_base(decision.reverse_base)}",
            f"Q={_format_quality(decision.reverse_quality)}",
            "",
            "Consensus",
            f"base={decision.consensus_base}",
            "",
            "Reason",
            decision.reason.value,
        )
    )


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect Forward/Reverse pair-consensus decisions from two AB1 files."
    )
    parser.add_argument("forward_ab1", help="Forward AB1 file path")
    parser.add_argument("reverse_ab1", help="Reverse AB1 file path")
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--show-decisions",
        action="store_true",
        help="Display every ConsensusDecision",
    )
    display_group.add_argument(
        "--only-conflicts",
        action="store_true",
        help="Display decisions whose reason is not BOTH_AGREE",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        print(
            inspect_pair_consensus(
                args.forward_ab1,
                args.reverse_ab1,
                show_decisions=args.show_decisions,
                only_conflicts=args.only_conflicts,
            )
        )
    except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
        print(f"Pair consensus inspection failed: {error}", file=sys.stderr)
        return 2
    return 0


def _format_base(base):
    return "gap" if base is None else base


def _format_quality(quality):
    return "-" if quality is None else f"{quality:g}"


if __name__ == "__main__":
    raise SystemExit(main())
