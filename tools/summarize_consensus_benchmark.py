#!/usr/bin/env python3
"""Summarize human annotations against isolated v1/v2 comparison changes.

This is an evaluation-only tool.  It reads an annotated comparison CSV and
rebuilds the six explicitly registered validation alignments only to recover
per-column evidence and region context.  It never changes consensus policy or
calls the Review Engine.
"""

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from tools.compare_consensus_v1_v2 import build_known_pair_comparisons


_REQUIRED_INPUT_COLUMNS = frozenset(
    (
        "sample_id",
        "alignment_column",
        "v1_base",
        "v2_base",
        "v1_reason",
        "v2_reason",
        "human_decision",
        "human_comment",
    )
)
_OUTPUT_COLUMNS = (
    "sample_id",
    "alignment_column",
    "v1_base",
    "v2_base",
    "v2_reason",
    "human_decision",
    "forward_quality",
    "reverse_quality",
    "quality_difference",
    "evidence_margin",
    "region_type",
    "accept_or_keep",
)
_STANDARD_DECISIONS = frozenset(("ACCEPT", "KEEP_N"))
_SEPARATOR = "=" * 60


def read_annotation_rows(path):
    """Load an annotated v1/v2 CSV and preserve future non-empty labels."""

    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = frozenset(reader.fieldnames or ())
        missing = _REQUIRED_INPUT_COLUMNS - columns
        if missing:
            raise ValueError("input CSV is missing columns: " + ", ".join(sorted(missing)))
        return tuple(reader)


def build_benchmark_records(annotation_rows, comparisons):
    """Join changed annotated rows to current v2 evidence and region metadata."""

    comparisons_by_sample = {comparison.sample_id: comparison for comparison in comparisons}
    records = []
    for row in annotation_rows:
        if row["v1_base"] == row["v2_base"]:
            continue
        sample_id = row["sample_id"]
        comparison = comparisons_by_sample.get(sample_id)
        if comparison is None:
            raise ValueError(
                f"sample_id {sample_id!r} is not one of the explicitly registered validation pairs"
            )
        index = _parse_alignment_index(row["alignment_column"])
        if index >= comparison.alignment.length:
            raise ValueError(f"alignment_column {index} is outside sample {sample_id}")
        v1 = comparison.v1_result.decisions[index]
        v2 = comparison.v2_result.decisions[index]
        if row["v1_base"] != v1.consensus_base or row["v2_base"] != v2.consensus_base:
            raise ValueError(
                f"CSV bases do not match the current comparison at {sample_id} column {index}"
            )
        if row["v1_reason"] != v1.reason.value or row["v2_reason"] != v2.reason.value:
            raise ValueError(
                f"CSV reasons do not match the current comparison at {sample_id} column {index}"
            )
        decision = (row.get("human_decision") or "").strip().upper()
        records.append(
            {
                "sample_id": sample_id,
                "alignment_column": index,
                "v1_base": v1.consensus_base,
                "v2_base": v2.consensus_base,
                "v2_reason": v2.reason.value,
                "human_decision": decision,
                "forward_quality": v2.forward_quality,
                "reverse_quality": v2.reverse_quality,
                "quality_difference": v2.quality_difference,
                "evidence_margin": v2.evidence_margin,
                "region_type": classify_region(comparison, index),
                "accept_or_keep": _accept_or_keep(decision),
            }
        )
    return tuple(records)


def summarize_records(records):
    """Return descriptive agreement metrics without claiming unavailable recall."""

    decision_counts = Counter(record["human_decision"] for record in records)
    accept_count = decision_counts["ACCEPT"]
    keep_count = decision_counts["KEEP_N"]
    labelled_count = accept_count + keep_count
    transitions = Counter(_transition_type(record) for record in records)
    by_reason = defaultdict(Counter)
    for record in records:
        by_reason[record["v2_reason"]]["total"] += 1
        if record["human_decision"] == "ACCEPT":
            by_reason[record["v2_reason"]]["ACCEPT"] += 1
        elif record["human_decision"] == "KEEP_N":
            by_reason[record["v2_reason"]]["KEEP_N"] += 1
        elif record["human_decision"]:
            by_reason[record["v2_reason"]]["OTHER"] += 1
        else:
            by_reason[record["v2_reason"]]["UNANNOTATED"] += 1
    return {
        "total_v2_changes": len(records),
        "ACCEPT": accept_count,
        "KEEP_N": keep_count,
        "precision": accept_count / labelled_count if labelled_count else None,
        "recall": None,
        "N_TO_BASE": transitions["N_TO_BASE"],
        "BASE_TO_BASE": transitions["BASE_TO_BASE"],
        "BASE_TO_N": transitions["BASE_TO_N"],
        "by_reason": dict(by_reason),
        "other_decisions": {
            label: count
            for label, count in decision_counts.items()
            if label and label not in _STANDARD_DECISIONS
        },
        "unannotated": decision_counts[""],
    }


