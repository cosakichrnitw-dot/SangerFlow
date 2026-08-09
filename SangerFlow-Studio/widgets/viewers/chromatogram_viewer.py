"""PySide6 chromatogram viewer for SangerRead collections.

This viewer intentionally mirrors the older Tkinter Main Viewer interaction
model: raw chromatogram coordinates are drawn in one horizontally scrollable
waveform surface, while sample labels stay in a fixed left column and follow
vertical scrolling only.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from time import perf_counter_ns
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QStaticText
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.selection import SelectionKind, StudioSelection
from core.models import SangerRead
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


ROW_HEIGHT = 100
TRACE_TOP = 55
TRACE_HEIGHT = 70
SEQUENCE_Y = 20
RULER_Y = 5
LABEL_WIDTH = 110
SCALE_PANEL_WIDTH = 38
SAMPLE_PANEL_TITLE_HEIGHT = 30
SAMPLE_CHECKBOX_HEIGHT = 24
SAMPLE_CHECKBOX_SPACING = 2
BASE_HIT_TOLERANCE = 18
TRACE_TILE_WIDTH = 1024
TRACE_TILE_PREFETCH = 1
TRACE_TILE_BUILD_BUDGET_MS = 10.0
X_SCALE_MIN = 30
X_SCALE_MAX = 2000
Y_SCALE_MIN = 50
Y_SCALE_MAX = 300

_TRACE_COLORS = {
    "A": QColor("#2CA02C"),
    "C": QColor("#1F77B4"),
    "G": QColor("#222222"),
    "T": QColor("#D62728"),
}
_BASE_COLORS = {
    "A": QColor("green"),
    "C": QColor("blue"),
    "G": QColor("black"),
    "T": QColor("red"),
}


@dataclass(frozen=True)
class ChromatogramRenderCache:
    """Precomputed raw-coordinate drawing geometry for one read row."""

    trace_paths: dict[str, QPainterPath]
    quality_path: QPainterPath | None
    base_items: tuple[tuple[int, str, int, QStaticText], ...]
    tick_items: tuple[tuple[int, str, QStaticText], ...]


@dataclass(frozen=True)
class ChromatogramReadView:
    """Raw-coordinate display adapter for one Sanger chromatogram read."""

    read_id: str
    read: SangerRead
    sequence: str
    quality: tuple[int, ...]
    traces: dict[str, tuple[int, ...]]
    base_positions: tuple[int, ...]
    trim_start: int
    trim_end: int
    trimmed_base_positions: tuple[int, ...]
    render_cache: ChromatogramRenderCache

    @property
    def sequence_length(self) -> int:
        return len(self.sequence)

    @property
    def trace_length(self) -> int:
        if not self.traces:
            return 0
        return max((len(trace) for trace in self.traces.values()), default=0)

    @property
    def average_quality(self) -> float:
        if not self.quality:
            return 0.0
        return float(mean(self.quality))

    @property
    def q20_rate(self) -> float:
        if not self.quality:
            return 0.0
        return 100.0 * sum(quality >= 20 for quality in self.quality) / len(self.quality)

    @property
    def q30_rate(self) -> float:
        if not self.quality:
            return 0.0
        return 100.0 * sum(quality >= 30 for quality in self.quality) / len(self.quality)

    @property
    def trim_length(self) -> int:
        return max(0, min(self.trim_end, self.sequence_length) - max(0, self.trim_start))


@dataclass(frozen=True)
class SelectedBaseInfo:
    """Selected raw-base coordinate information shown in the base inspector."""

    read_id: str
    base: str
    quality: int | str
    region: str
    raw_index: int
    trim_index: int | None
    raw_trace_position: int
    trim_trace_position: int | None


class ChromatogramPaintProfiler:
    """Collect paint timing for read-level chromatogram graphics items."""

    _SECTIONS = (
        "background",
        "quality",
        "trim",
        "trace",
        "read_name",
        "base",
        "tick",
    )

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.paint_calls = 0
        self.total_ns = 0
        self.section_ns = {section: 0 for section in self._SECTIONS}
        self.section_calls = {section: 0 for section in self._SECTIONS}

    def record_paint(self, total_ns: int, section_ns: dict[str, int]) -> None:
        self.paint_calls += 1
        self.total_ns += total_ns
        for section, elapsed_ns in section_ns.items():
            if section not in self.section_ns:
                continue
            self.section_ns[section] += elapsed_ns
            self.section_calls[section] += 1

    def snapshot(self) -> dict[str, object]:
        sections = {
            section: {
                "calls": self.section_calls[section],
                "total_ms": self.section_ns[section] / 1_000_000,
                "avg_ms": (
                    self.section_ns[section] / self.section_calls[section] / 1_000_000
                    if self.section_calls[section]
                    else 0.0
                ),
            }
            for section in self._SECTIONS
        }
        dominant = max(
            self._SECTIONS,
            key=lambda section: self.section_ns[section],
        )
        return {
            "paint_calls": self.paint_calls,
            "total_ms": self.total_ns / 1_000_000,
            "avg_paint_ms": (
                self.total_ns / self.paint_calls / 1_000_000
                if self.paint_calls
                else 0.0
            ),
            "sections": sections,
            "dominant_section": dominant if self.section_ns[dominant] else None,
        }


class ChromatogramCacheProfiler:
    """Collect trace tile cache build timings and memory estimates."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.tile_builds = 0
        self.total_build_ns = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.tiles_in_memory = 0
        self.estimated_cache_bytes = 0
        self.device_pixel_ratio = 1.0
        self.last_logical_width = 0
        self.last_logical_height = 0
        self.last_physical_width = 0
        self.last_physical_height = 0

    def record_hit(self) -> None:
        self.cache_hits += 1

    def record_miss(self) -> None:
        self.cache_misses += 1

    def record_build(
        self,
        *,
        elapsed_ns: int,
        logical_width: int,
        logical_height: int,
        physical_width: int,
        physical_height: int,
        device_pixel_ratio: float,
        tiles_in_memory: int,
        estimated_cache_bytes: int,
    ) -> None:
        self.tile_builds += 1
        self.total_build_ns += elapsed_ns
        self.last_logical_width = logical_width
        self.last_logical_height = logical_height
        self.last_physical_width = physical_width
        self.last_physical_height = physical_height
        self.device_pixel_ratio = device_pixel_ratio
        self.tiles_in_memory = tiles_in_memory
        self.estimated_cache_bytes = estimated_cache_bytes

    def snapshot(self) -> dict[str, object]:
        return {
            "tile_builds": self.tile_builds,
            "total_build_ms": self.total_build_ns / 1_000_000,
            "avg_tile_build_ms": (
                self.total_build_ns / self.tile_builds / 1_000_000
                if self.tile_builds
                else 0.0
            ),
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "tiles_in_memory": self.tiles_in_memory,
            "estimated_cache_memory_mb": self.estimated_cache_bytes / (1024 * 1024),
            "device_pixel_ratio": self.device_pixel_ratio,
            "last_logical_width": self.last_logical_width,
            "last_logical_height": self.last_logical_height,
            "last_physical_width": self.last_physical_width,
            "last_physical_height": self.last_physical_height,
        }


