#!/usr/bin/env python3
"""Launch the read-only Multiple Consensus Alignment Viewer prototype.

FASTA input must already contain equally long, aligned consensus sequences.
The optional validation preview builds current v2.1 pair candidates, then
right-pads them only to exercise the GUI. That preview is not a biological
multiple sequence alignment and must not be used for analysis or export.

Usage:
    python -m tools.launch_multiple_consensus_viewer aligned_consensus.fasta
    python -m tools.launch_multiple_consensus_viewer sample1.fasta sample2.fasta
    python -m tools.launch_multiple_consensus_viewer --validation-known-pairs
"""

import argparse
from pathlib import Path
import sys
import tkinter as tk

from Bio import SeqIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from gui.multiple_consensus_viewer import (
    MultipleAlignmentViewModel,
    MultipleConsensusAlignmentWindow,
    build_multiple_alignment_view_model,
)
from tools.launch_consensus_viewer import build_view_model_from_ab1_pair


_KNOWN_VALIDATION_SAMPLE_IDS = (
    "IK345_COl-1",
    "IK346_COl-1",
    "IK347_COl-1",
    "IK348_COl-1",
    "IK349_COl-1",
    "IK350_COl-1",
)


def load_aligned_consensus_fasta(fasta_paths) -> list[dict[str, str]]:
    """Load consensus records from FASTA without performing alignment."""

    records = []
    for fasta_path in fasta_paths:
        path = Path(fasta_path)
        if not path.is_file():
            raise OSError(f"FASTA file does not exist: {path}")
        with path.open("r", encoding="utf-8") as handle:
            for record in SeqIO.parse(handle, "fasta"):
                sequence = str(record.seq).strip()
                if not sequence:
                    raise ValueError(f"FASTA record has an empty sequence: {record.id}")
                records.append({"sample_id": str(record.id), "sequence": sequence})
    if not records:
        raise ValueError("no FASTA consensus sequences were found")
    return records


def build_validation_preview_sequences(
    validation_directory: str | Path = "validation_data",
) -> list[dict[str, str]]:
    """Build a display-only, left-aligned preview from the six known AB1 pairs.

    The underlying pair candidates use the existing Single Consensus Review
    workflow. Their unequal lengths are padded with terminal gaps solely so
    this prototype can display multiple rows; this is not an alignment result.
    """

    directory = Path(validation_directory)
    records = []
    for sample_id in _KNOWN_VALIDATION_SAMPLE_IDS:
        forward_path = directory / f"{sample_id}_F.ab1"
        reverse_path = directory / f"{sample_id}_R.ab1"
        if not forward_path.is_file() or not reverse_path.is_file():
            raise OSError(
                f"validation pair is missing for {sample_id}: "
                f"{forward_path.name}, {reverse_path.name}"
            )
        view_model = build_view_model_from_ab1_pair(
            str(forward_path),
            str(reverse_path),
            sample_identifier=sample_id,
        )
        records.append(
            {"sample_id": sample_id, "sequence": view_model.consensus_sequence}
        )
    return _right_pad_for_display_preview(records)


def _right_pad_for_display_preview(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Pad unequal rows for a clearly non-analytical GUI preview only."""

    if not records:
        raise ValueError("at least one preview sequence is required")
    longest_length = max(len(record["sequence"]) for record in records)
    return [
        {
            "sample_id": record["sample_id"],
            "sequence": record["sequence"].ljust(longest_length, "-"),
        }
        for record in records
    ]


def build_view_model_from_fasta(fasta_paths) -> MultipleAlignmentViewModel:
    """Load caller-supplied aligned FASTA records into the GUI adapter."""

    return build_multiple_alignment_view_model(load_aligned_consensus_fasta(fasta_paths))


def show_multiple_consensus_viewer(
    view_model: MultipleAlignmentViewModel,
    *,
    root_factory=tk.Tk,
    window_factory=MultipleConsensusAlignmentWindow,
) -> None:
    """Show the prototype without importing Main Viewer or Single Viewer GUI."""

    root = root_factory()
    root.withdraw()
    window = window_factory(root, view_model)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Launch the read-only Multiple Consensus Alignment Viewer. "
            "FASTA input must already be aligned."
        )
    )
    parser.add_argument(
        "fasta_files",
        nargs="*",
        help="One or more FASTA files containing already aligned consensus sequences",
    )
    parser.add_argument(
        "--validation-known-pairs",
        action="store_true",
        help=(
            "Build the six validation_data v2.1 candidates and show a "
            "left-aligned, terminal-gap-padded GUI preview only"
        ),
    )
    parser.add_argument(
        "--validation-directory",
        default="validation_data",
        help="Directory used with --validation-known-pairs (default: validation_data)",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.validation_known_pairs and args.fasta_files:
        parser.error("FASTA files cannot be combined with --validation-known-pairs")
    if not args.validation_known_pairs and not args.fasta_files:
        parser.error("provide aligned FASTA file(s) or --validation-known-pairs")

    try:
        if args.validation_known_pairs:
            print(
                "Validation preview: v2.1 pair candidates are terminal-gap-padded "
                "for display only; this is not a biological multiple alignment.",
                file=sys.stderr,
            )
            records = build_validation_preview_sequences(args.validation_directory)
            view_model = build_multiple_alignment_view_model(records)
        else:
            view_model = build_view_model_from_fasta(args.fasta_files)
        show_multiple_consensus_viewer(view_model)
    except (ValueError, OSError, tk.TclError) as error:
        print(f"Multiple Consensus Viewer launch failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