def format_summary(summary):
    """Format a transparent evaluation report including the recall limitation."""

    precision = "not available" if summary["precision"] is None else f"{summary['precision']:.2%}"
    lines = [
        _SEPARATOR,
        "Consensus v1/v2 Human-Annotation Benchmark Summary",
        _SEPARATOR,
        f"total v2 changes: {summary['total_v2_changes']}",
        f"ACCEPT: {summary['ACCEPT']}",
        f"KEEP_N: {summary['KEEP_N']}",
        f"precision (ACCEPT / annotated changes): {precision}",
        "recall: not calculable from a changed-column CSV; false negatives are absent",
        f"N -> base: {summary['N_TO_BASE']}",
        f"base -> base: {summary['BASE_TO_BASE']}",
        f"base -> N: {summary['BASE_TO_N']}",
        "",
        "Decision type summary:",
    ]
    for reason in sorted(summary["by_reason"]):
        counts = summary["by_reason"][reason]
        lines.extend(
            (
                reason,
                f"  total: {counts['total']}",
                f"  ACCEPT: {counts['ACCEPT']}",
                f"  KEEP_N: {counts['KEEP_N']}",
            )
        )
    if summary["other_decisions"]:
        lines.append("Other human_decision labels: " + str(summary["other_decisions"]))
    if summary["unannotated"]:
        lines.append(f"Unannotated rows: {summary['unannotated']}")
    return "\n".join(lines)


def write_summary_csv(path, records):
    """Write quality/evidence/region records for ACCEPT versus KEEP_N analysis."""

    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def classify_region(comparison, alignment_index):
    """Classify a column from the actual coordinate-preserving alignment."""

    column = comparison.alignment.column_at(alignment_index)
    if column.forward is not None and column.reverse is not None:
        return "OVERLAP"
    overlap_indexes = [
        item.alignment_index
        for item in comparison.alignment.columns
        if item.forward is not None and item.reverse is not None
    ]
    if not overlap_indexes:
        return "UNRESOLVED_REGION"
    side = "FORWARD" if column.forward is not None else "REVERSE"
    if alignment_index < overlap_indexes[0] or alignment_index > overlap_indexes[-1]:
        return f"TERMINAL_ONE_SIDED_{side}"
    return f"INTERNAL_GAP_{side}"


def build_parser():
    parser = argparse.ArgumentParser(
        description="Summarize annotated v1/v2 consensus comparison CSV rows."
    )
    parser.add_argument("input_csv", help="Annotated consensus_v1_v2_comparison.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark_summary.csv"),
        help="CSV for quality/evidence/region analysis (default: benchmark_summary.csv)",
    )
    parser.add_argument(
        "--validation-directory",
        type=Path,
        default=REPOSITORY_ROOT / "validation_data",
        help="Directory containing the six explicitly registered validation pairs",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        annotations = read_annotation_rows(args.input_csv)
        comparisons = build_known_pair_comparisons(args.validation_directory)
        records = build_benchmark_records(annotations, comparisons)
        summary = summarize_records(records)
        row_count = write_summary_csv(args.output, records)
    except (OSError, ValueError, IndexError) as error:
        print(f"Benchmark summary failed: {error}", file=sys.stderr)
        return 2
    print(format_summary(summary))
    print(f"Wrote {row_count} rows to {args.output}")
    return 0


def _parse_alignment_index(value):
    try:
        index = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"alignment_column must be a non-negative integer: {value!r}") from error
    if index < 0:
        raise ValueError("alignment_column must be a non-negative integer")
    return index


def _accept_or_keep(decision):
    if decision == "ACCEPT":
        return "ACCEPT"
    if decision == "KEEP_N":
        return "KEEP_N"
    return "UNANNOTATED" if not decision else "OTHER"


def _transition_type(record):
    before, after = record["v1_base"], record["v2_base"]
    if before == "N" and after != "N":
        return "N_TO_BASE"
    if before != "N" and after == "N":
        return "BASE_TO_N"
    return "BASE_TO_BASE"


if __name__ == "__main__":
    raise SystemExit(main())
