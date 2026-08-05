#!/usr/bin/env python3
"""Launch the standalone Single Consensus Review prototype for one AB1 pair.

This is a prototype-evaluation entry point. It does not integrate with the
existing Main Window or alter consensus, alignment, or review results.

Usage:
    python -m tools.launch_consensus_viewer forward.ab1 reverse.ab1
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
from core.consensus_v2_1 import build_pair_consensus_v2_1
from core.pair_alignment import AmbiguousAlignmentWarning, NoCredibleOverlapError, align_pair
from core.trimming import trim_sequence
from gui.consensus_viewer import (
    SingleConsensusReviewWindow,
    SingleConsensusViewModel,
    build_single_consensus_view_model,
)


def build_view_model_from_ab1_pair(
    forward_path: str,
    reverse_path: str,
    *,
    sample_identifier: str | None = None,
) -> SingleConsensusViewModel:
    """Read, trim, align, and adapt one AB1 pair for the standalone viewer.

    The returned model contains bridge-derived ReviewEvidence. The GUI receives
    no raw AB1 data and does not calculate coordinates itself.
    """

    view_model, _forward_read, _reverse_read = _build_viewer_input_from_ab1_pair(
        forward_path,
        reverse_path,
        sample_identifier=sample_identifier,
    )
    return view_model


def _build_viewer_input_from_ab1_pair(
    forward_path: str,
    reverse_path: str,
    *,
    sample_identifier: str | None = None,
):
    """Return one GUI model and the exact reads needed for Main Viewer jumps."""

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
    view_model = build_single_consensus_view_model(
        sample_identifier or Path(forward_path).stem,
        pair_alignment,
        consensus_result,
    )
    return view_model, forward_read, reverse_read


def show_single_consensus_viewer(
    view_model: SingleConsensusViewModel,
    *,
    root_factory=tk.Tk,
    window_factory=SingleConsensusReviewWindow,
) -> None:
    """Show one prototype window without importing or changing MainWindow."""

    root = root_factory()
    root.withdraw()
    window = window_factory(root, view_model)
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def show_consensus_viewer_with_main_viewer(
    view_model: SingleConsensusViewModel,
    forward_read,
    reverse_read,
) -> None:
    """Open the prototype with a MainWindow callback for trace navigation."""

    from gui.main_window import MainWindow

    root = tk.Tk()
    main_window = MainWindow(root)
    main_window.reads = [forward_read, reverse_read]
    main_window.chrom_viewer.load_reads(main_window.reads)
    main_window.open_single_consensus_review(view_model)
    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Launch the standalone Single Consensus Review prototype for an AB1 pair."
    )
    parser.add_argument("forward_ab1", help="Forward AB1 file path")
    parser.add_argument("reverse_ab1", help="Reverse AB1 file path")
    parser.add_argument(
        "--sample-id",
        help="Optional display-only sample identifier (default: Forward filename stem)",
    )
    parser.add_argument(
        "--with-main-viewer",
        action="store_true",
        help="Open the prototype with Main Viewer trace-jump callbacks enabled",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        view_model, forward_read, reverse_read = _build_viewer_input_from_ab1_pair(
            args.forward_ab1,
            args.reverse_ab1,
            sample_identifier=args.sample_id,
        )
        if args.with_main_viewer:
            show_consensus_viewer_with_main_viewer(
                view_model,
                forward_read,
                reverse_read,
            )
        else:
            show_single_consensus_viewer(view_model)
    except (NoCredibleOverlapError, ValueError, IndexError, OSError, tk.TclError) as error:
        print(f"Consensus Viewer launch failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
