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
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.quality_report_viewer import QualityReportViewer
from widgets.viewers.viewer_actions import ViewerAction, ViewerActionProvider
from widgets.viewers.viewer_context import ViewerContext
from widgets.viewers.viewer_registry import ViewerDescriptor, ViewerRegistry

__all__ = [
    "BaseViewer",
    "ChromatogramViewer",
    "ChromatogramViewerActionProvider",
    "AlignmentChromatogramViewer",
    "AlignmentViewer",
    "DatasetViewer",
    "PlaceholderViewer",
    "QualityReportViewer",
    "ViewerAction",
    "ViewerActionProvider",
    "ViewerContext",
    "ViewerDescriptor",
    "ViewerRegistry",
    "create_chromatogram_viewer_from_dataset",
    "create_dataset_viewer",
    "create_alignment_viewer",
    "has_chromatogram_sources",
    "reads_from_dataset",
]
