#!/usr/bin/env python3
"""Compare v1 pair consensus with the experimental v2 shadow candidate.

Usage:
    python tools/compare_consensus.py forward.ab1 reverse.ab1
"""

import argparse
from collections import Counter
import csv
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
from core.consensus_experimental import build_pair_consensus_v2_candidate
from core.pair_alignment import (
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)
from core.trimming import trim_sequence
from tools.inspect_pair_alignment import summarize_alignment


_SEPARATOR = "=" * 60
_BENCHMARK_COLUMNS = (
    "sample_id",
    "alignment_column",
    "legacy_base",
    "proposed_base",
    "forward_base",
    "forward_quality",
    "forward_raw_index",
    "forward_raw_trace_position",
    "reverse_base",
    "reverse_quality",
    "reverse_raw_index",
    "reverse_raw_trace_position",
    "evidence_margin",
    "human_decision",
    "human_comment",
)
_KNOWN_VALIDATION_PAIRS = (
    ("IK345_COl-1", "IK345_COl-1_F.ab1", "IK345_COl-1_R.ab1"),
    ("IK346_COl-1", "IK346_COl-1_F.ab1", "IK346_COl-1_R.ab1"),
    ("IK347_COl-1", "IK347_COl-1_F.ab1", "IK347_COl-1_R.ab1"),
    ("IK348_COl-1", "IK348_COl-1_F.ab1", "IK348_COl-1_R.ab1"),
    ("IK349_COl-1", "IK349_COl-1_F.ab1", "IK349_COl-1_R.ab1"),
    ("IK350_COl-1", "IK350_COl-1_F.ab1", "IK350_COl-1_R.ab1"),
)


def compare_pair_consensus(forward_path, reverse_path, display_mode="proposals", columns=None):
    """Run the existing pipeline and format an isolated v1/v2 comparison."""

    forward_read, reverse_read, alignment, v1_result, candidate_result = (
        _build_comparison_results(forward_path, reverse_path)
    )
    return format_consensus_comparison(
        forward_read,
        reverse_read,
        alignment,
        v1_result,
        candidate_result,
        display_mode=display_mode,
        columns=columns,
    )


def format_consensus_comparison(
    forward_read,
    reverse_read,
    alignment,
    v1_result,
    candidate_result,
    *,
    display_mode="proposals",
    columns=None,
):
    """Format existing v1 and shadow values without changing either result."""

    if candidate_result.v1_result != v1_result:
        raise ValueError("candidate v1_result does not match the supplied v1_result")
    selected = _select_decisions(candidate_result, display_mode, columns)
    alignment_summary = summarize_alignment(alignment)
    v1_reason_counts = Counter(decision.reason.value for decision in v1_result.decisions)
    experimental_reason_counts = Counter(
        decision.reason.value for decision in candidate_result.decisions
    )
    transitions = _transition_counts(candidate_result)
    lines = [
        _SEPARATOR,
        "Consensus v1 / Experimental v2 Shadow Comparison",
        _SEPARATOR,
        "Sample:",
        f"Forward: {forward_read.filename}",
        f"Reverse: {reverse_read.filename}",
        "",
        "Alignment:",
        f"alignment length: {alignment_summary['alignment_length']}",
        f"overlap length: {alignment_summary['overlap_length']}",
        f"overlap identity: {v1_result.metrics.overlap_identity * 100:.2f}%",
        "",
        "Consensus comparison:",
        f"v1 N count: {v1_result.metrics.unresolved_base_count}",
        "v2 two-sided agreement proposals: "
        f"{sum(decision.proposed_base is not None for decision in candidate_result.decisions)}",
        f"shadow sequence changes: {len(candidate_result.changed_positions)}",
        f"algorithm version: {candidate_result.parameters.algorithm_version}",
        "promotion policy: none (default shadow mode)",
        "",
        "v1 DecisionReason counts:",
    ]
    lines.extend(f"{reason}: {v1_reason_counts[reason]}" for reason in sorted(v1_reason_counts))
    lines.extend(("", "ExperimentalDecisionReason counts:"))
    lines.extend(
        f"{reason}: {experimental_reason_counts[reason]}"
        for reason in sorted(experimental_reason_counts)
    )
    lines.extend(
        (
            "",
            "Transition summary:",
            f"N -> Base: {transitions['N_TO_BASE']}",
            f"Base -> N: {transitions['BASE_TO_N']}",
            f"Base -> Different Base: {transitions['BASE_TO_DIFFERENT_BASE']}",
            f"Base -> Base (unchanged): {transitions['BASE_TO_BASE']}",
            f"N -> N (unchanged): {transitions['N_TO_N']}",
            _SEPARATOR,
            f"Displayed decisions ({display_mode}): {len(selected)}",
        )
    )
    if not selected:
        lines.append("None")
    for decision in selected:
        lines.extend(
            ("", format_comparison_decision(decision, alignment), "-" * 40)
        )
    return "\n".join(lines)


