#!/usr/bin/env python3
"""Inspect a baseline pair alignment without creating consensus data.

Usage:
    python tools/inspect_pair_alignment.py forward.ab1 reverse.ab1
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
from core.pair_alignment import (
    AmbiguousAlignmentWarning,
    NoCredibleOverlapError,
    align_pair,
)
from core.trimming import trim_sequence


_UNAMBIGUOUS_BASES = frozenset("ACGT")


def summarize_alignment(alignment):
    """Derive human-readable diagnostics from a ``PairAlignment`` only."""

    columns = alignment.columns
    paired_indexes = [
        index
        for index, column in enumerate(columns)
        if column.forward is not None and column.reverse is not None
    ]
    first_paired = paired_indexes[0]
    last_paired = paired_indexes[-1]

    overlap_length = len(paired_indexes)
    unambiguous_matches = 0
    mismatches = 0
    internal_gaps = 0
    forward_terminal_overhang = 0
    reverse_terminal_overhang = 0

    for index, column in enumerate(columns):
        forward_base = _base_for_column(alignment.forward_view.sequence, column.forward)
        reverse_base = _base_for_column(alignment.reverse_view.sequence, column.reverse)
        if column.forward is not None and column.reverse is not None:
            if forward_base in _UNAMBIGUOUS_BASES and reverse_base in _UNAMBIGUOUS_BASES:
                if forward_base == reverse_base:
                    unambiguous_matches += 1
                else:
                    mismatches += 1
        elif first_paired < index < last_paired:
            internal_gaps += 1
        elif column.forward is not None:
            forward_terminal_overhang += 1
        else:
            reverse_terminal_overhang += 1

    comparable_bases = unambiguous_matches + mismatches
    overlap_identity = (
        None
        if comparable_bases == 0
        else unambiguous_matches / comparable_bases * 100
    )
    return {
        "alignment_length": len(columns),
        "overlap_length": overlap_length,
        "unambiguous_match_count": unambiguous_matches,
        "mismatch_count": mismatches,
        "overlap_identity": overlap_identity,
        "internal_gap_count": internal_gaps,
        "forward_terminal_overhang_length": forward_terminal_overhang,
        "reverse_terminal_overhang_length": reverse_terminal_overhang,
        "first_paired_column": first_paired,
        "last_paired_column": last_paired,
    }


def aligned_text(alignment):
    """Return aligned Forward, marker, and Reverse strings for inspection."""

    forward = []
    reverse = []
    markers = []
    for column in alignment.columns:
        forward_base = _base_for_column(alignment.forward_view.sequence, column.forward)
        reverse_base = _base_for_column(alignment.reverse_view.sequence, column.reverse)
        forward.append(forward_base)
        reverse.append(reverse_base)
        markers.append(_marker(forward_base, reverse_base))
    return "".join(forward), "".join(markers), "".join(reverse)


def format_alignment(alignment, width):
    """Format a wrapped, 0-based alignment display."""

    forward, markers, reverse = aligned_text(alignment)
    lines = []
    for start in range(0, len(forward), width):
        end = min(start + width, len(forward))
        lines.extend(
            (
                f"column {start:>5}-{end - 1:<5} Forward  {forward[start:end]}",
                f"{'':25} marker   {markers[start:end]}",
                f"{'':25} Reverse  {reverse[start:end]}",
                "",
            )
        )
    return "\n".join(lines)


def format_coordinate(alignment, alignment_index):
    """Format raw-coordinate evidence for one 0-based alignment column."""

    column = alignment.column_at(alignment_index)
    return "\n".join(
        (
            f"Alignment column: {column.alignment_index}",
            _format_side("Forward", column.forward),
            _format_side("Reverse", column.reverse),
        )
    )


def inspect_pair(forward_path, reverse_path, width=80, selected_columns=None):
    """Load, trim, align, and return text diagnostics for two AB1 paths."""

    if width < 1:
        raise ValueError("width must be at least one")
    forward_read = read_ab1(forward_path)
    reverse_read = read_ab1(reverse_path)
    trim_sequence(forward_read)
    trim_sequence(reverse_read)
    forward_view = build_forward_assembly_view(forward_read)
    reverse_view = build_reverse_assembly_view(reverse_read)

    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always", AmbiguousAlignmentWarning)
        alignment = align_pair(forward_view, reverse_view)
    ambiguity_warning = any(
        issubclass(item.category, AmbiguousAlignmentWarning)
        for item in captured_warnings
    )

    summary = summarize_alignment(alignment)
    selected_columns = _selected_columns(alignment, summary, selected_columns)
    lines = [
        "Pair alignment inspection (baseline; no consensus is generated)",
        f"Forward filename: {forward_read.filename}",
        f"Reverse filename: {reverse_read.filename}",
        f"Forward raw length: {len(forward_read.sequence)}",
        f"Reverse raw length: {len(reverse_read.sequence)}",
        f"Forward trimmed length: {len(forward_read.trimmed_sequence)}",
        f"Reverse trimmed length: {len(reverse_read.trimmed_sequence)}",
        "Best score: unavailable (not exposed by the current align_pair API)",
        "Second-best score / score margin: unavailable (not exposed by the current align_pair API)",
        f"Alignment length: {summary['alignment_length']}",
        f"Overlap length: {summary['overlap_length']}",
        f"Unambiguous match count: {summary['unambiguous_match_count']}",
        f"Mismatch count: {summary['mismatch_count']}",
        "Overlap identity: " + _format_identity(summary["overlap_identity"]),
        f"Internal gap count: {summary['internal_gap_count']}",
        "Forward terminal overhang length: "
        f"{summary['forward_terminal_overhang_length']}",
        "Reverse terminal overhang length: "
        f"{summary['reverse_terminal_overhang_length']}",
        f"Ambiguity warning: {'yes' if ambiguity_warning else 'no'}",
        "Credible-overlap note: the current requirement of at least one A/C/G/T "
        "match is a structural minimum only, not a scientific quality criterion.",
        "",
        "Aligned sequences (| = A/C/G/T match, * = A/C/G/T mismatch, "
        "? = ambiguity-containing pair):",
        format_alignment(alignment, width),
        "Coordinate detail (0-based):",
    ]
    for alignment_index in selected_columns:
        lines.extend((format_coordinate(alignment, alignment_index), ""))
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inspect a Forward/Reverse AB1 pair alignment without consensus."
    )
    parser.add_argument("forward_ab1", help="Forward AB1 file path")
    parser.add_argument("reverse_ab1", help="Reverse AB1 file path")
    parser.add_argument(
        "--width",
        type=int,
        default=80,
        help="Alignment display width (default: 80)",
    )
    parser.add_argument(
        "--column",
        type=int,
        action="append",
        dest="columns",
        help="0-based alignment column to display; repeatable",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        print(
            inspect_pair(
                args.forward_ab1,
                args.reverse_ab1,
                width=args.width,
                selected_columns=args.columns,
            )
        )
    except (NoCredibleOverlapError, ValueError, IndexError, OSError) as error:
        print(f"Pair alignment inspection failed: {error}", file=sys.stderr)
        return 2
    return 0


def _base_for_column(sequence, coordinate):
    return "-" if coordinate is None else sequence[coordinate.assembly_index].upper()


def _marker(forward_base, reverse_base):
    if forward_base == "-" or reverse_base == "-":
        return " "
    if forward_base in _UNAMBIGUOUS_BASES and reverse_base in _UNAMBIGUOUS_BASES:
        return "|" if forward_base == reverse_base else "*"
    return "?"


def _format_side(name, coordinate):
    if coordinate is None:
        return f"{name}: gap"
    return (
        f"{name}: assembly index={coordinate.assembly_index}, "
        f"raw index={coordinate.raw_index}, "
        f"raw trace position={coordinate.raw_trace_position}"
    )


def _format_identity(identity):
    return "unavailable (no comparable A/C/G/T pairs)" if identity is None else f"{identity:.2f}%"


def _selected_columns(alignment, summary, requested_columns):
    if requested_columns:
        return requested_columns
    return sorted(
        {
            0,
            alignment.length - 1,
            summary["first_paired_column"],
            summary["last_paired_column"],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
