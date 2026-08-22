"""Viewer framework primitives for SangerFlow-Studio."""

from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.chromatogram_viewer import (
    ChromatogramViewer,
    ChromatogramViewerActionProvider,
    create_chromatogram_viewer_from_dataset,
    has_chromatogram_sources,
    reads_from_dataset,
)
from widgets.viewers.dataset_viewer import DatasetViewer, create_dataset_viewer
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers.alignment_viewer import AlignmentViewer, create_alignment_viewer
from widgets.viewers.sequence_editor import SequenceEditor, create_sequence_editor
from widgets.viewers.consensus_review_viewer import (
    ConsensusReviewViewer,
    create_consensus_review_viewer,
)
from widgets.viewers.fr_consensus_review import (
    ConsensusReviewManagerViewer,
    MultipleConsensusReviewViewer,
    SingleConsensusReviewViewer,
    build_consensus_sample_rows,
)
from widgets.viewers.identification_result_viewers import (
    BlastResultStudioViewer,
    BoldResultStudioViewer,
    create_blast_result_viewer,
    create_bold_result_viewer,
)
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.quality_report_viewer import QualityReportViewer
from widgets.viewers.project_records_viewer import ProjectRecordsViewer, create_project_records_viewer
from widgets.viewers.viewer_actions import ViewerAction, ViewerActionProvider
from widgets.viewers.viewer_context import ViewerContext
from widgets.viewers.viewer_registry import ViewerDescriptor, ViewerRegistry

__all__ = [
    "BaseViewer",
    "ChromatogramViewer",
    "ChromatogramViewerActionProvider",
    "AlignmentChromatogramViewer",
    "AlignmentViewer",
    "SequenceEditor",
    "ConsensusReviewViewer",
    "ConsensusReviewManagerViewer",
    "MultipleConsensusReviewViewer",
    "DatasetViewer",
    "PlaceholderViewer",
    "QualityReportViewer",
    "ProjectRecordsViewer",
    "SingleConsensusReviewViewer",
    "BlastResultStudioViewer",
    "BoldResultStudioViewer",
    "ViewerAction",
    "ViewerActionProvider",
    "ViewerContext",
    "ViewerDescriptor",
    "ViewerRegistry",
    "create_chromatogram_viewer_from_dataset",
    "create_dataset_viewer",
    "create_alignment_viewer",
    "create_sequence_editor",
    "create_consensus_review_viewer",
    "create_blast_result_viewer",
    "create_bold_result_viewer",
    "create_project_records_viewer",
    "build_consensus_sample_rows",
    "has_chromatogram_sources",
    "reads_from_dataset",
]