def format_comparison_decision(decision, alignment=None):
    """Format one existing shadow decision for human comparison."""

    v1 = decision.v1_decision
    forward_coordinate, reverse_coordinate = _coordinates_for_decision(
        decision, alignment
    )
    lines = [
        f"Alignment column: {decision.alignment_index}",
        f"Consensus index: {decision.alignment_index}",
        f"Forward: base={_format_base(v1.forward_base)}, Q={_format_quality(v1.forward_quality)}",
        "  coordinates: " + _format_coordinate(forward_coordinate),
        f"Reverse: base={_format_base(v1.reverse_base)}, Q={_format_quality(v1.reverse_quality)}",
        "  coordinates: " + _format_coordinate(reverse_coordinate),
        "v1:",
        f"  base={v1.consensus_base}",
        f"  reason={v1.reason.value}",
        "v2 candidate:",
        f"  candidate base={decision.candidate_base}",
        f"  proposed base={_format_base(decision.proposed_base)}",
        f"  reason={decision.reason.value}",
        f"  changed_from_v1={decision.changed_from_v1}",
    ]
    if decision.evidence is None:
        lines.extend(("  winner=unavailable", "  runner-up=unavailable", "  evidence margin=unavailable"))
    else:
        lines.extend(
            (
                f"  winner={decision.evidence.winner_base}",
                f"  runner-up={decision.evidence.runner_up_base}",
                f"  evidence margin={decision.evidence.evidence_margin:.6f}",
                "  candidate evidence: "
                + ", ".join(
                    f"{base}={score:.6f}"
                    for base, score in decision.evidence.scores_by_base.items()
                ),
            )
        )
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Compare v1 pair consensus with an experimental v2 shadow candidate."
    )
    parser.add_argument("forward_ab1", nargs="?", help="Forward AB1 file path")
    parser.add_argument("reverse_ab1", nargs="?", help="Reverse AB1 file path")
    parser.add_argument(
        "--benchmark-known-pairs",
        action="store_true",
        help="Export proposals for the six explicitly registered validation pairs",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="CSV output path for --benchmark-known-pairs",
    )
    display_group = parser.add_mutually_exclusive_group()
    display_group.add_argument(
        "--only-changes",
        action="store_const",
        const="changes",
        dest="display_mode",
        help="Display only columns whose candidate sequence differs from v1",
    )
    display_group.add_argument(
        "--all",
        action="store_const",
        const="all",
        dest="display_mode",
        help="Display every comparison decision",
    )
    display_group.add_argument(
        "--column",
        type=int,
        action="append",
        dest="columns",
        help="Display one 0-based alignment column; repeatable",
    )
    parser.set_defaults(display_mode="proposals", columns=None)
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
        if args.output is None:
            print("--benchmark-known-pairs requires --output PATH.csv", file=sys.stderr)
            return 2
        try:
            row_count = export_known_pair_benchmark(args.output)
        except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
            print(f"Consensus benchmark failed: {error}", file=sys.stderr)
            return 2
        print(f"Wrote {row_count} proposal rows to {args.output}")
        return 0
    if not args.forward_ab1 or not args.reverse_ab1:
        print("forward_ab1 and reverse_ab1 are required.", file=sys.stderr)
        return 2
    if args.output is not None:
        print("--output is only valid with --benchmark-known-pairs.", file=sys.stderr)
        return 2
    display_mode = "columns" if args.columns else args.display_mode
    try:
        print(
            compare_pair_consensus(
                args.forward_ab1,
                args.reverse_ab1,
                display_mode=display_mode,
                columns=args.columns,
            )
        )
    except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
        print(f"Consensus comparison failed: {error}", file=sys.stderr)
        return 2
    return 0


def _select_decisions(candidate_result, display_mode, columns):
    if display_mode == "proposals":
        return tuple(
            decision
            for decision in candidate_result.decisions
            if decision.proposed_base is not None
        )
    if display_mode == "changes":
        return tuple(
            decision for decision in candidate_result.decisions if decision.changed_from_v1
        )
    if display_mode == "all":
        return candidate_result.decisions
    if display_mode == "columns":
        requested = set(columns or ())
        return tuple(
            candidate_result.decisions[index]
            for index in sorted(requested)
            if 0 <= index < len(candidate_result.decisions)
        )
    raise ValueError("display_mode must be proposals, changes, all, or columns")