class ChromatogramViewer(BaseViewer):
    """Display multiple raw SangerRead chromatograms in a vertical row matrix."""

    def __init__(
        self,
        reads: Iterable[SangerRead],
        *,
        title: str = "Chromatogram Viewer",
        source_object_id: str | None = None,
        context: object | None = None,
        source_dataset: object | None = None,
    ) -> None:
        self._context = context
        self._source_dataset = source_dataset
        self._reads = tuple(_read_view(read) for read in reads)
        self._visibility_source_key = source_object_id or f"chromatogram:{id(self)}"
        self._visibility_manager = getattr(context, "read_visibility_manager", None)
        self._selected_read_id: str | None = None
        self._selected_base: SelectedBaseInfo | None = None
        self._show_trim_region = False
        self._x_offset = 0
        self._y_offset = 0
        self._scale_x = 1.0
        self._scale_y = 1.0
        self._pending_scale_x = self._scale_x
        self._pending_scale_y = self._scale_y
        self._visible_read_ids = {read.read_id for read in self._reads}
        if self._visibility_manager is not None:
            read_ids = tuple(read.read_id for read in self._reads)
            self._visibility_manager.initialize_source(self._visibility_source_key, read_ids)
            self._visible_read_ids = set(
                self._visibility_manager.visible_ids(self._visibility_source_key, read_ids)
            )
            self._visibility_manager.visibility_changed.connect(self._visibility_changed)
        self._action_provider = ChromatogramViewerActionProvider()
        super().__init__(
            viewer_id=f"chromatogram-viewer-{_safe_identifier(source_object_id) if source_object_id else id(self)}",
            viewer_title=title,
            viewer_kind="chromatogram",
            source_object_id=source_object_id,
        )
        self._build_ui()

    @property
    def read_views(self) -> tuple[ChromatogramReadView, ...]:
        return self._reads

    @property
    def selected_read_id(self) -> str | None:
        return self._selected_read_id

    @property
    def selected_base(self) -> SelectedBaseInfo | None:
        return self._selected_base

    @property
    def show_trim_region(self) -> bool:
        return self._show_trim_region

    @property
    def scale_x(self) -> float:
        return self._scale_x

    @property
    def scale_y(self) -> float:
        return self._scale_y

    @property
    def visible_read_ids(self) -> frozenset[str]:
        return frozenset(self._visible_read_ids)

    @property
    def visible_read_views(self) -> tuple[ChromatogramReadView, ...]:
        return tuple(
            read_view
            for read_view in self._reads
            if read_view.read_id in self._visible_read_ids
        )

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "chromatogram.toggle_trim_region",
            "chromatogram.export",
            "chromatogram.run_blast",
            "chromatogram.build_consensus",
            "chromatogram.open_quality_report",
            "chromatogram.align",
            "chromatogram.dev_start_paint_profile",
            "chromatogram.dev_stop_paint_profile",
        )

    def open_dataset(self, dataset: object) -> None:
        self._source_dataset = dataset
        self._reads = tuple(_read_view(read) for read in reads_from_dataset(dataset))
        read_ids = tuple(read.read_id for read in self._reads)
        if self._visibility_manager is not None:
            self._visibility_manager.initialize_source(self._visibility_source_key, read_ids)
            self._visible_read_ids = set(
                self._visibility_manager.visible_ids(self._visibility_source_key, read_ids)
            )
        else:
            self._visible_read_ids = set(read_ids)
        self._selected_read_id = None
        self._selected_base = None
        self.refresh()

    def refresh(self) -> None:
        visible_count = len(self._visible_read_ids)
        self._summary_label.setText(
            f"Reads: {visible_count}/{len(self._reads)}"
            + (
                f"    Selected: {self._selected_read_id}"
                if self._selected_read_id
                else ""
            )
        )
        self._update_scroll_ranges()
        self._update_base_inspector()
        self._canvas_widget.rebuild_scene()
        self._read_label_widget.update()

    def select_read(self, read_id: str) -> None:
        read_view = self._read_by_id(read_id)
        self._selected_read_id = read_view.read_id
        self._summary_label.setText(f"Reads: {len(self._visible_read_ids)}/{len(self._reads)}    Selected: {read_view.read_id}")
        self._update_base_inspector()
        self._canvas_widget.update_selection(self._selected_base)
        self.selection_changed.emit(
            StudioSelection(
                kind=SelectionKind.SEQUENCE_RECORD,
                object_id=read_view.read_id,
                payload=read_view,
                source_viewer_id=self.viewer_id,
            )
        )

    def select_base_at(self, content_x: float, content_y: float) -> SelectedBaseInfo | None:
        visible_reads = self.visible_read_views
        row_height = self._row_height()
        row_index = int(content_y // row_height)
        if row_index < 0 or row_index >= len(visible_reads):
            return None
        read_view = visible_reads[row_index]
        if not read_view.base_positions:
            return None
        raw_index = min(
            range(len(read_view.base_positions)),
            key=lambda index: abs(read_view.base_positions[index] - content_x),
        )
        if abs(read_view.base_positions[raw_index] - content_x) > BASE_HIT_TOLERANCE:
            return None
        self._selected_read_id = read_view.read_id
        self._selected_base = _selected_base_info(read_view, raw_index)
        self._summary_label.setText(f"Reads: {len(self._visible_read_ids)}/{len(self._reads)}    Selected: {read_view.read_id}")
        self._update_base_inspector()
        self._canvas_widget.update_selection(self._selected_base)
        self.selection_changed.emit(
            StudioSelection(
                kind=SelectionKind.SEQUENCE_RECORD,
                object_id=read_view.read_id,
                payload=read_view,
                source_viewer_id=self.viewer_id,
            )
        )
        return self._selected_base

    def set_read_visible(self, read_id: str, visible: bool) -> None:
        self._read_by_id(read_id)
        if self._visibility_manager is not None:
            self._visibility_manager.set_visible(self._visibility_source_key, read_id, visible)
            return
        if visible:
            self._visible_read_ids.add(read_id)
        else:
            self._visible_read_ids.discard(read_id)
            if self._selected_read_id == read_id:
                self._selected_read_id = None
                self._selected_base = None
        self.refresh()

    def _visibility_changed(self, source_key: str, visible_ids: object) -> None:
        if source_key != self._visibility_source_key:
            return
        self._visible_read_ids = set(tuple(visible_ids))
        if self._selected_read_id not in self._visible_read_ids:
            self._selected_read_id = None
            self._selected_base = None
        self.refresh()

    def set_x_scale(self, value: float) -> None:
        self._scale_x = self._clamp_x_scale(value)
        self._pending_scale_x = self._scale_x
        self._update_scroll_ranges()
        self._canvas_widget.rebuild_scene()

    def set_y_scale(self, value: float) -> None:
        self._scale_y = self._clamp_y_scale(value)
        self._pending_scale_y = self._scale_y
        self._update_scroll_ranges()
        self._canvas_widget.rebuild_scene()

    def preview_x_scale(self, value: float) -> None:
        self._pending_scale_x = self._clamp_x_scale(value)
        self.status_message_changed.emit(f"X scale preview: {self._pending_scale_x:.2f}x")

    def preview_y_scale(self, value: float) -> None:
        self._pending_scale_y = self._clamp_y_scale(value)
        self.status_message_changed.emit(f"Y scale preview: {self._pending_scale_y:.2f}x")

    def commit_pending_scale(self) -> None:
        changed = (
            self._pending_scale_x != self._scale_x
            or self._pending_scale_y != self._scale_y
        )
        self._scale_x = self._pending_scale_x
        self._scale_y = self._pending_scale_y
        if not changed:
            return
        self._update_scroll_ranges()
        self._canvas_widget.rebuild_scene()

    def rebuild_diagnostics(self) -> dict[str, int]:
        return self._canvas_widget.rebuild_diagnostics()

    def toggle_trim_region(self) -> None:
        self._show_trim_region = not self._show_trim_region
        self._canvas_widget.rebuild_scene()
        state = "shown" if self._show_trim_region else "hidden"
        self.status_message_changed.emit(f"Trim region overlay {state}.")

    def enable_paint_profiling(self, *, reset: bool = True) -> None:
        self._canvas_widget.enable_paint_profiling(reset=reset)

    def disable_paint_profiling(self) -> None:
        self._canvas_widget.disable_paint_profiling()

    def paint_profile_snapshot(self) -> dict[str, object]:
        snapshot = self._canvas_widget.paint_profile_snapshot()
        snapshot["rebuild_diagnostics"] = self.rebuild_diagnostics()
        snapshot["cache_profile"] = self._canvas_widget.cache_profile_snapshot()
        return snapshot

    def start_paint_profile(self) -> None:
        """Development-only action: start collecting paint timings."""

        self.enable_paint_profiling(reset=True)
        self.status_message_changed.emit("Development paint profiling started.")
        _emit_profile_output("[PROFILE] started")

    def stop_paint_profile(self) -> dict[str, object]:
        """Development-only action: stop paint profiling and print a summary."""

        snapshot = self.paint_profile_snapshot()
        _emit_profile_output(_format_paint_profile_snapshot(snapshot))
        self.disable_paint_profiling()
        _emit_profile_output("[PROFILE] stopped")
        self.status_message_changed.emit("Development paint profiling stopped. See terminal output.")
        return snapshot

    def request_export(self) -> None:
        self.status_message_changed.emit("Export action requested for Chromatogram Viewer.")
        self.export_requested.emit({"viewer": self, "read_id": self._selected_read_id})

    def request_blast(self) -> None:
        self.status_message_changed.emit("BLAST action requested for selected chromatogram read.")
        self.open_related_requested.emit(
            {"action": "BLAST", "viewer": self, "read_id": self._selected_read_id}
        )

    def request_consensus(self) -> None:
        self.status_message_changed.emit("Consensus action requested for chromatogram reads.")
        self.open_related_requested.emit(
            {"action": "CONSENSUS", "viewer": self, "read_id": self._selected_read_id}
        )

    def open_quality_report(self) -> object | None:
        context = self._context
        dock_manager = getattr(context, "dock_manager", None)
        if dock_manager is not None:
            dock = dock_manager.show_quality_report(
                self.read_views,
                source_key=self._visibility_source_key,
            )
            if dock is not None:
                return dock
        self.open_related_requested.emit({"action": "QUALITY_REPORT", "viewer": self})
        return None

    @property
    def source_dataset(self) -> object | None:
        return self._source_dataset

    def align(self) -> object | None:
        context = self._context
        controller = getattr(context, "project_controller", None)
        if controller is None:
            self.open_related_requested.emit({"action": "ALIGN", "viewer": self})
            return None
        align_method = getattr(controller, "align_chromatogram_viewer", None)
        if not callable(align_method):
            self.open_related_requested.emit({"action": "ALIGN", "viewer": self})
            return None
        return align_method(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary_label = QLabel()
        self._summary_label.setObjectName("chromatogramSummaryLabel")
        layout.addWidget(self._summary_label)

        self._dev_profile_panel = QWidget()
        self._dev_profile_panel.setObjectName("chromatogramDevPaintProfilePanel")
        dev_layout = QHBoxLayout(self._dev_profile_panel)
        dev_layout.setContentsMargins(0, 0, 0, 4)
        dev_layout.setSpacing(6)
        dev_label = QLabel("Development paint profiling:")
        dev_label.setStyleSheet("color: #777777;")
        self._dev_start_profile_button = QPushButton("Start Paint Profile")
        self._dev_start_profile_button.setObjectName("devStartPaintProfileButton")
        self._dev_stop_profile_button = QPushButton("Stop Paint Profile")
        self._dev_stop_profile_button.setObjectName("devStopPaintProfileButton")
        self._dev_start_profile_button.clicked.connect(
            lambda _checked=False: self.start_paint_profile()
        )
        self._dev_stop_profile_button.clicked.connect(
            lambda _checked=False: self.stop_paint_profile()
        )
        dev_layout.addWidget(dev_label)
        dev_layout.addWidget(self._dev_start_profile_button)
        dev_layout.addWidget(self._dev_stop_profile_button)
        dev_layout.addStretch(1)
        layout.addWidget(self._dev_profile_panel)

        viewer_area = QGridLayout()
        viewer_area.setContentsMargins(0, 0, 0, 0)
        viewer_area.setHorizontalSpacing(0)
        viewer_area.setVerticalSpacing(0)

        self._read_label_widget = ReadLabelColumnWidget(self)
        self._canvas_widget = ChromatogramCanvasWidget(self)
        self._vertical_scrollbar = QScrollBar(Qt.Orientation.Vertical, self)
        self._vertical_scrollbar.hide()
        self._horizontal_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._horizontal_scrollbar.setFixedHeight(12)
        self._horizontal_scrollbar.setStyleSheet(_thin_horizontal_scrollbar_stylesheet())
        self._scale_panel_widget = ScalePanelWidget(self)

        viewer_area.addWidget(self._read_label_widget, 0, 0)
        viewer_area.addWidget(self._canvas_widget, 0, 1)
        viewer_area.addWidget(self._scale_panel_widget, 0, 2)
        viewer_area.addWidget(self._horizontal_scrollbar, 1, 1)
        viewer_area.setColumnStretch(0, 0)
        viewer_area.setColumnStretch(1, 1)
        viewer_area.setColumnStretch(2, 0)
        viewer_area.setRowStretch(0, 1)

        layout.addLayout(viewer_area, 1)

        self._inspector_panel = SelectedBasePanel()
        layout.addWidget(self._inspector_panel)

        self._vertical_scrollbar.valueChanged.connect(self._set_y_offset)
        self._horizontal_scrollbar.valueChanged.connect(self._set_x_offset)
        self._canvas_widget.resized.connect(self._update_scroll_ranges)
        self.refresh()

    def _set_x_offset(self, value: int) -> None:
        self._x_offset = value
        self._canvas_widget.set_view_offset(self._x_offset, self._y_offset)

    def _set_y_offset(self, value: int) -> None:
        self._y_offset = value
        self._canvas_widget.set_view_offset(self._x_offset, self._y_offset)
        self._read_label_widget.update()

    def _update_scroll_ranges(self) -> None:
        content_width = self._content_width()
        content_height = self._content_height()
        viewport_width = max(1, self._canvas_widget.width())
        viewport_height = max(1, self._canvas_widget.height())
        max_x = max(0, content_width - viewport_width)
        max_y = max(0, content_height - viewport_height)
        self._horizontal_scrollbar.setRange(0, max_x)
        self._horizontal_scrollbar.setPageStep(viewport_width)
        self._horizontal_scrollbar.setSingleStep(40)
        self._vertical_scrollbar.setRange(0, max_y)
        self._vertical_scrollbar.setPageStep(viewport_height)
        self._vertical_scrollbar.setSingleStep(max(1, self._row_height() // 2))
        self._x_offset = min(self._x_offset, max_x)
        self._y_offset = min(self._y_offset, max_y)
        if self._horizontal_scrollbar.value() != self._x_offset:
            self._horizontal_scrollbar.setValue(self._x_offset)
        else:
            self._canvas_widget.set_view_offset(self._x_offset, self._y_offset)
        if self._vertical_scrollbar.value() != self._y_offset:
            self._vertical_scrollbar.setValue(self._y_offset)
        else:
            self._canvas_widget.set_view_offset(self._x_offset, self._y_offset)

    def _content_width(self) -> int:
        max_trace = max((read.trace_length for read in self._reads), default=0)
        max_position = max(
            (max(read.base_positions) for read in self._reads if read.base_positions),
            default=0,
        )
        return max(1, int(max(max_trace, max_position) * self._scale_x) + 80)

    def _content_height(self) -> int:
        return len(self.visible_read_views) * self._row_height()

    def _row_height(self) -> int:
        return max(40, int(ROW_HEIGHT * self._scale_y))

    def _clamp_x_scale(self, value: float) -> float:
        return min(X_SCALE_MAX / 100, max(X_SCALE_MIN / 100, float(value)))

    def _clamp_y_scale(self, value: float) -> float:
        return min(Y_SCALE_MAX / 100, max(Y_SCALE_MIN / 100, float(value)))

    def _update_base_inspector(self) -> None:
        selected_read = None
        if self._selected_read_id is not None:
            try:
                selected_read = self._read_by_id(self._selected_read_id)
            except KeyError:
                selected_read = None
        self._inspector_panel.set_selection(selected_read, self._selected_base)

    def _read_by_id(self, read_id: str) -> ChromatogramReadView:
        for read_view in self._reads:
            if read_view.read_id == read_id:
                return read_view
        raise KeyError(read_id)


class ChromatogramViewerActionProvider:
    """Action connection points for trim display, Export, BLAST, and Consensus."""

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="chromatogram.toggle_trim_region",
                label="Show Trim Region",
                tooltip="Toggle raw-coordinate trim outside-region overlay",
                callback=getattr(viewer, "toggle_trim_region"),
            ),
            ViewerAction(
                action_id="chromatogram.export",
                label="Export",
                tooltip="Export selected chromatogram data",
                callback=getattr(viewer, "request_export"),
            ),
            ViewerAction(
                action_id="chromatogram.run_blast",
                label="BLAST",
                tooltip="Run BLAST for the selected read in a future workflow",
                callback=getattr(viewer, "request_blast"),
            ),
            ViewerAction(
                action_id="chromatogram.build_consensus",
                label="Consensus",
                tooltip="Open the future consensus workflow for these reads",
                callback=getattr(viewer, "request_consensus"),
            ),
            ViewerAction(
                action_id="chromatogram.open_quality_report",
                label="Quality Report",
                tooltip="Open a Tkinter-style per-read quality report",
                callback=getattr(viewer, "open_quality_report"),
            ),
            ViewerAction(
                action_id="chromatogram.align",
                label="Align",
                tooltip="Create an AlignmentDataset, add it to the current Project, and open Alignment Viewer",
                callback=getattr(viewer, "align"),
            ),
            ViewerAction(
                action_id="chromatogram.dev_start_paint_profile",
                label="Dev: Start Paint Profile",
                tooltip="Development-only: start collecting chromatogram paint timings",
                callback=getattr(viewer, "start_paint_profile"),
            ),
            ViewerAction(
                action_id="chromatogram.dev_stop_paint_profile",
                label="Dev: Stop Paint Profile",
                tooltip="Development-only: stop paint profiling and print timing summary to terminal",
                callback=getattr(viewer, "stop_paint_profile"),
            ),
        )


class SamplePanelWidget(QWidget):
    """Compact sample visibility checklist for chromatogram read display."""

    resized = Signal()

    def __init__(self, viewer: ChromatogramViewer) -> None:
        super().__init__()
        self._viewer = viewer
        self.setFixedWidth(LABEL_WIDTH)
        self.setMinimumWidth(LABEL_WIDTH)
        self.setMaximumWidth(LABEL_WIDTH)
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)
        self.setObjectName("chromatogramSamplePanel")
        self._title_label = QLabel(self)
        self._title_label.setObjectName("chromatogramSamplePanelTitle")
        self._title_label.setStyleSheet("font-weight: 600; color: #333333;")
        self._all_button = QPushButton("All", self)
        self._none_button = QPushButton("None", self)
        self._invert_button = QPushButton("Invert", self)
        for button in (self._all_button, self._none_button, self._invert_button):
            button.setFixedHeight(22)
        self._all_button.clicked.connect(self.select_all)
        self._none_button.clicked.connect(self.clear_all)
        self._invert_button.clicked.connect(self.invert_selection)
        self._checkboxes: dict[str, QCheckBox] = {}
        self._build_checkboxes()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.resized.emit()
        self._layout_checkboxes()
        super().resizeEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        content_y = event.position().y() - self._checkbox_top()
        row_index = int(content_y // (SAMPLE_CHECKBOX_HEIGHT + SAMPLE_CHECKBOX_SPACING))
        if 0 <= row_index < len(self._viewer.read_views):
            self._viewer.select_read(self._viewer.read_views[row_index].read_id)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#F8F8F8"))
        painter.fillRect(0, 0, self.width(), SAMPLE_PANEL_TITLE_HEIGHT, QColor("#F0F0F0"))
        row_step = SAMPLE_CHECKBOX_HEIGHT + SAMPLE_CHECKBOX_SPACING
        for row_index, read_view in enumerate(self._viewer.read_views):
            y = self._checkbox_top() + row_index * row_step
            if y > event.rect().bottom():
                break
            if y + SAMPLE_CHECKBOX_HEIGHT < event.rect().top():
                continue
            if read_view.read_id == self._viewer.selected_read_id:
                painter.fillRect(0, y, self.width(), SAMPLE_CHECKBOX_HEIGHT, QColor("#F1EEFF"))
            painter.setPen(QPen(QColor("#D8D8D8")))
            painter.drawLine(0, y + SAMPLE_CHECKBOX_HEIGHT - 1, self.width(), y + SAMPLE_CHECKBOX_HEIGHT - 1)
        painter.setPen(QPen(QColor("#B8B8B8")))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()

    def refresh(self) -> None:
        self._title_label.setText(f"Reads ({len(self._viewer.read_views)})")
        self._build_checkboxes()
        self._layout_checkboxes()
        self.update()

    def _build_checkboxes(self) -> None:
        existing = set(self._checkboxes)
        wanted = {read.read_id for read in self._viewer.read_views}
        for read_id in existing - wanted:
            checkbox = self._checkboxes.pop(read_id)
            checkbox.deleteLater()
        for read_view in self._viewer.read_views:
            if read_view.read_id in self._checkboxes:
                continue
            checkbox = QCheckBox(_elide(read_view.read_id, 28), self)
            checkbox.setObjectName(f"sampleCheckbox:{read_view.read_id}")
            checkbox.setChecked(read_view.read_id in self._viewer.visible_read_ids)
            checkbox.toggled.connect(
                lambda checked, read_id=read_view.read_id: self._viewer.set_read_visible(read_id, checked)
            )
            self._checkboxes[read_view.read_id] = checkbox
        for read_view in self._viewer.read_views:
            checkbox = self._checkboxes[read_view.read_id]
            checkbox.blockSignals(True)
            checkbox.setChecked(read_view.read_id in self._viewer.visible_read_ids)
            checkbox.blockSignals(False)

    def _layout_checkboxes(self) -> None:
        self._title_label.setGeometry(10, 4, self.width() - 20, SAMPLE_PANEL_TITLE_HEIGHT - 6)
        button_y = SAMPLE_PANEL_TITLE_HEIGHT
        button_width = (self.width() - 20) // 3
        self._all_button.setGeometry(10, button_y, button_width - 2, 22)
        self._none_button.setGeometry(10 + button_width, button_y, button_width - 2, 22)
        self._invert_button.setGeometry(10 + 2 * button_width, button_y, button_width - 2, 22)
        row_step = SAMPLE_CHECKBOX_HEIGHT + SAMPLE_CHECKBOX_SPACING
        for row_index, read_view in enumerate(self._viewer.read_views):
            checkbox = self._checkboxes.get(read_view.read_id)
            if checkbox is None:
                continue
            y = self._checkbox_top() + row_index * row_step
            checkbox.setGeometry(10, y, self.width() - 20, SAMPLE_CHECKBOX_HEIGHT)
            checkbox.setVisible(y + SAMPLE_CHECKBOX_HEIGHT >= 0 and y <= self.height())
            if read_view.read_id == self._viewer.selected_read_id:
                checkbox.setStyleSheet("background-color: #F1EEFF; font-weight: 600;")
            elif read_view.read_id in self._viewer.visible_read_ids:
                checkbox.setStyleSheet("background-color: transparent;")
            else:
                checkbox.setStyleSheet("background-color: transparent; color: #777777;")

    def select_all(self) -> None:
        for read_view in self._viewer.read_views:
            self._viewer._visible_read_ids.add(read_view.read_id)
        self._viewer.refresh()

    def clear_all(self) -> None:
        self._viewer._visible_read_ids.clear()
        self._viewer._selected_read_id = None
        self._viewer._selected_base = None
        self._viewer.refresh()

    def invert_selection(self) -> None:
        all_ids = {read_view.read_id for read_view in self._viewer.read_views}
        self._viewer._visible_read_ids = all_ids - self._viewer._visible_read_ids
        if self._viewer._selected_read_id not in self._viewer._visible_read_ids:
            self._viewer._selected_read_id = None
            self._viewer._selected_base = None
        self._viewer.refresh()

    def _checkbox_top(self) -> int:
        return SAMPLE_PANEL_TITLE_HEIGHT + 26


class ReadLabelColumnWidget(QWidget):
    """Fixed read-name layer mirroring the Tkinter label_canvas."""

    def __init__(self, viewer: ChromatogramViewer) -> None:
        super().__init__()
        self._viewer = viewer
        self.setFixedWidth(LABEL_WIDTH)
        self.setMinimumWidth(LABEL_WIDTH)
        self.setMaximumWidth(LABEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAutoFillBackground(True)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#FFFFFF"))
        painter.setFont(QFont("Courier", 9, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#333333")))
        row_height = self._viewer._row_height()
        y_offset = self._viewer._y_offset
        for row_index, read_view in enumerate(self._viewer.visible_read_views):
            y = row_index * row_height - y_offset + SEQUENCE_Y * self._viewer.scale_y
            if y > event.rect().bottom() + 20:
                break
            if y < event.rect().top() - 30:
                continue
            painter.drawText(QPointF(5, y), _elide(read_view.read_id, 18))
        painter.setPen(QPen(QColor("#D8D8D8")))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.end()


class ChromatogramCanvasWidget(QGraphicsView):
    """QGraphicsView-backed raw-coordinate waveform viewport.

    The scene owns one graphics item per read.  Trace drawing is kept in a
    lazy, high-DPI tile cache so scale changes and folder opening do not
    rasterize every read across the full trace width at once.
    """

    resized = Signal()

    def __init__(self, viewer: ChromatogramViewer) -> None:
        super().__init__()
        self._viewer = viewer
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pan_anchor: QPointF | None = None
        self._pan_x_offset = 0
        self._pan_y_offset = 0
        self.setMinimumSize(400, 220)
        self.setMouseTracking(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontAdjustForAntialiasing, True)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self._row_items: dict[str, ChromatogramReadGraphicsItem] = {}
        self._paint_profiler: ChromatogramPaintProfiler | None = None
        self._cache_profiler = ChromatogramCacheProfiler()
        self._scene_rebuild_count = 0
        self._trace_pixmap_rebuild_count = 0
        self._pending_tile_jobs: list[tuple[str, int]] = []
        self._pending_tile_job_keys: set[tuple[str, int]] = set()
        self._tile_build_timer = QTimer(self)
        self._tile_build_timer.setInterval(0)
        self._tile_build_timer.timeout.connect(self._process_pending_tile_jobs)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.resized.emit()
        super().resizeEvent(event)

    def rebuild_scene(self) -> None:
        """Rebuild scene items after data, visibility, scale, or selection changes."""

        self._scene_rebuild_count += 1
        self._tile_build_timer.stop()
        self._pending_tile_jobs.clear()
        self._pending_tile_job_keys.clear()
        self._scene.clear()
        self._row_items.clear()
        content_width = self._viewer._content_width()
        content_height = self._viewer._content_height()
        self._scene.setSceneRect(0, 0, content_width, content_height)
        row_height = self._viewer._row_height()
        device_pixel_ratio = self.viewport().devicePixelRatioF()
        for row_index, read_view in enumerate(self._viewer.visible_read_views):
            row_item = ChromatogramReadGraphicsItem(
                read_view,
                row_index=row_index,
                row_height=row_height,
                content_width=content_width,
                scale_x=self._viewer.scale_x,
                scale_y=self._viewer.scale_y,
                show_trim_region=self._viewer.show_trim_region,
                selected_base=self._viewer.selected_base,
                device_pixel_ratio=device_pixel_ratio,
                cache_profiler=self._cache_profiler,
                paint_profiler=self._paint_profiler,
            )
            self._scene.addItem(row_item)
            self._row_items[read_view.read_id] = row_item
        self.set_view_offset(self._viewer._x_offset, self._viewer._y_offset)

    def set_view_offset(self, x_offset: int, y_offset: int) -> None:
        self.horizontalScrollBar().setValue(int(x_offset))
        self.verticalScrollBar().setValue(int(y_offset))
        self.schedule_visible_trace_tiles()

    def visible_x_range(self) -> tuple[float, float]:
        left = float(self._viewer._x_offset)
        right = left + max(1, self.viewport().width())
        return (left, right)

    def ensure_visible_trace_tiles(self) -> None:
        visible_range = self.visible_x_range()
        for row_item in self._visible_row_items():
            before = row_item.trace_pixmap_rebuild_count
            row_item.ensure_visible_trace_tiles(visible_range)
            self._trace_pixmap_rebuild_count += row_item.trace_pixmap_rebuild_count - before

    def schedule_visible_trace_tiles(self) -> None:
        visible_range = self.visible_x_range()
        for row_item in self._visible_row_items():
            for tile_index in row_item.missing_trace_tile_indices(visible_range):
                key = (row_item.read_id, tile_index)
                if key in self._pending_tile_job_keys:
                    continue
                self._pending_tile_job_keys.add(key)
                self._pending_tile_jobs.append(key)
        if self._pending_tile_jobs and not self._tile_build_timer.isActive():
            self._tile_build_timer.start()

    def process_pending_trace_tiles_for_tests(self) -> None:
        while self._pending_tile_jobs:
            self._process_pending_tile_jobs()

    def _process_pending_tile_jobs(self) -> None:
        if not self._pending_tile_jobs:
            self._tile_build_timer.stop()
            return
        started_ns = perf_counter_ns()
        built_any = False
        while self._pending_tile_jobs:
            read_id, tile_index = self._pending_tile_jobs.pop(0)
            self._pending_tile_job_keys.discard((read_id, tile_index))
            row_item = self._row_items.get(read_id)
            if row_item is None or row_item.has_trace_tile(tile_index):
                continue
            before = row_item.trace_pixmap_rebuild_count
            row_item.build_trace_tile(tile_index)
            self._trace_pixmap_rebuild_count += row_item.trace_pixmap_rebuild_count - before
            row_item.update(row_item.trace_tile_rect(tile_index))
            built_any = True
            elapsed_ms = (perf_counter_ns() - started_ns) / 1_000_000
            if elapsed_ms >= TRACE_TILE_BUILD_BUDGET_MS:
                break
        if not self._pending_tile_jobs:
            self._tile_build_timer.stop()
        elif built_any:
            self.viewport().update()

    def _visible_row_items(self) -> tuple["ChromatogramReadGraphicsItem", ...]:
        if not self._row_items:
            return ()
        top = float(self._viewer._y_offset)
        bottom = top + max(1, self.viewport().height())
        row_margin = float(self._viewer._row_height())
        visible_top = max(0.0, top - row_margin)
        visible_bottom = bottom + row_margin
        visible_items: list[ChromatogramReadGraphicsItem] = []
        for row_item in self._row_items.values():
            rect = row_item.sceneBoundingRect()
            if rect.bottom() < visible_top or rect.top() > visible_bottom:
                continue
            visible_items.append(row_item)
        return tuple(visible_items)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        angle_delta = event.angleDelta()
        pixel_delta = event.pixelDelta()
        horizontal_delta = pixel_delta.x() or angle_delta.x()
        vertical_delta = pixel_delta.y() or angle_delta.y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and vertical_delta:
            factor = 1.2 if vertical_delta > 0 else 1 / 1.2
            self._viewer.set_x_scale(self._viewer.scale_x * factor)
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier and vertical_delta:
            horizontal_delta = vertical_delta
            vertical_delta = 0
        self.handle_wheel_delta(horizontal_delta, vertical_delta)
        event.accept()

    def handle_wheel_delta(self, horizontal_delta: int, vertical_delta: int) -> None:
        if horizontal_delta:
            scrollbar = self._viewer._horizontal_scrollbar
            scrollbar.setValue(scrollbar.value() - int(horizontal_delta))
            return
        if vertical_delta:
            scrollbar = self._viewer._vertical_scrollbar
            scrollbar.setValue(scrollbar.value() - int(vertical_delta))

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if (
            event.button() == Qt.MouseButton.MiddleButton
            or (
                event.button() == Qt.MouseButton.LeftButton
                and event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            )
        ):
            self._pan_anchor = event.position()
            self._pan_x_offset = self._viewer._x_offset
            self._pan_y_offset = self._viewer._y_offset
            event.accept()
            return
        scene_position = self.mapToScene(event.position().toPoint())
        content_x = scene_position.x() / self._viewer.scale_x
        content_y = scene_position.y()
        self._viewer.select_base_at(content_x, content_y)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._pan_anchor is not None:
            delta = event.position() - self._pan_anchor
            self._viewer._horizontal_scrollbar.setValue(
                self._pan_x_offset - int(delta.x())
            )
            self._viewer._vertical_scrollbar.setValue(
                self._pan_y_offset - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self._pan_anchor is not None:
            self._pan_anchor = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @property
    def row_items(self) -> dict[str, "ChromatogramReadGraphicsItem"]:
        return dict(self._row_items)

    def scene_item_counts(self) -> dict[str, int]:
        return {
            "scene_items": len(self._scene.items()),
            "read_items": len(self._row_items),
            "trace_items": 0,
            "base_items": 0,
            "tick_items": 0,
            "overlay_items": 0,
            "trim_items": 0,
        }

    def update_selection(self, selected_base: SelectedBaseInfo | None) -> None:
        for row_item in self._row_items.values():
            row_item.set_selected_base(selected_base)

    def enable_paint_profiling(self, *, reset: bool = True) -> None:
        if self._paint_profiler is None:
            self._paint_profiler = ChromatogramPaintProfiler()
        elif reset:
            self._paint_profiler.reset()
        for row_item in self._row_items.values():
            row_item.set_paint_profiler(self._paint_profiler)

    def disable_paint_profiling(self) -> None:
        self._paint_profiler = None
        for row_item in self._row_items.values():
            row_item.set_paint_profiler(None)

    def paint_profile_snapshot(self) -> dict[str, object]:
        if self._paint_profiler is None:
            return ChromatogramPaintProfiler().snapshot()
        return self._paint_profiler.snapshot()

    def cache_profile_snapshot(self) -> dict[str, object]:
        snapshot = self._cache_profiler.snapshot()
        snapshot["tiles_in_memory"] = sum(
            row_item.trace_tile_count for row_item in self._row_items.values()
        )
        snapshot["estimated_cache_memory_mb"] = (
            sum(row_item.trace_cache_memory_bytes for row_item in self._row_items.values())
            / (1024 * 1024)
        )
        return snapshot

    def rebuild_diagnostics(self) -> dict[str, object]:
        return {
            "scene_rebuild_count": self._scene_rebuild_count,
            "trace_pixmap_rebuild_count": self._trace_pixmap_rebuild_count,
            "device_pixel_ratio": self.viewport().devicePixelRatioF(),
            "pending_tile_jobs": len(self._pending_tile_jobs),
        }


class TracePixmapCache:
    """Read-level horizontal tile cache for trace, quality, and trim overlays.

    This object is deliberately isolated so a future bounded/LRU tile cache can
    replace the in-memory dictionary without changing ChromatogramReadGraphicsItem.
    """

    def __init__(
        self,
        read_view: ChromatogramReadView,
        *,
        content_width: int,
        row_height: int,
        scale_x: float,
        scale_y: float,
        show_trim_region: bool,
        device_pixel_ratio: float,
        profiler: ChromatogramCacheProfiler,
    ) -> None:
        self._read_view = read_view
        self._content_width = max(1, int(content_width))
        self._row_height = max(1, int(row_height))
        self._scale_x = scale_x
        self._scale_y = scale_y
        self._show_trim_region = show_trim_region
        self._device_pixel_ratio = max(1.0, float(device_pixel_ratio))
        self._profiler = profiler
        self._tiles: dict[int, QPixmap] = {}
        self._last_build_ns = 0
        self.rebuild_count = 0

    def invalidate(self) -> None:
        self._tiles.clear()

    def ensure_visible(self, visible_x_range: tuple[float, float]) -> None:
        first_tile, last_tile = self._tile_range(visible_x_range)
        for tile_index in range(first_tile, last_tile + 1):
            self.ensure_tile(tile_index)

    def ensure_tile(self, tile_index: int) -> QPixmap:
        cached = self._tiles.get(tile_index)
        if cached is not None:
            self._profiler.record_hit()
            return cached
        self._profiler.record_miss()
        pixmap = self.rebuild_tile(tile_index)
        self._tiles[tile_index] = pixmap
        self._profiler.record_build(
            elapsed_ns=self._last_build_ns,
            logical_width=pixmap.width() / pixmap.devicePixelRatio(),
            logical_height=pixmap.height() / pixmap.devicePixelRatio(),
            physical_width=pixmap.width(),
            physical_height=pixmap.height(),
            device_pixel_ratio=self._device_pixel_ratio,
            tiles_in_memory=len(self._tiles),
            estimated_cache_bytes=self.estimated_memory_bytes(),
        )
        return pixmap

    def has_tile(self, tile_index: int) -> bool:
        return tile_index in self._tiles

    def missing_tile_indices(self, visible_x_range: tuple[float, float]) -> tuple[int, ...]:
        first_tile, last_tile = self._tile_range(visible_x_range)
        return tuple(
            tile_index
            for tile_index in range(first_tile, last_tile + 1)
            if tile_index not in self._tiles
        )

    def build_tile_cached(self, tile_index: int) -> QPixmap:
        return self.ensure_tile(tile_index)

    def rebuild_tile(self, tile_index: int) -> QPixmap:
        self.rebuild_count += 1
        start_ns = perf_counter_ns()
        tile_left = tile_index * TRACE_TILE_WIDTH
        logical_width = min(TRACE_TILE_WIDTH, max(1, self._content_width - tile_left))
        physical_size = QSize(
            max(1, int(round(logical_width * self._device_pixel_ratio))),
            max(1, int(round(self._row_height * self._device_pixel_ratio))),
        )
        pixmap = QPixmap(physical_size)
        pixmap.setDevicePixelRatio(self._device_pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.translate(-tile_left, 0)
        painter.scale(self._scale_x, self._scale_y)
        self._paint_quality(painter)
        if self._show_trim_region:
            self._paint_trim_overlay(painter)
        self._paint_traces(painter)
        painter.end()
        self._last_build_ns = perf_counter_ns() - start_ns
        return pixmap

    def draw_visible(
        self,
        painter: QPainter,
        visible_x_range: tuple[float, float],
    ) -> None:
        first_tile, last_tile = self._tile_range(visible_x_range)
        for tile_index in range(first_tile, last_tile + 1):
            pixmap = self._tiles.get(tile_index)
            if pixmap is None:
                self._profiler.record_miss()
                continue
            self._profiler.record_hit()
            painter.drawPixmap(tile_index * TRACE_TILE_WIDTH, 0, pixmap)

    def tile_rect(self, tile_index: int) -> QRectF:
        tile_left = tile_index * TRACE_TILE_WIDTH
        logical_width = min(TRACE_TILE_WIDTH, max(1, self._content_width - tile_left))
        return QRectF(tile_left, 0, logical_width, self._row_height)

    def estimated_memory_bytes(self) -> int:
        total = 0
        for pixmap in self._tiles.values():
            total += pixmap.width() * pixmap.height() * 4
        return total

    @property
    def tile_count(self) -> int:
        return len(self._tiles)

    def _tile_range(self, visible_x_range: tuple[float, float]) -> tuple[int, int]:
        left, right = visible_x_range
        first_tile = max(0, int(left // TRACE_TILE_WIDTH) - TRACE_TILE_PREFETCH)
        last_tile = max(first_tile, int(right // TRACE_TILE_WIDTH) + TRACE_TILE_PREFETCH)
        max_tile = max(0, int((self._content_width - 1) // TRACE_TILE_WIDTH))
        return (min(first_tile, max_tile), min(last_tile, max_tile))

    def _paint_quality(self, painter: QPainter) -> None:
        path = self._read_view.render_cache.quality_path
        if path is None:
            return
        painter.fillPath(path, QColor("#EEF9FF"))

    def _paint_trim_overlay(self, painter: QPainter) -> None:
        positions = self._read_view.base_positions
        if not positions:
            return
        trim_start = max(0, min(self._read_view.trim_start, len(positions) - 1))
        trim_end = max(0, min(self._read_view.trim_end, len(positions)))
        center_y = TRACE_TOP + TRACE_HEIGHT / 2
        y1 = center_y - TRACE_HEIGHT / 2
        y2 = center_y
        total_width = positions[-1]
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        painter.setBrush(QColor(255, 153, 153, 150))
        if trim_start > 0:
            painter.drawRect(QRectF(0, y1, positions[trim_start], y2 - y1))
        if trim_end < len(positions):
            x1 = positions[trim_end]
            painter.drawRect(QRectF(x1, y1, max(0, total_width - x1), y2 - y1))

    def _paint_traces(self, painter: QPainter) -> None:
        for base in ("A", "C", "G", "T"):
            path = self._read_view.render_cache.trace_paths.get(base)
            if path is None:
                continue
            painter.setPen(QPen(_TRACE_COLORS[base], 1))
            painter.drawPath(path)


class ChromatogramReadGraphicsItem(QGraphicsItem):
    """Single graphics item for one read row.

    The scene intentionally owns one item per read.  Trace, base, tick, quality,
    trim, and read-name drawing happens inside this item's paint method so the
    scene does not contain thousands of tiny text/path items.  This keeps the
    boundary ready for future per-read pixmap or tile caches.
    """

    def __init__(
        self,
        read_view: ChromatogramReadView,
        *,
        row_index: int,
        row_height: int,
        content_width: int,
        scale_x: float,
        scale_y: float,
        show_trim_region: bool,
        selected_base: SelectedBaseInfo | None,
        device_pixel_ratio: float,
        cache_profiler: ChromatogramCacheProfiler,
        paint_profiler: ChromatogramPaintProfiler | None = None,
    ) -> None:
        super().__init__()
        self.read_id = read_view.read_id
        self._read_view = read_view
        self._row_height = row_height
        self._content_width = content_width
        self._scale_x = scale_x
        self._scale_y = scale_y
        self._show_trim_region = show_trim_region
        self._selected_base = selected_base
        self._paint_profiler = paint_profiler
        self._trace_pixmap_cache = TracePixmapCache(
            read_view,
            content_width=content_width,
            row_height=row_height,
            scale_x=scale_x,
            scale_y=scale_y,
            show_trim_region=show_trim_region,
            device_pixel_ratio=device_pixel_ratio,
            profiler=cache_profiler,
        )
        self._last_exposed_left = 0.0
        self._last_exposed_right = float(content_width)
        self.setPos(0, row_index * row_height)

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt override
        return QRectF(0, 0, self._content_width, self._row_height)

    def set_paint_profiler(self, profiler: ChromatogramPaintProfiler | None) -> None:
        self._paint_profiler = profiler

    def set_selected_base(self, selected_base: SelectedBaseInfo | None) -> None:
        self._selected_base = selected_base
        self.update()

    def invalidate_trace_cache(self) -> None:
        self._trace_pixmap_cache.invalidate()

    def ensure_visible_trace_tiles(self, visible_x_range: tuple[float, float]) -> None:
        self._trace_pixmap_cache.ensure_visible(visible_x_range)

    def missing_trace_tile_indices(self, visible_x_range: tuple[float, float]) -> tuple[int, ...]:
        return self._trace_pixmap_cache.missing_tile_indices(visible_x_range)

    def has_trace_tile(self, tile_index: int) -> bool:
        return self._trace_pixmap_cache.has_tile(tile_index)

    def build_trace_tile(self, tile_index: int) -> None:
        self._trace_pixmap_cache.build_tile_cached(tile_index)

    def trace_tile_rect(self, tile_index: int) -> QRectF:
        return self._trace_pixmap_cache.tile_rect(tile_index)

    @property
    def trace_pixmap_rebuild_count(self) -> int:
        return self._trace_pixmap_cache.rebuild_count

    @property
    def trace_tile_count(self) -> int:
        return self._trace_pixmap_cache.tile_count

    @property
    def trace_cache_memory_bytes(self) -> int:
        return self._trace_pixmap_cache.estimated_memory_bytes()

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802 - Qt override
        del widget
        exposed = option.exposedRect.adjusted(-40, -20, 40, 20)
        self._last_exposed_left = max(0.0, exposed.left())
        self._last_exposed_right = min(float(self._content_width), exposed.right())
        profiler = self._paint_profiler
        if profiler is None:
            self._paint_background(painter)
            self._paint_trace_pixmap(painter)

            self._paint_sequence(painter, exposed)
            self._paint_position_ticks(painter, exposed)
            return

        paint_start = perf_counter_ns()
        section_ns: dict[str, int] = {}

        start = perf_counter_ns()
        self._paint_background(painter)
        section_ns["background"] = perf_counter_ns() - start

        start = perf_counter_ns()
        self._paint_trace_pixmap(painter)
        section_ns["trace"] = perf_counter_ns() - start
        section_ns["quality"] = 0
        section_ns["trim"] = 0

        section_ns["read_name"] = 0

        start = perf_counter_ns()
        self._paint_sequence(painter, exposed)
        section_ns["base"] = perf_counter_ns() - start

        start = perf_counter_ns()
        self._paint_position_ticks(painter, exposed)
        section_ns["tick"] = perf_counter_ns() - start

        profiler.record_paint(perf_counter_ns() - paint_start, section_ns)

    def _paint_background(self, painter: QPainter) -> None:
        painter.fillRect(self.boundingRect(), QColor("#FFFFFF"))
        painter.setPen(QPen(QColor("#E2E2E2")))
        painter.drawLine(0, int(self._row_height - 1), int(self._content_width), int(self._row_height - 1))

    def _paint_trace_pixmap(self, painter: QPainter) -> None:
        self._trace_pixmap_cache.draw_visible(
            painter,
            (self._last_exposed_left, self._last_exposed_right),
        )

    def _paint_sequence(self, painter: QPainter, exposed: QRectF) -> None:
        painter.setFont(QFont("Courier", 10, QFont.Weight.Bold))
        sequence_y = SEQUENCE_Y * self._scale_y
        left = exposed.left()
        right = exposed.right()
        for raw_index, base, trace_position, static_text in self._read_view.render_cache.base_items:
            x = trace_position * self._scale_x
            if x < left:
                continue
            if x > right:
                break
            if (
                self._selected_base
                and self._selected_base.read_id == self._read_view.read_id
                and self._selected_base.raw_index == raw_index
            ):
                painter.fillRect(QRectF(x - 8, sequence_y - 12, 16, 24), QColor("#FFF176"))
            painter.setPen(_BASE_COLORS.get(base, QColor("black")))
            painter.drawStaticText(QPointF(x - 5, sequence_y - 8), static_text)

    def _paint_position_ticks(self, painter: QPainter, exposed: QRectF) -> None:
        if not self._read_view.render_cache.tick_items:
            return
        painter.setFont(QFont("Courier", 7))
        painter.setPen(QPen(QColor("#777777")))
        tick_y = RULER_Y * self._scale_y
        left = exposed.left()
        right = exposed.right()
        for trace_position, _label, static_text in self._read_view.render_cache.tick_items:
            x = trace_position * self._scale_x
            if x < left:
                continue
            if x > right:
                break
            painter.drawStaticText(QPointF(x - 4, tick_y), static_text)
            painter.drawLine(int(x), int(tick_y + 10), int(x), int(tick_y + 13))


class ScalePanelWidget(QWidget):
    """Right-side X/Y scale controls mirroring the Tkinter viewer scale bars."""

    def __init__(self, viewer: ChromatogramViewer) -> None:
        super().__init__()
        self._viewer = viewer
        self.setFixedWidth(SCALE_PANEL_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #F2F2F2;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 4, 1, 2)
        layout.setSpacing(2)

        bars_layout = QHBoxLayout()
        bars_layout.setContentsMargins(0, 0, 0, 0)
        bars_layout.setSpacing(1)

        self.y_slider = QScrollBar(Qt.Orientation.Vertical)
        self.y_slider.setRange(Y_SCALE_MIN, Y_SCALE_MAX)
        self.y_slider.setSingleStep(5)
        self.y_slider.setPageStep(40)
        self.y_slider.setValue(100)
        self.y_slider.setObjectName("chromatogramYScaleSlider")
        self.y_slider.setFixedWidth(17)
        self.y_slider.setStyleSheet(_scale_slider_stylesheet())
        self.y_slider.valueChanged.connect(self._y_slider_value_changed)
        self.y_slider.sliderReleased.connect(viewer.commit_pending_scale)
        bars_layout.addWidget(self.y_slider, 1)

        self.x_slider = QScrollBar(Qt.Orientation.Vertical)
        self.x_slider.setRange(X_SCALE_MIN, X_SCALE_MAX)
        self.x_slider.setSingleStep(10)
        self.x_slider.setPageStep(100)
        self.x_slider.setValue(100)
        self.x_slider.setObjectName("chromatogramXScaleSlider")
        self.x_slider.setFixedWidth(17)
        self.x_slider.setStyleSheet(_scale_slider_stylesheet())
        self.x_slider.valueChanged.connect(self._x_slider_value_changed)
        self.x_slider.sliderReleased.connect(viewer.commit_pending_scale)
        bars_layout.addWidget(self.x_slider, 1)
        layout.addLayout(bars_layout, 1)

        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(0)
        y_label = QLabel("y")
        x_label = QLabel("x")
        for label in (y_label, x_label):
            label.setStyleSheet("font-family: Arial; font-size: 9px; background: #F2F2F2;")
            label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        label_layout.addWidget(y_label, 1)
        label_layout.addWidget(x_label, 1)
        layout.addLayout(label_layout)

    def _x_slider_value_changed(self, value: int) -> None:
        if self.x_slider.isSliderDown():
            self._viewer.preview_x_scale(value / 100)
        else:
            self._viewer.set_x_scale(value / 100)

    def _y_slider_value_changed(self, value: int) -> None:
        if self.y_slider.isSliderDown():
            self._viewer.preview_y_scale(value / 100)
        else:
            self._viewer.set_y_scale(value / 100)


class SelectedBasePanel(QFrame):
    """Tkinter Main Viewer-style selected base inspector."""

    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        title = QLabel("Selected Read / Base")
        title.setStyleSheet("font-weight: 600;")
        self._detail = QLabel()
        self._detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._detail.setStyleSheet("font-family: Menlo, Monaco, monospace;")
        layout.addWidget(title)
        layout.addWidget(self._detail)
        self.set_selection(None, None)

    def set_selected_base(self, info: SelectedBaseInfo | None) -> None:
        self.set_selection(None, info)

    def set_selection(
        self,
        read_view: ChromatogramReadView | None,
        info: SelectedBaseInfo | None,
    ) -> None:
        read_id = getattr(read_view, "read_id", None) or getattr(info, "read_id", "—")
        length = getattr(read_view, "sequence_length", "—")
        mean_q = (
            f"{getattr(read_view, 'average_quality'):.1f}"
            if read_view is not None
            else "—"
        )
        q20 = f"{getattr(read_view, 'q20_rate'):.1f}%" if read_view is not None else "—"
        q30 = f"{getattr(read_view, 'q30_rate'):.1f}%" if read_view is not None else "—"
        trim = (
            f"{getattr(read_view, 'trim_start')}–{getattr(read_view, 'trim_end')}"
            if read_view is not None
            else "—"
        )
        if info is None:
            self._detail.setText(
                f"Sample: {read_id}\n"
                f"Length: {length}   Mean Q: {mean_q}   Q20: {q20}   Q30: {q30}   Trim: {trim}\n"
                "Base: —   Quality: —   Region: —\n"
                "Raw index (0-based): —   Trim index (0-based): —\n"
                "Raw trace: —   Trim trace: —"
            )
            return
        self._detail.setText(
            f"Sample: {info.read_id}\n"
            f"Length: {length}   Mean Q: {mean_q}   Q20: {q20}   Q30: {q30}   Trim: {trim}\n"
            f"Base: {info.base}   Quality: {info.quality}   Region: {info.region}\n"
            f"Raw index (0-based): {info.raw_index}   "
            f"Trim index (0-based): {_dash(info.trim_index)}\n"
            f"Raw trace: {info.raw_trace_position}   "
            f"Trim trace: {_dash(info.trim_trace_position)}"
        )

    def text(self) -> str:
        return self._detail.text()


def create_chromatogram_viewer_from_dataset(
    context: object,
    dataset: object,
) -> ChromatogramViewer:
    return ChromatogramViewer(
        reads_from_dataset(dataset),
        title=f"Chromatograms: {getattr(dataset, 'name', _dataset_identifier(dataset))}",
        source_object_id=_dataset_identifier(dataset),
        context=context,
        source_dataset=dataset,
    )


def reads_from_dataset(dataset: object) -> tuple[SangerRead, ...]:
    reads: list[SangerRead] = []
    for record in getattr(dataset, "records", ()):
        source = getattr(record, "source_reference", None)
        if isinstance(source, SangerRead):
            reads.append(source)
    return tuple(reads)


def has_chromatogram_sources(dataset: object) -> bool:
    return bool(reads_from_dataset(dataset))


def _read_view(read: SangerRead) -> ChromatogramReadView:
    sequence = read.sequence or ""
    quality = tuple(read.quality or ())
    traces = {base: tuple(values) for base, values in (read.traces or {}).items()}
    base_positions = tuple(read.base_positions or ())
    trim_end = read.trim_end if read.trim_end else len(sequence)
    return ChromatogramReadView(
        read_id=read.filename,
        read=read,
        sequence=sequence,
        quality=quality,
        traces=traces,
        base_positions=base_positions,
        trim_start=read.trim_start,
        trim_end=trim_end,
        trimmed_base_positions=tuple(read.trimmed_base_positions or ()),
        render_cache=_build_render_cache(
            sequence=sequence,
            quality=quality,
            traces=traces,
            base_positions=base_positions,
            trim_start=read.trim_start,
            trim_end=trim_end,
        ),
    )


def _build_render_cache(
    *,
    sequence: str,
    quality: tuple[int, ...],
    traces: dict[str, tuple[int, ...]],
    base_positions: tuple[int, ...],
    trim_start: int,
    trim_end: int,
) -> ChromatogramRenderCache:
    return ChromatogramRenderCache(
        trace_paths=_build_trace_paths(traces),
        quality_path=_build_quality_path(quality, base_positions),
        base_items=tuple(
            (
                raw_index,
                base,
                base_positions[raw_index],
                QStaticText(base),
            )
            for raw_index, base in enumerate(sequence[: len(base_positions)])
        ),
        tick_items=_build_tick_items(base_positions, trim_start, trim_end),
    )


def _build_trace_paths(traces: dict[str, tuple[int, ...]]) -> dict[str, QPainterPath]:
    paths: dict[str, QPainterPath] = {}
    center_y = TRACE_TOP + TRACE_HEIGHT / 2
    for base in ("A", "C", "G", "T"):
        trace = traces.get(base, ())
        if not trace:
            continue
        maximum = max(trace) or 1
        path = QPainterPath()
        path.moveTo(0, center_y - (trace[0] / maximum) * TRACE_HEIGHT / 2)
        for index, value in enumerate(trace[1:], start=1):
            path.lineTo(index, center_y - (value / maximum) * TRACE_HEIGHT / 2)
        paths[base] = path
    return paths


def _build_quality_path(
    quality: tuple[int, ...],
    base_positions: tuple[int, ...],
) -> QPainterPath | None:
    if not quality or not base_positions:
        return None
    center_y = TRACE_TOP + TRACE_HEIGHT / 2
    max_height = TRACE_HEIGHT / 2
    first_x = base_positions[0]
    first_height = min(quality[0], 40) / 40 * max_height
    path = QPainterPath(QPointF(first_x, center_y - first_height))
    last_x = first_x
    for index, q_value in enumerate(quality[1:], start=1):
        if index >= len(base_positions):
            break
        x = base_positions[index]
        last_x = x
        height = min(q_value, 40) / 40 * max_height
        path.lineTo(x, center_y - height)
    path.lineTo(last_x, center_y)
    path.lineTo(first_x, center_y)
    path.closeSubpath()
    return path


def _build_tick_items(
    base_positions: tuple[int, ...],
    trim_start: int,
    trim_end: int,
) -> tuple[tuple[int, str, QStaticText], ...]:
    if not base_positions:
        return ()
    start = max(0, trim_start)
    end = min(len(base_positions), trim_end)
    items = []
    for trimmed_position, raw_index in enumerate(range(start, end), start=1):
        if trimmed_position == 1 or trimmed_position % 10 == 0:
            label = str(trimmed_position)
            items.append((base_positions[raw_index], label, QStaticText(label)))
    return tuple(items)


def _selected_base_info(read_view: ChromatogramReadView, raw_index: int) -> SelectedBaseInfo:
    trim_start = read_view.trim_start
    trim_end = min(read_view.trim_end, read_view.sequence_length)
    in_trim = trim_start <= raw_index < trim_end
    trim_index = raw_index - trim_start if in_trim else None
    trim_trace_position = (
        read_view.trimmed_base_positions[trim_index]
        if trim_index is not None and trim_index < len(read_view.trimmed_base_positions)
        else None
    )
    return SelectedBaseInfo(
        read_id=read_view.read_id,
        base=read_view.sequence[raw_index] if raw_index < read_view.sequence_length else "—",
        quality=read_view.quality[raw_index] if raw_index < len(read_view.quality) else "—",
        region="TRIMMED" if in_trim else "OUTSIDE TRIM",
        raw_index=raw_index,
        trim_index=trim_index,
        raw_trace_position=read_view.base_positions[raw_index],
        trim_trace_position=trim_trace_position,
    )


def _dataset_identifier(dataset: object) -> str:
    return (
        getattr(dataset, "dataset_id", None)
        or getattr(dataset, "alignment_id", None)
        or str(id(dataset))
    )


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )


def _elide(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: max(0, limit - 1)]}…"


def _dash(value: object | None) -> object:
    return "—" if value is None else value


def _format_paint_profile_snapshot(snapshot: dict[str, object]) -> str:
    sections = snapshot.get("sections", {})
    lines = [
        "=== Chromatogram Paint Profile ===",
        f"paint calls: {snapshot.get('paint_calls', 0)}",
        f"total paint ms: {_format_ms(snapshot.get('total_ms', 0.0))}",
        f"avg paint ms: {_format_ms(snapshot.get('avg_paint_ms', 0.0))}",
        "",
    ]
    diagnostics = snapshot.get("rebuild_diagnostics", {})
    if isinstance(diagnostics, dict):
        lines.extend(
            (
                f"scene rebuilds: {diagnostics.get('scene_rebuild_count', 0)}",
                f"trace pixmap rebuilds: {diagnostics.get('trace_pixmap_rebuild_count', 0)}",
                f"device pixel ratio: {_format_ms(diagnostics.get('device_pixel_ratio', 1.0))}",
                "",
            )
        )
    cache_profile = snapshot.get("cache_profile", {})
    if isinstance(cache_profile, dict):
        lines.extend(
            (
                "=== Chromatogram Cache Profile ===",
                f"tile builds: {cache_profile.get('tile_builds', 0)}",
                f"total build ms: {_format_ms(cache_profile.get('total_build_ms', 0.0))}",
                f"avg tile build ms: {_format_ms(cache_profile.get('avg_tile_build_ms', 0.0))}",
                f"cache hits: {cache_profile.get('cache_hits', 0)}",
                f"cache misses: {cache_profile.get('cache_misses', 0)}",
                f"tiles in memory: {cache_profile.get('tiles_in_memory', 0)}",
                f"estimated cache memory MB: {_format_ms(cache_profile.get('estimated_cache_memory_mb', 0.0))}",
                f"DPR: {_format_ms(cache_profile.get('device_pixel_ratio', 1.0))}",
                "last tile logical: "
                f"{_format_ms(cache_profile.get('last_logical_width', 0.0))} x "
                f"{_format_ms(cache_profile.get('last_logical_height', 0.0))}",
                "last tile physical: "
                f"{cache_profile.get('last_physical_width', 0)} x "
                f"{cache_profile.get('last_physical_height', 0)}",
                "",
            )
        )
    for section in ("background", "quality", "trim", "trace", "read_name", "base", "tick"):
        section_data = sections.get(section, {}) if isinstance(sections, dict) else {}
        lines.append(
            f"{section}: "
            f"calls={section_data.get('calls', 0)} "
            f"total_ms={_format_ms(section_data.get('total_ms', 0.0))} "
            f"avg_ms={_format_ms(section_data.get('avg_ms', 0.0))}"
        )
    lines.extend(
        (
            "",
            f"dominant section: {snapshot.get('dominant_section') or '—'}",
        )
    )
    return "\n".join(lines)


def _emit_profile_output(text: str) -> None:
    print(text, flush=True)


def _format_ms(value: object) -> str:
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return "0.000"


def _scale_slider_stylesheet() -> str:
    return """
        QScrollBar:vertical {
            width: 10px;
            background: #F0F0F0;
            margin: 0px;
            border: none;
        }
        QScrollBar::handle:vertical {
            min-height: 28px;
            background: #8A8A8A;
            border-radius: 4px;
        }
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
            border: none;
            background: transparent;
        }
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: #F0F0F0;
        }
    """


def _thin_horizontal_scrollbar_stylesheet() -> str:
    return """
        QScrollBar:horizontal {
            height: 10px;
            background: #F0F0F0;
            margin: 0px;
            border: none;
        }
        QScrollBar::handle:horizontal {
            min-width: 28px;
            background: #8A8A8A;
            border-radius: 4px;
        }
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
            border: none;
            background: transparent;
        }
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: #E3E3E3;
        }
    """
