#!/usr/bin/env python3
"""Launch a demonstration Project Dataset Manager with in-memory datasets.

Usage:
    python -m tools.launch_project_dataset_manager
"""

from __future__ import annotations

from pathlib import Path
import sys
import tkinter as tk
from typing import TextIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from gui.project_dataset_manager import ProjectDatasetManagerWindow


def build_demo_project() -> Project:
    """Build an in-memory project that exercises manager table fields."""

    imported_fasta = SequenceDataset.from_sequence_pairs(
        "imported_fasta_demo",
        "Imported Wedgefish FASTA",
        SourceType.IMPORTED_FASTA,
        (
            ("WEDGE_001", "ATGCA"),
            ("WEDGE_002", "ATGCAT"),
            ("WEDGE_003", "ATG"),
        ),
    )
    alignment = SequenceDataset.from_sequence_pairs(
        "alignment_demo",
        "Wedgefish Alignment",
        SourceType.IMPORTED_ALIGNMENT,
        (
            ("WEDGE_001", "ATGC-TA"),
            ("WEDGE_002", "ATGCGTA"),
            ("WEDGE_003", "ATG--TA"),
        ),
    )
    reviewed_consensus = SequenceDataset.from_sequence_pairs(
        "reviewed_consensus_demo",
        "Reviewed Consensus Candidates",
        SourceType.REVIEWED_CONSENSUS,
        (
            ("WEDGE_004", "ATGCTAA"),
            ("WEDGE_005", "ATGTTAA"),
        ),
    )

    return (
        Project.create("sangerflow_demo", "SangerFlow Demo Project")
        .add_dataset(imported_fasta, derivation_type=DerivationType.IMPORTED)
        .add_dataset(
            alignment,
            parent_dataset_id=imported_fasta.dataset_id,
            derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
        )
        .add_dataset(reviewed_consensus)
    )


def report_open_dataset(dataset: SequenceDataset, *, stream: TextIO = sys.stdout) -> None:
    """Print one selected dataset; this launcher deliberately opens no viewer."""

    print("Opened dataset:", file=stream)
    print(f"  {dataset.dataset_id}", file=stream)
    print(f"  sequences: {dataset.sequence_count}", file=stream)


def report_open_datasets(
    datasets: tuple[SequenceDataset, ...],
    *,
    stream: TextIO = sys.stdout,
) -> None:
    """Print selected datasets in manager/project order."""

    print("Opened datasets:", file=stream)
    for dataset in datasets:
        print(f"  {dataset.dataset_id} (sequences: {dataset.sequence_count})", file=stream)


def report_project_changed(project: Project, *, stream: TextIO = sys.stdout) -> None:
    """Print the new immutable Project returned after manager removal."""

    print("Project changed:", file=stream)
    print(f"  datasets: {project.dataset_count}", file=stream)


def show_project_dataset_manager(
    project: Project,
    *,
    root_factory=tk.Tk,
    window_factory=ProjectDatasetManagerWindow,
) -> None:
    """Create a standalone Tk root and route callbacks to terminal diagnostics."""

    root = root_factory()
    root.withdraw()
    window = window_factory(
        root,
        project,
        on_open_dataset=report_open_dataset,
        on_open_datasets=report_open_datasets,
        on_project_changed=report_project_changed,
    )
    window.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("This launcher accepts no command-line arguments.", file=sys.stderr)
        return 2
    try:
        show_project_dataset_manager(build_demo_project())
    except tk.TclError as error:
        print(f"Project Dataset Manager launch failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
