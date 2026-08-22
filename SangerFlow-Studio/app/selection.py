"""Typed selection values shared by Studio widgets and viewers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SelectionKind(Enum):
    """Kinds of selectable objects in the Studio shell."""

    PROJECT = "PROJECT"
    DATASET = "DATASET"
    ANALYSIS_RESULT = "ANALYSIS_RESULT"
    VIEWER = "VIEWER"
    SEQUENCE_RECORD = "SEQUENCE_RECORD"
    CHROMATOGRAM_POSITION = "CHROMATOGRAM_POSITION"
    ALIGNMENT_COLUMN = "ALIGNMENT_COLUMN"
    CONSENSUS_POSITION = "CONSENSUS_POSITION"
    BLAST_HIT = "BLAST_HIT"
    BOLD_HIT = "BOLD_HIT"


@dataclass(frozen=True)
class StudioSelection:
    """Immutable selection payload passed through AppState signals."""

    kind: SelectionKind
    object_id: str | None
    payload: object | None
    source_viewer_id: str | None = None

    @classmethod
    def project(cls, project: object) -> "StudioSelection":
        return cls(
            kind=SelectionKind.PROJECT,
            object_id=getattr(project, "project_id", None),
            payload=project,
        )

    @classmethod
    def dataset(cls, entry: object) -> "StudioSelection":
        dataset = getattr(entry, "dataset", None)
        return cls(
            kind=SelectionKind.DATASET,
            object_id=getattr(dataset, "dataset_id", None)
            or getattr(dataset, "alignment_id", None),
            payload=entry,
        )

    @classmethod
    def analysis_result(cls, entry: object) -> "StudioSelection":
        return cls(
            kind=SelectionKind.ANALYSIS_RESULT,
            object_id=getattr(entry, "result_id", None),
            payload=entry,
        )

    @classmethod
    def viewer(cls, viewer: object) -> "StudioSelection":
        return cls(
            kind=SelectionKind.VIEWER,
            object_id=getattr(viewer, "viewer_id", None),
            payload=viewer,
        )
