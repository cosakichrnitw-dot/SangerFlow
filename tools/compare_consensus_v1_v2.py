#!/usr/bin/env python3
"""Inspect isolated v1/v2 pair-consensus differences for human review.

This script is diagnostic only.  It never promotes v2 bases, writes a FASTA,
or calls the Review Engine.
"""

import argparse
import csv
from dataclasses import dataclass
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
from core.consensus_v2 import (
    ConsensusV2DecisionReason,
    EvidenceContext,
    build_pair_consensus_v2,
)
from core.pair_alignment import (
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)
from core.trimming import trim_sequence


_KNOWN_VALIDATION_PAIRS = (
    ("IK345_COl-1", "IK345_COl-1_F.ab1", "IK345_COl-1_R.ab1"),
    ("IK346_COl-1", "IK346_COl-1_F.ab1", "IK346_COl-1_R.ab1"),
    ("IK347_COl-1", "IK347_COl-1_F.ab1", "IK347_COl-1_R.ab1"),
    ("IK348_COl-1", "IK348_COl-1_F.ab1", "IK348_COl-1_R.ab1"),
    ("IK349_COl-1", "IK349_COl-1_F.ab1", "IK349_COl-1_R.ab1"),
    ("IK350_COl-1", "IK350_COl-1_F.ab1", "IK350_COl-1_R.ab1"),
)
_CSV_COLUMNS = (
    "sample_id",
    "alignment_column",
    "v1_base",
    "v2_base",
    "v1_reason",
    "v2_reason",
    "forward_base",
    "forward_quality",
    "forward_raw_index",
    "forward_trace_position",
    "reverse_base",
    "reverse_quality",
    "reverse_raw_index",
    "reverse_trace_position",
)
_SEPARATOR = "=" * 60


@dataclass(frozen=True)
class ConsensusComparison:
    """One immutable v1/v2 comparison with the coordinate-preserving alignment."""

    sample_id: str
    alignment: object
    v1_result: object
    v2_result: object

    def __post_init__(self):
        if not isinstance(self.sample_id, str) or not self.sample_id:
            raise ValueError("sample_id must be a non-empty string")
        if self.alignment.length != len(self.v1_result.decisions):
            raise ValueError("alignment and v1 decision lengths differ")
        if self.alignment.length != len(self.v2_result.decisions):
            raise ValueError("alignment and v2 decision lengths differ")


def build_comparison(forward_path, reverse_path, sample_id=None):
    """Read, trim, align, and compare without mutating consensus outputs."""

    forward_read = read_ab1(forward_path)
    reverse_read = read_ab1(reverse_path)
    trim_sequence(forward_read)
    trim_sequence(reverse_read)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AmbiguousAlignmentWarning)
        alignment = align_pair(
            build_forward_assembly_view(forward_read),
            build_reverse_assembly_view(reverse_read),
        )
    return ConsensusComparison(
        sample_id=sample_id or Path(forward_path).stem,
        alignment=alignment,
        v1_result=build_pair_consensus(alignment),
        v2_result=build_pair_consensus_v2(alignment),
    )


def format_comparison(comparison, include_all=False):
    """Format changed columns by default, or all columns for audit mode."""

    selected = _selected_indexes(comparison, include_all)
    lines = [
        _SEPARATOR,
        "Consensus v1 / v2 Comparison",
        _SEPARATOR,
        f"Sample: {comparison.sample_id}",
        f"v1 N count: {comparison.v1_result.metrics.unresolved_base_count}",
        f"v2 N count: {comparison.v2_result.metrics.unresolved_base_count}",
        f"changed positions: {len(_changed_indexes(comparison))}",
        f"v2 accepted conflict count: {_accepted_conflict_count(comparison)}",
        f"v2 two-sided agreement count: {_two_sided_agreement_count(comparison)}",
        _SEPARATOR,
        f"Displayed columns: {len(selected)}",
    ]
    if not selected:
        lines.append("None")
    for index in selected:
        lines.extend(("", format_column(comparison, index), "-" * 40))
    return "\n".join(lines)


def format_column(comparison, alignment_index):
    """Format v1/v2 decisions and source coordinates for one alignment column."""

    v1 = comparison.v1_result.decisions[alignment_index]
    v2 = comparison.v2_result.decisions[alignment_index]
    column = comparison.alignment.column_at(alignment_index)
    return "\n".join(
        (
            f"column {alignment_index}",
            "v1:",
            f"base = {v1.consensus_base}",
            f"reason = {v1.reason.value}",
            "v2:",
            f"base = {v2.consensus_base}",
            f"reason = {v2.reason.value}",
            "Evidence:",
            "Forward:",
            f"base {format_value(v2.forward_base)}",
            f"quality {format_value(v2.forward_quality)}",
            f"raw index {coordinate_value(column.forward, 'raw_index')}",
            f"trace position {coordinate_value(column.forward, 'raw_trace_position')}",
            "Reverse:",
            f"base {format_value(v2.reverse_base)}",
            f"quality {format_value(v2.reverse_quality)}",
            f"raw index {coordinate_value(column.reverse, 'raw_index')}",
            f"trace position {coordinate_value(column.reverse, 'raw_trace_position')}",
        )
    )


