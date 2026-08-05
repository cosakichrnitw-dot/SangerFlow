#!/usr/bin/env python3
"""Launch the Consensus Review Manager from explicit AB1 Forward/Reverse pairs.

This is a prototype-evaluation launcher. It uses the existing AB1 -> trim ->
AssemblyReadView -> PairAlignment -> v2.1 candidate workflow, then presents
the resulting candidates to the GUI manager. It does not integrate this route
into Main Window or persist any review state.

Usage:
    python -m tools.launch_consensus_review_manager --validation-known-pairs
    python -m tools.launch_consensus_review_manager F1.ab1 R1.ab1 F2.ab1 R2.ab1
"""

import argparse
from pathlib import Path
import sys
import tkinter as tk


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from gui.consensus_review_manager import (
    ConsensusReviewCandidate,
    ConsensusReviewManagerWindow,
)
from gui.consensus_viewer import SingleConsensusReviewWindow
from gui.multiple_consensus_viewer import MultipleConsensusAlignmentWindow
from core.consensus_evidence_map import ConsensusEvidenceEntry, ConsensusEvidenceMap
from tools.launch_consensus_alignment_viewer import _group_explicit_pairs
from tools.launch_consensus_viewer import build_view_model_from_ab1_pair


_KNOWN_VALIDATION_SAMPLE_IDS = (
    "IK345_COl-1",
    "IK346_COl-1",
    "IK347_COl-1",
    "IK348_COl-1",
    "IK349_COl-1",
    "IK350_COl-1",
)


def build_review_candidates_from_ab1_pairs(
    ab1_paths: list[str],
    *,
    sample_ids: list[str] | None = None,
) -> tuple[ConsensusReviewCandidate, ...]:
    """Build GUI manager candidates via the existing standalone pair workflow."""

    candidates = []
    for sample_id, forward_path, reverse_path in _group_explicit_pairs(
        ab1_paths,
        sample_ids=sample_ids,
    ):
        view_model = build_view_model_from_ab1_pair(
            forward_path,
            reverse_path,
            sample_identifier=sample_id,
        )
        candidates.append(
            ConsensusReviewCandidate(
                sample_id=sample_id,
                sequence=view_model.consensus_sequence,
                single_review_input=view_model,
                metadata={
                    "forward_filename": Path(forward_path).name,
                    "reverse_filename": Path(reverse_path).name,
                    "algorithm_version": "consensus-v2.1-shadow",
                },
            )
        )
    return tuple(candidates)


def known_validation_ab1_paths(
    validation_directory: str | Path = "validation_data",
) -> tuple[list[str], list[str]]:
    """Return only the fixed, known validation pairs; never infer filenames."""

    directory = Path(validation_directory)
    paths = []
    for sample_id in _KNOWN_VALIDATION_SAMPLE_IDS:
        forward_path = directory / f"{sample_id}_F.ab1"
        reverse_path = directory / f"{sample_id}_R.ab1"
        if not forward_path.is_file() or not reverse_path.is_file():
            raise OSError(
                f"validation pair is missing for {sample_id}: "
                f"{forward_path.name}, {reverse_path.name}"
            )
        paths.extend((str(forward_path), str(reverse_path)))
    return paths, list(_KNOWN_VALIDATION_SAMPLE_IDS)


def build_evidence_map_from_review_candidates(
    candidates: tuple[ConsensusReviewCandidate, ...],
) -> ConsensusEvidenceMap:
    """Index existing Single Review evidence without recalculating coordinates."""

    entries = []
    for candidate in candidates:
        view_model = candidate.single_review_input
        columns = getattr(view_model, "columns", None)
        if columns is None:
            raise ValueError("candidate has no Single Consensus Review evidence input")
        for column in columns:
            entries.append(
                ConsensusEvidenceEntry(
                    sample_id=candidate.sample_id,
                    consensus_position=column.consensus_position,
                    review_evidence=column.review_evidence,
                )
            )
    return ConsensusEvidenceMap(entries)


def show_consensus_review_manager(
    candidates: tuple[ConsensusReviewCandidate, ...],
    *,
    root_factory=tk.Tk,
    manager_factory=ConsensusReviewManagerWindow,
    single_window_factory=SingleConsensusReviewWindow,
    multiple_window_factory=MultipleConsensusAlignmentWindow,
    on_trace_jump=None,
) -> None:
    """Open the manager and route callbacks to standalone viewer prototypes."""

    root = root_factory()
    root.withdraw()
    evidence_map = build_evidence_map_from_review_candidates(candidates)

    def open_single(candidate: ConsensusReviewCandidate) -> None:
        view_model = candidate.single_review_input
        if view_model is None:
            raise ValueError("selected candidate has no Single Consensus Review input")
        single_window_factory(root, view_model)

    def open_multiple(aligned_consensus_set) -> None:
        multiple_window_factory(
            root,
            aligned_consensus_set,
            evidence_map=evidence_map,
            on_trace_jump=on_trace_jump,
        )

    manager = manager_factory(
        root,
        candidates,
        on_open_single=open_single,
        on_open_multiple=open_multiple,
    )
    manager.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prototype only: create v2.1 candidates from explicit AB1 pairs "
            "and open Consensus Review Manager."
        )
    )
    parser.add_argument(
        "ab1_files",
        nargs="*",
        help="Explicit Forward/Reverse pairs: F1 R1 F2 R2 [...].",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        help="Optional sample identifier; provide once per explicit pair.",
    )
    parser.add_argument(
        "--validation-known-pairs",
        action="store_true",
        help="Use only the six fixed validation_data pairs IK345 through IK350.",
    )
    parser.add_argument(
        "--validation-directory",
        default="validation_data",
        help="Directory used with --validation-known-pairs (default: validation_data).",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.validation_known_pairs and args.ab1_files:
        parser.error("AB1 paths cannot be combined with --validation-known-pairs")
    if args.validation_known_pairs and args.sample_ids:
        parser.error("--sample-id cannot be combined with --validation-known-pairs")
    if not args.validation_known_pairs and not args.ab1_files:
        parser.error("provide explicit AB1 pairs or --validation-known-pairs")
    try:
        if args.validation_known_pairs:
            ab1_paths, sample_ids = known_validation_ab1_paths(args.validation_directory)
        else:
            ab1_paths, sample_ids = args.ab1_files, args.sample_ids
        candidates = build_review_candidates_from_ab1_pairs(
            ab1_paths,
            sample_ids=sample_ids,
        )
        print("Consensus candidates:")
        for candidate in candidates:
            print(f"  {candidate.sample_id}: {len(candidate.sequence)} bp")
        show_consensus_review_manager(candidates)
    except (ValueError, IndexError, OSError, tk.TclError) as error:
        print(f"Consensus Review Manager launch failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
