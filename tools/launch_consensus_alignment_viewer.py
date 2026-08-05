#!/usr/bin/env python3
"""Launch the prototype multiple-consensus viewer from explicit AB1 pairs.

This diagnostic entry point builds independent v2.1 shadow candidates, aligns
them through the existing MAFFT-backed consensus-alignment core, then opens
the read-only Multiple Consensus Alignment Viewer.  It is not part of the
main workflow and does not persist or promote any candidate sequence.

Usage:
    python -m tools.launch_consensus_alignment_viewer \\
        forward_1.ab1 reverse_1.ab1 forward_2.ab1 reverse_2.ab1
"""

import argparse
from pathlib import Path
import sys
import tkinter as tk
import warnings


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.ab1_reader import read_ab1
from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from core.consensus_alignment import (
    AlignedConsensusSet,
    ConsensusAlignmentExecutionError,
    MafftExecutableNotFoundError,
    run_consensus_alignment,
)
from core.consensus_v2_1 import build_pair_consensus_v2_1
from core.pair_alignment import AmbiguousAlignmentWarning, NoCredibleOverlapError, align_pair
from core.trimming import trim_sequence
from gui.multiple_consensus_viewer import (
    MultipleConsensusAlignmentWindow,
    build_multiple_alignment_view_model,
)


def build_consensus_candidates_from_ab1_pairs(
    ab1_paths: list[str],
    *,
    sample_ids: list[str] | None = None,
) -> list[dict[str, object]]:
    """Build independent v2.1 candidates from explicitly ordered AB1 pairs.

    ``ab1_paths`` is interpreted only as ``Forward, Reverse`` pairs in the
    supplied order.  No filename-based pairing or classification is performed.
    """

    pairs = _group_explicit_pairs(ab1_paths, sample_ids=sample_ids)
    candidates = []
    for sample_id, forward_path, reverse_path in pairs:
        forward_read = read_ab1(forward_path)
        reverse_read = read_ab1(reverse_path)
        trim_sequence(forward_read)
        trim_sequence(reverse_read)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", AmbiguousAlignmentWarning)
            pair_alignment = align_pair(
                build_forward_assembly_view(forward_read),
                build_reverse_assembly_view(reverse_read),
            )
        consensus_result = build_pair_consensus_v2_1(pair_alignment)
        candidates.append(
            {
                "sample_id": sample_id,
                "sequence": consensus_result.consensus_sequence,
                "metadata": {
                    "forward_filename": Path(forward_path).name,
                    "reverse_filename": Path(reverse_path).name,
                    "algorithm_version": consensus_result.algorithm_version,
                },
            }
        )
    return candidates


def align_candidates_for_viewer(
    candidates: list[dict[str, object]],
) -> AlignedConsensusSet:
    """Use the MAFFT-backed core workflow; this module does not align itself."""

    return run_consensus_alignment(candidates, alignment_id="v2.1-prototype")


def show_consensus_alignment_viewer(
    aligned_consensus_set: AlignedConsensusSet,
    *,
    root_factory=tk.Tk,
    window_factory=MultipleConsensusAlignmentWindow,
) -> None:
    """Display the read-only matrix prototype from an existing core result."""

    root = root_factory()
    root.withdraw()
    view_model = build_multiple_alignment_view_model(aligned_consensus_set)
    window = window_factory(root, view_model)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def _group_explicit_pairs(
    ab1_paths: list[str],
    *,
    sample_ids: list[str] | None,
) -> list[tuple[str, str, str]]:
    if len(ab1_paths) < 4 or len(ab1_paths) % 2:
        raise ValueError("provide at least two explicit Forward/Reverse AB1 pairs")
    pair_count = len(ab1_paths) // 2
    if sample_ids is not None and len(sample_ids) != pair_count:
        raise ValueError("--sample-id must be provided once for each AB1 pair")

    pairs = []
    used_sample_ids = set()
    for pair_index in range(pair_count):
        forward_path = ab1_paths[pair_index * 2]
        reverse_path = ab1_paths[(pair_index * 2) + 1]
        sample_id = (
            sample_ids[pair_index]
            if sample_ids is not None
            else _default_sample_id(forward_path)
        )
        if not sample_id or any(character.isspace() for character in sample_id):
            raise ValueError("sample IDs must be non-empty and contain no whitespace")
        if sample_id in used_sample_ids:
            raise ValueError(f"sample IDs must be unique: {sample_id}")
        pairs.append((sample_id, forward_path, reverse_path))
        used_sample_ids.add(sample_id)
    return pairs


def _default_sample_id(forward_path: str) -> str:
    """Use the Forward filename stem only as a display identifier."""

    stem = Path(forward_path).stem
    return stem[:-2] if stem.endswith("_F") else stem


def _print_run_summary(
    candidates: list[dict[str, object]],
    aligned_consensus_set: AlignedConsensusSet,
) -> None:
    print("Consensus v2.1 candidates:")
    for candidate in candidates:
        print(f"  {candidate['sample_id']}: {len(candidate['sequence'])} bp")
    print("MAFFT alignment:")
    print(f"  alignment length: {aligned_consensus_set.alignment_length} bp")
    print(f"  gap percentage: {aligned_consensus_set.gap_percentage:.2f}%")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prototype only: build v2.1 candidates from explicit AB1 pairs, "
            "align them through MAFFT, and open the Multiple Consensus Viewer."
        )
    )
    parser.add_argument(
        "ab1_files",
        nargs="+",
        help="Explicit Forward/Reverse pairs: F1 R1 F2 R2 [...]; at least two pairs",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="Optional sample identifier; provide once per explicit pair",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        candidates = build_consensus_candidates_from_ab1_pairs(
            args.ab1_files,
            sample_ids=args.sample_ids,
        )
        aligned_consensus_set = align_candidates_for_viewer(candidates)
        _print_run_summary(candidates, aligned_consensus_set)
        show_consensus_alignment_viewer(aligned_consensus_set)
    except (
        ConsensusAlignmentExecutionError,
        MafftExecutableNotFoundError,
        NoCredibleOverlapError,
        ValueError,
        IndexError,
        OSError,
        tk.TclError,
    ) as error:
        print(f"Consensus Alignment Viewer launch failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