def export_known_pair_benchmark(output_path, validation_directory=None):
    """Write blank-review CSV rows for proposals from six explicit AB1 pairs.

    The pair list is intentionally fixed rather than inferred from filenames.
    Default shadow parameters are used, so this function never promotes a
    proposed base into a candidate sequence.
    """

    output_path = Path(output_path)
    validation_directory = (
        REPOSITORY_ROOT / "validation_data"
        if validation_directory is None
        else Path(validation_directory)
    )
    rows = []
    for sample_id, forward_name, reverse_name in _KNOWN_VALIDATION_PAIRS:
        forward_read, reverse_read, alignment, v1_result, candidate_result = (
            _build_comparison_results(
                validation_directory / forward_name, validation_directory / reverse_name
            )
        )
        del forward_read, reverse_read, v1_result
        rows.extend(
            _benchmark_rows_for_candidate(sample_id, alignment, candidate_result)
        )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_BENCHMARK_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _build_comparison_results(forward_path, reverse_path):
    forward_read = read_ab1(forward_path)
    reverse_read = read_ab1(reverse_path)
    trim_sequence(forward_read)
    trim_sequence(reverse_read)
    forward_view = build_forward_assembly_view(forward_read)
    reverse_view = build_reverse_assembly_view(reverse_read)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", AmbiguousAlignmentWarning)
        alignment = align_pair(forward_view, reverse_view)
    v1_result = build_pair_consensus(alignment)
    candidate_result = build_pair_consensus_v2_candidate(alignment)
    return forward_read, reverse_read, alignment, v1_result, candidate_result


def _benchmark_rows_for_candidate(sample_id, alignment, candidate_result):
    """Return editable CSV rows for proposed two-sided-agreement columns."""

    rows = []
    for decision in _select_decisions(candidate_result, "proposals", None):
        v1 = decision.v1_decision
        forward_coordinate, reverse_coordinate = _coordinates_for_decision(
            decision, alignment
        )
        rows.append(
            {
                "sample_id": sample_id,
                "alignment_column": decision.alignment_index,
                "legacy_base": v1.consensus_base,
                "proposed_base": decision.proposed_base,
                "forward_base": _csv_base(v1.forward_base),
                "forward_quality": _csv_quality(v1.forward_quality),
                "forward_raw_index": _csv_coordinate(forward_coordinate, "raw_index"),
                "forward_raw_trace_position": _csv_coordinate(
                    forward_coordinate, "raw_trace_position"
                ),
                "reverse_base": _csv_base(v1.reverse_base),
                "reverse_quality": _csv_quality(v1.reverse_quality),
                "reverse_raw_index": _csv_coordinate(reverse_coordinate, "raw_index"),
                "reverse_raw_trace_position": _csv_coordinate(
                    reverse_coordinate, "raw_trace_position"
                ),
                "evidence_margin": _csv_evidence_margin(decision),
                "human_decision": "",
                "human_comment": "",
            }
        )
    return rows


def _coordinates_for_decision(decision, alignment):
    if alignment is None:
        return None, None
    column = alignment.column_at(decision.alignment_index)
    return column.forward, column.reverse


def _transition_counts(candidate_result):
    counts = Counter()
    for decision in candidate_result.decisions:
        before = decision.v1_decision.consensus_base
        after = decision.candidate_base
        if before == "N" and after != "N":
            counts["N_TO_BASE"] += 1
        elif before != "N" and after == "N":
            counts["BASE_TO_N"] += 1
        elif before != "N" and after != "N" and before != after:
            counts["BASE_TO_DIFFERENT_BASE"] += 1
        elif before != "N":
            counts["BASE_TO_BASE"] += 1
        else:
            counts["N_TO_N"] += 1
    return counts


def _format_base(base):
    return "none" if base is None else base


def _format_quality(quality):
    return "-" if quality is None else f"{quality:g}"


def _format_coordinate(coordinate):
    if coordinate is None:
        return (
            "assembly index=None, trimmed index=None, raw index=None, "
            "raw trace position=None"
        )
    return (
        f"assembly index={coordinate.assembly_index}, "
        f"trimmed index={coordinate.trimmed_index}, "
        f"raw index={coordinate.raw_index}, "
        f"raw trace position={coordinate.raw_trace_position}"
    )


def _csv_base(base):
    return "" if base is None else base


def _csv_quality(quality):
    return "" if quality is None else quality


def _csv_coordinate(coordinate, attribute):
    return "" if coordinate is None else getattr(coordinate, attribute)


def _csv_evidence_margin(decision):
    return "" if decision.evidence is None else decision.evidence.evidence_margin


if __name__ == "__main__":
    raise SystemExit(main())