def comparison_rows(comparison, include_all=False):
    """Build CSV-ready comparison rows; default rows are changed columns only."""

    rows = []
    for index in _selected_indexes(comparison, include_all):
        v1 = comparison.v1_result.decisions[index]
        v2 = comparison.v2_result.decisions[index]
        column = comparison.alignment.column_at(index)
        rows.append(
            {
                "sample_id": comparison.sample_id,
                "alignment_column": index,
                "v1_base": v1.consensus_base,
                "v2_base": v2.consensus_base,
                "v1_reason": v1.reason.value,
                "v2_reason": v2.reason.value,
                "forward_base": format_csv_value(v2.forward_base),
                "forward_quality": format_csv_value(v2.forward_quality),
                "forward_raw_index": coordinate_value(column.forward, "raw_index"),
                "forward_trace_position": coordinate_value(
                    column.forward, "raw_trace_position"
                ),
                "reverse_base": format_csv_value(v2.reverse_base),
                "reverse_quality": format_csv_value(v2.reverse_quality),
                "reverse_raw_index": coordinate_value(column.reverse, "raw_index"),
                "reverse_trace_position": coordinate_value(
                    column.reverse, "raw_trace_position"
                ),
            }
        )
    return rows


def write_comparison_csv(output_path, comparisons, include_all=False):
    """Write selected comparison rows without changing any consensus result."""

    rows = [
        row
        for comparison in comparisons
        for row in comparison_rows(comparison, include_all=include_all)
    ]
    with Path(output_path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def build_known_pair_comparisons(validation_directory=None):
    """Build comparisons for six explicitly registered pairs, never inferred ones."""

    directory = (
        REPOSITORY_ROOT / "validation_data"
        if validation_directory is None
        else Path(validation_directory)
    )
    return tuple(
        build_comparison(directory / forward_name, directory / reverse_name, sample_id)
        for sample_id, forward_name, reverse_name in _KNOWN_VALIDATION_PAIRS
    )


def format_benchmark(comparisons):
    """Format the requested one-line summary for each known validation pair."""

    lines = [
        _SEPARATOR,
        "Consensus v1 / v2 Known-Pair Benchmark",
        _SEPARATOR,
        "Sample\tv1 N count\tv2 N count\tchanged positions\t"
        "v2 accepted conflict count\tv2 two-sided agreement count",
    ]
    for comparison in comparisons:
        lines.append(
            "\t".join(
                (
                    comparison.sample_id,
                    str(comparison.v1_result.metrics.unresolved_base_count),
                    str(comparison.v2_result.metrics.unresolved_base_count),
                    str(len(_changed_indexes(comparison))),
                    str(_accepted_conflict_count(comparison)),
                    str(_two_sided_agreement_count(comparison)),
                )
            )
        )
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compare isolated v1 and v2 pair consensus results."
    )
    parser.add_argument("forward_ab1", nargs="?", help="Forward AB1 path")
    parser.add_argument("reverse_ab1", nargs="?", help="Reverse AB1 path")
    parser.add_argument(
        "--all", action="store_true", help="Display and export all alignment columns"
    )
    parser.add_argument(
        "--benchmark-known-pairs",
        action="store_true",
        help="Compare the six explicitly registered validation pairs",
    )
    parser.add_argument("--output", type=Path, help="Write selected rows as CSV")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.benchmark_known_pairs:
        if args.forward_ab1 or args.reverse_ab1:
            print(
                "--benchmark-known-pairs does not accept individual AB1 paths.",
                file=sys.stderr,
            )
            return 2
        try:
            comparisons = build_known_pair_comparisons()
        except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
            print(f"Consensus v1/v2 benchmark failed: {error}", file=sys.stderr)
            return 2
        print(format_benchmark(comparisons))
    else:
        if not args.forward_ab1 or not args.reverse_ab1:
            print("forward_ab1 and reverse_ab1 are required.", file=sys.stderr)
            return 2
        try:
            comparisons = (build_comparison(args.forward_ab1, args.reverse_ab1),)
        except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
            print(f"Consensus v1/v2 comparison failed: {error}", file=sys.stderr)
            return 2
        print(format_comparison(comparisons[0], include_all=args.all))
    if args.output is not None:
        row_count = write_comparison_csv(args.output, comparisons, include_all=args.all)
        print(f"Wrote {row_count} CSV rows to {args.output}")
    return 0


def _selected_indexes(comparison, include_all):
    if include_all:
        return tuple(range(comparison.alignment.length))
    return _changed_indexes(comparison)


def _changed_indexes(comparison):
    return tuple(
        index
        for index, (v1, v2) in enumerate(
            zip(comparison.v1_result.decisions, comparison.v2_result.decisions)
        )
        if v1.consensus_base != v2.consensus_base
    )


def _accepted_conflict_count(comparison):
    return sum(
        decision.reason
        in (
            ConsensusV2DecisionReason.HIGHER_QUALITY_FORWARD,
            ConsensusV2DecisionReason.HIGHER_QUALITY_REVERSE,
        )
        for decision in comparison.v2_result.decisions
    )


def _two_sided_agreement_count(comparison):
    return sum(
        decision.evidence_context is EvidenceContext.TWO_SIDED_AGREEMENT
        for decision in comparison.v2_result.decisions
    )


def coordinate_value(coordinate, attribute):
    return "None" if coordinate is None else getattr(coordinate, attribute)


def format_value(value):
    return "None" if value is None else value


def format_csv_value(value):
    return "" if value is None else value


if __name__ == "__main__":
    raise SystemExit(main())
