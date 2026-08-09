"""Alignment-coordinate chromatogram viewer for PySide6 Studio.

This ports the Tkinter ``Align Chromatograms`` behavior rather than embedding
the raw-coordinate ChromatogramViewer.  The horizontal display axis is the
alignment column, so gap columns occupy real screen space and every read is
vertically synchronized by alignment position.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QScrollBar,
    QVBoxLayout,
    QWidget,
)

from app.selection import SelectionKind, StudioSelection
from core.alignment_mapper import alignment_to_trace_positions, trace_to_alignment_positions
from core.chromatogram_alignment import align_reads
from core.consensus import build_quality_consensus
from core.models import SangerRead
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


NAME_WIDTH = 210
BASE_WIDTH = 28
ROW_HEIGHT = 200
CONSENSUS_Y = 60
FIRST_READ_Y = 170
BASE_Y_OFFSET = -35
TRACE_SCALE = 0.05
RULER_Y = 18
LOCAL_TRACE_WINDOW = 20
LOCAL_TRACE_COLUMN_FRACTION = 0.9
LOCAL_TRACE_SAMPLE_STEP = 2

_TRACE_COLORS = {
    "A": QColor("green"),
    "T": QColor("red"),
    "G": QColor("black"),
    "C": QColor("blue"),
}
_BASE_COLORS = {
    "A": QColor("green"),
    "T": QColor("red"),
    "G": QColor("black"),
    "C": QColor("blue"),
}


class AlignmentChromatogramViewer(BaseViewer):
    """Review chromatograms in MAFFT alignment-column coordinates."""

    def __init__(
        self,
        reads: Iterable[SangerRead],
        *,
        alignment: object | None = None,
        context: object | None = None,
        source_object_id: str | None = None,
    ) -> None:
        self._reads = tuple(reads)
        self._context = context
        self._visibility_source_key = source_object_id or f"alignment-chromatogram:{id(self)}"
        self._visibility_manager = getattr(context, "read_visibility_manager", None)
        self._alignment = alignment if alignment is not None else align_reads(self._reads)
        self._maps = _build_alignment_maps(self._alignment, self._reads)
        self._reverse_maps = {
            sample_name: trace_to_alignment_positions(mapping)
            for sample_name, mapping in self._maps.items()
        }
        self._consensus, self._confidence, self._consensus_warning = (
            _build_alignment_consensus(self._reads, self._alignment)
        )
        self._selected_cell: tuple[str, int] | None = None
        self._selected_trace_position: int | None = None
        self._show_trim_region = False
        self._visible_read_ids = {read.filename for read in self._reads}
        if self._visibility_manager is not None:
            read_ids = tuple(read.filename for read in self._reads)
            self._visibility_manager.initialize_source(self._visibility_source_key, read_ids)
            self._visible_read_ids = set(
                self._visibility_manager.visible_ids(self._visibility_source_key, read_ids)
            )
            self._visibility_manager.visibility_changed.connect(self._visibility_changed)
        self._x_offset = 0
        self._y_offset = 0
        self._action_provider = AlignmentChromatogramActionProvider()
        super().__init__(
            viewer_id=f"alignment-chromatogram-{_safe_identifier(source_object_id) if source_object_id else id(self)}",
            viewer_title="Align Chromatograms",
            viewer_kind="alignment-chromatogram",
            source_object_id=source_object_id,
        )
        self._build_ui()

    @property
    def reads(self) -> tuple[SangerRead, ...]:
        return self._reads

    @property
    def alignment(self) -> object:
        return self._alignment

    @property
    def consensus(self) -> str:
        return self._consensus

    @property
    def maps(self) -> dict[str, dict[int, int | None]]:
        return self._maps

    @property
    def selected_cell(self) -> tuple[str, int] | None:
        return self._selected_cell

    @property
    def show_trim_region(self) -> bool:
        return self._show_trim_region

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "alignment_chromatogram.align",
            "alignment_chromatogram.toggle_trim_region",
            "alignment_chromatogram.open_quality_report",
            "alignment_chromatogram.build_consensus",
            "alignment_chromatogram.export",
            "alignment_chromatogram.run_blast",
        )

    def alignment_column_to_trace_position(
        self,
        sample_name: str,
        alignment_column: int,
    ) -> int | None:
        """Return existing-core 1-based alignment column to trim trace position."""

        return self._maps.get(sample_name, {}).get(alignment_column)

    def select_alignment_cell(
        self,
        row_index: int,
        column_index: int,
    ) -> tuple[str, int, str, int | None] | None:
        """Select an alignment-coordinate chromatogram cell."""

        records = self._visible_records()
        if row_index < 0 or row_index >= len(records):
            return None
        record = records[row_index]
        sequence = str(record.seq)
        if column_index < 0 or column_index >= len(sequence):
            return None
        sample_name = record.id
        alignment_column = column_index + 1
        base = sequence[column_index]
        trace_position = self.alignment_column_to_trace_position(
            sample_name,
            alignment_column,
        )
        self._selected_cell = (sample_name, alignment_column)
        self._selected_trace_position = trace_position
        self._center_on_alignment_column(alignment_column, row_index)
        self._update_status(sample_name, alignment_column, base, trace_position)
        self._canvas_widget.update()
        self.selection_changed.emit(
            StudioSelection(
                kind=SelectionKind.SEQUENCE_RECORD,
                object_id=sample_name,
                payload={
                    "sample_name": sample_name,
                    "alignment_column": alignment_column,
                    "base": base,
                    "trace_position": trace_position,
                    "coordinate_system": "alignment-column",
                },
                source_viewer_id=self.viewer_id,
            )
        )
        return sample_name, alignment_column, base, trace_position

    def select_trace_position(
        self,
        sample_name: str,
        trim_trace_position: int,
    ) -> tuple[str, int, str, int | None] | None:
        """Synchronize a trim-trace selection back to an alignment column."""

        alignment_column = self._reverse_maps.get(sample_name, {}).get(trim_trace_position)
        if alignment_column is None:
            return None
        row_index = _record_index(self._visible_records(), sample_name)
        if row_index is None:
            return None
        return self.select_alignment_cell(row_index, alignment_column - 1)

    def align(self) -> None:
        """Rerun the existing MAFFT alignment path for the current reads."""

        self._alignment = align_reads(self._reads)
        self._maps = _build_alignment_maps(self._alignment, self._reads)
        self._reverse_maps = {
            sample_name: trace_to_alignment_positions(mapping)
            for sample_name, mapping in self._maps.items()
        }
        self._consensus, self._confidence, self._consensus_warning = (
            _build_alignment_consensus(self._reads, self._alignment)
        )
        self._selected_cell = None
        self._selected_trace_position = None
        if self._visibility_manager is not None:
            read_ids = tuple(read.filename for read in self._reads)
            self._visibility_manager.initialize_source(self._visibility_source_key, read_ids)
            self._visible_read_ids = set(
                self._visibility_manager.visible_ids(self._visibility_source_key, read_ids)
            )
        self.refresh()

    def toggle_trim_region(self) -> None:
        self._show_trim_region = not self._show_trim_region
        self._canvas_widget.update()
        state = "shown" if self._show_trim_region else "hidden"
        self.status_message_changed.emit(f"Trim region overlay {state}.")

    def open_quality_report(self) -> object | None:
        context = self._context
        dock_manager = getattr(context, "dock_manager", None)
        if dock_manager is not None:
            from widgets.viewers.chromatogram_viewer import _read_view

            dock = dock_manager.show_quality_report(
                tuple(_read_view(read) for read in self._reads),
                source_key=self._visibility_source_key,
            )
            if dock is not None:
                return dock
        self.open_related_requested.emit({"action": "QUALITY_REPORT", "viewer": self})
        return None

    def request_consensus(self) -> None:
        self.open_related_requested.emit(
            {"action": "CONSENSUS", "viewer": self, "reads": self._reads}
        )

    def request_export(self) -> None:
        self.export_requested.emit(
            {"viewer": self, "consensus": self._consensus, "alignment": self._alignment}
        )

    def request_blast(self) -> None:
        self.open_related_requested.emit(
            {"action": "BLAST", "viewer": self, "reads": self._reads}
        )

    def refresh(self) -> None:
        self._summary.setText(
            f"Reads: {len(self._visible_records())}/{len(self._records())}    "
            f"Alignment length: {_alignment_length(self._alignment)}    "
            f"Consensus length: {len(self._consensus)}"
        )
        if self._consensus_warning:
            self._status.setText(self._consensus_warning)
        elif self._selected_cell is None:
            self._status.setText("Select an aligned base or gap column.")
        self._update_scroll_ranges()
        self._canvas_widget.update()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        layout.addWidget(self._summary)
        self._status = QLabel()
        layout.addWidget(self._status)

        viewer_area = QGridLayout()
        viewer_area.setContentsMargins(0, 0, 0, 0)
        viewer_area.setHorizontalSpacing(0)
        viewer_area.setVerticalSpacing(0)
        self._canvas_widget = AlignmentChromatogramCanvasWidget(self)
        self._horizontal_scrollbar = QScrollBar(Qt.Orientation.Horizontal)
        self._vertical_scrollbar = QScrollBar(Qt.Orientation.Vertical)
        viewer_area.addWidget(self._canvas_widget, 0, 0)
        viewer_area.addWidget(self._vertical_scrollbar, 0, 1)
        viewer_area.addWidget(self._horizontal_scrollbar, 1, 0)
        viewer_area.setColumnStretch(0, 1)
        viewer_area.setRowStretch(0, 1)
        layout.addLayout(viewer_area, 1)

        self._horizontal_scrollbar.valueChanged.connect(self._set_x_offset)
        self._vertical_scrollbar.valueChanged.connect(self._set_y_offset)
        self._canvas_widget.resized.connect(self._update_scroll_ranges)
        self.refresh()

    def _set_x_offset(self, value: int) -> None:
        self._x_offset = value
        self._canvas_widget.update()

    def _set_y_offset(self, value: int) -> None:
        self._y_offset = value
        self._canvas_widget.update()

    def _update_scroll_ranges(self) -> None:
        viewport_width = max(1, self._canvas_widget.width())
        viewport_height = max(1, self._canvas_widget.height())
        plot_width = max(1, viewport_width - NAME_WIDTH)
        max_x = max(0, self._alignment_plot_width() - plot_width)
        max_y = max(0, self._content_height() - viewport_height)
        self._horizontal_scrollbar.setRange(0, max_x)
        self._horizontal_scrollbar.setPageStep(plot_width)
        self._horizontal_scrollbar.setSingleStep(BASE_WIDTH * 5)
        self._vertical_scrollbar.setRange(0, max_y)
        self._vertical_scrollbar.setPageStep(viewport_height)
        self._vertical_scrollbar.setSingleStep(max(1, ROW_HEIGHT // 2))
        self._x_offset = min(self._x_offset, max_x)
        self._y_offset = min(self._y_offset, max_y)
        if self._horizontal_scrollbar.value() != self._x_offset:
            self._horizontal_scrollbar.setValue(self._x_offset)
        if self._vertical_scrollbar.value() != self._y_offset:
            self._vertical_scrollbar.setValue(self._y_offset)

    def _content_width(self) -> int:
        return NAME_WIDTH + self._alignment_plot_width()

    def _alignment_plot_width(self) -> int:
        return _alignment_length(self._alignment) * BASE_WIDTH + 80

    def _content_height(self) -> int:
        return FIRST_READ_Y + len(self._visible_records()) * ROW_HEIGHT + 80

    def _center_on_alignment_column(self, alignment_column: int, row_index: int) -> None:
        column_x = (alignment_column - 1) * BASE_WIDTH
        plot_width = max(1, self._canvas_widget.width() - NAME_WIDTH)
        self._horizontal_scrollbar.setValue(
            max(0, int(column_x - plot_width / 2))
        )
        row_y = FIRST_READ_Y + row_index * ROW_HEIGHT
        self._vertical_scrollbar.setValue(
            max(0, int(row_y - self._canvas_widget.height() / 3))
        )

    def _update_status(
        self,
        sample_name: str,
        alignment_column: int,
        base: str,
        trace_position: int | None,
    ) -> None:
        extra = "    Gap/no trace coordinate" if trace_position is None else ""
        self._status.setText(
            f"Sample: {sample_name}    Alignment column: {alignment_column}    "
            f"Base: {base}    Trim trace position: {_dash(trace_position)}{extra}"
        )

    def _records(self) -> tuple[object, ...]:
        return tuple(self._alignment)

    def _visible_records(self) -> tuple[object, ...]:
        return tuple(
            record
            for record in self._records()
            if record.id in self._visible_read_ids
        )

    def _visibility_changed(self, source_key: str, visible_ids: object) -> None:
        if source_key != self._visibility_source_key:
            return
        self._visible_read_ids = set(tuple(visible_ids))
        if self._selected_cell and self._selected_cell[0] not in self._visible_read_ids:
            self._selected_cell = None
            self._selected_trace_position = None
        self.refresh()

    def _read_by_name(self, sample_name: str) -> SangerRead:
        for read in self._reads:
            if read.filename == sample_name:
                return read
        raise KeyError(sample_name)


class AlignmentChromatogramCanvasWidget(QWidget):
    """One alignment-coordinate canvas for consensus, bases, gaps, and traces."""

    resized = Signal()

    def __init__(self, viewer: AlignmentChromatogramViewer) -> None:
        super().__init__()
        self._viewer = viewer
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.resized.emit()
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        angle_delta = event.angleDelta()
        pixel_delta = event.pixelDelta()
        horizontal_delta = pixel_delta.x() or angle_delta.x()
        vertical_delta = pixel_delta.y() or angle_delta.y()
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
        content_x = event.position().x() + self._viewer._x_offset
        content_y = event.position().y() + self._viewer._y_offset
        selection = self._selection_from_content_position(content_x, content_y)
        if selection is not None:
            row_index, alignment_column = selection
            self._viewer.select_alignment_cell(row_index, alignment_column - 1)
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("white"))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(QFont("Menlo", 10))
        self._draw_ruler(painter)
        self._draw_selected_column(painter)
        self._draw_consensus(painter)
        self._draw_reads(painter)

    def _draw_ruler(self, painter: QPainter) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#555555")))
        y = RULER_Y - self._viewer._y_offset
        painter.drawText(5, y + 4, "Position")
        first_col, last_col = self._visible_columns()
        painter.setClipRect(self._plot_rect())
        for column in range(first_col, last_col + 1):
            x = self._viewport_x_for_column(column)
            if column == 1 or column % 10 == 0:
                painter.drawLine(int(x), int(y + 8), int(x), int(y + 16))
                painter.drawText(QRectF(x - 14, y - 10, 38, 14), Qt.AlignmentFlag.AlignCenter, str(column))
            else:
                painter.drawLine(int(x), int(y + 12), int(x), int(y + 16))
        painter.restore()

    def _draw_selected_column(self, painter: QPainter) -> None:
        if self._viewer.selected_cell is None:
            return
        _sample_name, alignment_column = self._viewer.selected_cell
        x = self._viewport_x_for_column(alignment_column) - BASE_WIDTH / 2
        painter.save()
        painter.setClipRect(self._plot_rect())
        painter.fillRect(
            QRectF(x, 0, BASE_WIDTH, self.height()),
            QColor(180, 120, 230, 45),
        )
        painter.setPen(QPen(QColor("#7B3FBF"), 2))
        painter.drawRect(QRectF(x, 0, BASE_WIDTH, self.height() - 1))
        painter.restore()

    def _draw_consensus(self, painter: QPainter) -> None:
        y = CONSENSUS_Y - self._viewer._y_offset
        if y < -30 or y > self.height() + 30:
            return
        painter.save()
        painter.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#222222")))
        painter.drawText(5, int(y), "Consensus")
        painter.setClipRect(self._plot_rect())
        first_col, last_col = self._visible_columns()
        for column in range(first_col, min(last_col, len(self._viewer.consensus)) + 1):
            base = self._viewer.consensus[column - 1]
            self._draw_base(painter, base, column, y, bold=True)
        painter.restore()

    def _draw_reads(self, painter: QPainter) -> None:
        records = self._viewer._visible_records()
        first_col, last_col = self._visible_columns()
        for row_index, record in enumerate(records):
            y_base = FIRST_READ_Y + row_index * ROW_HEIGHT - self._viewer._y_offset
            if y_base < -ROW_HEIGHT or y_base > self.height() + ROW_HEIGHT:
                continue
            sample_name = record.id
            mapping = self._viewer.maps.get(sample_name, {})
            read = self._viewer._read_by_name(sample_name)
            self._draw_read_name(painter, sample_name, y_base, row_index)
            if self._viewer.show_trim_region:
                self._draw_trim_region(painter, read, mapping, y_base)
            self._draw_trace(painter, read, mapping, y_base, first_col, last_col)
            self._draw_aligned_bases(painter, str(record.seq), y_base, first_col, last_col)

    def _draw_read_name(
        self,
        painter: QPainter,
        sample_name: str,
        y_base: float,
        row_index: int,
    ) -> None:
        painter.save()
        if self._viewer.selected_cell and self._viewer.selected_cell[0] == sample_name:
            painter.fillRect(
                QRectF(0, y_base - 62, NAME_WIDTH - 8, 78),
                QColor("#E8F1FF"),
            )
        painter.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        painter.setPen(QPen(QColor("#222222")))
        painter.drawText(5, int(y_base), sample_name)
        painter.setPen(QPen(QColor("#DDDDDD")))
        painter.drawLine(0, int(FIRST_READ_Y + row_index * ROW_HEIGHT + 30 - self._viewer._y_offset), self.width(), int(FIRST_READ_Y + row_index * ROW_HEIGHT + 30 - self._viewer._y_offset))
        painter.restore()

    def _draw_aligned_bases(
        self,
        painter: QPainter,
        sequence: str,
        y_base: float,
        first_col: int,
        last_col: int,
    ) -> None:
        painter.save()
        painter.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
        for column in range(first_col, min(last_col, len(sequence)) + 1):
            base = sequence[column - 1]
            self._draw_base(painter, base, column, y_base + BASE_Y_OFFSET, bold=True)
        painter.restore()

    def _draw_trace(
        self,
        painter: QPainter,
        read: SangerRead,
        mapping: dict[int, int | None],
        y_base: float,
        first_col: int,
        last_col: int,
    ) -> None:
        traces = _display_traces(read)
        if not traces or not traces.get("A"):
            return
        painter.save()
        painter.setClipRect(self._plot_rect())
        for base, color in _TRACE_COLORS.items():
            trace = traces.get(base, ())
            painter.setPen(QPen(color, 1.3))
            for segment in _local_trace_segments(mapping, trace, first_col=first_col, last_col=last_col):
                if len(segment) < 2:
                    continue
                painter.drawPath(
                    _smoothed_trace_path(
                        segment,
                        x_offset=self._viewer._x_offset,
                        y_base=y_base,
                    )
                )
        painter.restore()

    def _draw_trim_region(
        self,
        painter: QPainter,
        read: SangerRead,
        mapping: dict[int, int | None],
        y_base: float,
    ) -> None:
        trim_start = getattr(read, "trim_start", 0) or 0
        trim_end = getattr(read, "trim_end", len(getattr(read, "sequence", ""))) or 0
        sequence = getattr(read, "sequence", "") or ""
        if not sequence:
            return
        trim_columns = {
            column
            for column, trace_position in mapping.items()
            if trace_position is not None
            and _trim_index_for_trace_position(read, trace_position) is not None
        }
        if not trim_columns:
            return
        first_trim_column = min(trim_columns)
        last_trim_column = max(trim_columns)
        first_col = 1
        last_col = _alignment_length(self._viewer.alignment)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 120, 120, 45))
        painter.setClipRect(self._plot_rect())
        if trim_start > 0:
            self._draw_column_span(painter, first_col, first_trim_column - 1, y_base - 90, 120)
        if trim_end < len(sequence):
            self._draw_column_span(painter, last_trim_column + 1, last_col, y_base - 90, 120)
        painter.restore()

    def _draw_column_span(
        self,
        painter: QPainter,
        start_column: int,
        end_column: int,
        top: float,
        height: float,
    ) -> None:
        if end_column < start_column:
            return
        x1 = self._viewport_x_for_column(start_column) - BASE_WIDTH / 2
        x2 = self._viewport_x_for_column(end_column) + BASE_WIDTH / 2
        painter.drawRect(QRectF(x1, top, x2 - x1, height))

    def _draw_base(
        self,
        painter: QPainter,
        base: str,
        alignment_column: int,
        y: float,
        *,
        bold: bool = False,
    ) -> None:
        color = _base_color(base)
        painter.setPen(QPen(color))
        x = self._viewport_x_for_column(alignment_column)
        painter.drawText(
            QRectF(x - BASE_WIDTH / 2, y - 12, BASE_WIDTH, 16),
            Qt.AlignmentFlag.AlignCenter,
            base,
        )

    def _selection_from_content_position(
        self,
        content_x: float,
        content_y: float,
    ) -> tuple[int, int] | None:
        viewport_x = content_x - self._viewer._x_offset
        if viewport_x < NAME_WIDTH or content_y < FIRST_READ_Y - ROW_HEIGHT / 2:
            return None
        column = int((content_x - NAME_WIDTH) / BASE_WIDTH) + 1
        row = int((content_y - FIRST_READ_Y + ROW_HEIGHT / 2) / ROW_HEIGHT)
        if row < 0 or row >= len(self._viewer._visible_records()):
            return None
        if column < 1 or column > _alignment_length(self._viewer.alignment):
            return None
        return row, column

    def _visible_columns(self) -> tuple[int, int]:
        plot_width = max(1, self.width() - NAME_WIDTH)
        first = max(1, int(self._viewer._x_offset / BASE_WIDTH) + 1)
        last = min(
            _alignment_length(self._viewer.alignment),
            int((self._viewer._x_offset + plot_width) / BASE_WIDTH) + 2,
        )
        return first, max(first, last)

    def _viewport_x_for_column(self, alignment_column: int) -> float:
        return _alignment_column_x(alignment_column) - self._viewer._x_offset

    def _plot_rect(self) -> QRectF:
        return QRectF(NAME_WIDTH, 0, max(0, self.width() - NAME_WIDTH), self.height())


class AlignmentChromatogramActionProvider:
    """Toolbar actions for the alignment-coordinate chromatogram review viewer."""

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="alignment_chromatogram.align",
                label="Align",
                tooltip="Rerun existing MAFFT alignment for the loaded reads",
                callback=getattr(viewer, "align"),
            ),
            ViewerAction(
                action_id="alignment_chromatogram.toggle_trim_region",
                label="Show Trim",
                tooltip="Toggle trim overlay in the aligned chromatogram view",
                callback=getattr(viewer, "toggle_trim_region"),
            ),
            ViewerAction(
                action_id="alignment_chromatogram.open_quality_report",
                label="Quality Report",
                tooltip="Open quality report for aligned chromatogram reads",
                callback=getattr(viewer, "open_quality_report"),
            ),
            ViewerAction(
                action_id="alignment_chromatogram.build_consensus",
                label="Consensus",
                tooltip="Request consensus workflow for these reads",
                callback=getattr(viewer, "request_consensus"),
            ),
            ViewerAction(
                action_id="alignment_chromatogram.export",
                label="Export",
                tooltip="Request export for alignment/chromatogram review data",
                callback=getattr(viewer, "request_export"),
            ),
            ViewerAction(
                action_id="alignment_chromatogram.run_blast",
                label="BLAST",
                tooltip="Request BLAST workflow for these reads",
                callback=getattr(viewer, "request_blast"),
            ),
        )


def _build_alignment_maps(
    alignment: object,
    reads: tuple[SangerRead, ...],
) -> dict[str, dict[int, int | None]]:
    maps: dict[str, dict[int, int | None]] = {}
    by_name = {read.filename: read for read in reads}
    for record in alignment:
        read = by_name.get(record.id)
        if read is not None:
            maps[record.id] = alignment_to_trace_positions(str(record.seq), read)
    return maps


def _build_alignment_consensus(
    reads: tuple[SangerRead, ...],
    alignment: object,
) -> tuple[str, list[float], str]:
    """Build quality consensus using alignment-column quality coordinates."""

    aligned_quality_reads = tuple(
        _AlignmentQualityRead(_aligned_quality_for_record(read, str(record.seq)))
        for read, record in zip(reads, alignment)
    )
    consensus, confidence = build_quality_consensus(aligned_quality_reads, alignment)
    return consensus, confidence, ""


@dataclass(frozen=True)
class _AlignmentQualityRead:
    quality: tuple[int, ...]


def _aligned_quality_for_record(read: SangerRead, aligned_sequence: str) -> tuple[int, ...]:
    qualities: list[int] = []
    seq_index = 0
    trimmed_quality = tuple(getattr(read, "trimmed_quality", ()) or ())
    raw_quality = tuple(getattr(read, "quality", ()) or ())
    trim_start = getattr(read, "trim_start", 0) or 0
    for base in aligned_sequence:
        if base == "-":
            qualities.append(0)
            continue
        if seq_index < len(trimmed_quality):
            qualities.append(trimmed_quality[seq_index])
        elif trim_start + seq_index < len(raw_quality):
            qualities.append(raw_quality[trim_start + seq_index])
        else:
            qualities.append(0)
        seq_index += 1
    return tuple(qualities)


def _display_traces(read: SangerRead) -> dict[str, tuple[int, ...]]:
    traces = getattr(read, "trimmed_traces", None) or getattr(read, "traces", {})
    return {
        base: tuple(traces.get(base, ()))
        for base in ("A", "C", "G", "T")
    }


def _trace_segments(
    mapping: dict[int, int | None],
    trace: tuple[int, ...],
    *,
    first_col: int = 1,
    last_col: int | None = None,
) -> tuple[tuple[tuple[int, int], ...], ...]:
    """Return alignment-column trace segments, breaking at gap columns."""

    if last_col is None:
        last_col = max(mapping, default=0)
    segments: list[tuple[tuple[int, int], ...]] = []
    points: list[tuple[int, int]] = []
    for column in range(first_col, last_col + 1):
        trace_pos = mapping.get(column)
        if trace_pos is None:
            if len(points) >= 2:
                segments.append(tuple(points))
            points = []
            continue
        pos = int(trace_pos)
        if pos >= len(trace):
            continue
        points.append((column, int(trace[pos])))
    if len(points) >= 2:
        segments.append(tuple(points))
    return tuple(segments)


@dataclass(frozen=True)
class _LocalTracePoint:
    x: float
    signal: int
    alignment_column: int
    trace_position: int


def _local_trace_segments(
    mapping: dict[int, int | None],
    trace: tuple[int, ...],
    *,
    first_col: int = 1,
    last_col: int | None = None,
    window: int = LOCAL_TRACE_WINDOW,
) -> tuple[tuple[_LocalTracePoint, ...], ...]:
    """Return local peak-neighborhood trace segments in alignment coordinates.

    This keeps the Tkinter alignment-column contract, but draws the trace
    samples around each peak inside the fixed-width alignment column instead of
    plotting only the peak sample.  Each alignment column is returned as an
    independent path so gap columns and column boundaries never create synthetic
    trace bridges.
    """

    if last_col is None:
        last_col = max(mapping, default=0)
    segments: list[tuple[_LocalTracePoint, ...]] = []
    for column in range(first_col, last_col + 1):
        trace_pos = mapping.get(column)
        if trace_pos is None:
            continue
        pos = int(trace_pos)
        if pos >= len(trace):
            continue
        local_points = _local_trace_points_for_column(
            column,
            pos,
            trace,
            window=window,
        )
        if len(local_points) >= 2:
            segments.append(local_points)
    return tuple(segments)


def _local_trace_points_for_column(
    alignment_column: int,
    peak_trace_position: int,
    trace: tuple[int, ...],
    *,
    window: int = LOCAL_TRACE_WINDOW,
    sample_step: int = LOCAL_TRACE_SAMPLE_STEP,
) -> tuple[_LocalTracePoint, ...]:
    left = max(0, peak_trace_position - window)
    right = min(len(trace) - 1, peak_trace_position + window)
    if right < left:
        return ()
    span = max(1, right - left)
    column_center = _alignment_column_x(alignment_column)
    half_width = BASE_WIDTH * LOCAL_TRACE_COLUMN_FRACTION / 2
    points: list[_LocalTracePoint] = []
    sampled_positions = set(range(left, right + 1, max(1, sample_step)))
    sampled_positions.add(peak_trace_position)
    sampled_positions.add(right)
    for trace_position in sorted(sampled_positions):
        relative = (trace_position - left) / span
        x = column_center - half_width + relative * (half_width * 2)
        points.append(
            _LocalTracePoint(
                x=x,
                signal=int(trace[trace_position]),
                alignment_column=alignment_column,
                trace_position=trace_position,
            )
        )
    return tuple(points)


def _smoothed_trace_path(
    segment: tuple[_LocalTracePoint, ...],
    *,
    x_offset: int,
    y_base: float,
) -> QPainterPath:
    """Create a Tkinter smooth=True-like quadratic path for local trace points."""

    path = QPainterPath()
    if not segment:
        return path
    points = tuple(
        QPointF(point.x - x_offset, y_base - point.signal * TRACE_SCALE)
        for point in segment
    )
    path.moveTo(points[0])
    if len(points) == 1:
        return path
    if len(points) == 2:
        path.quadTo(points[0], points[1])
        return path
    for index in range(1, len(points) - 1):
        control = points[index]
        next_point = points[index + 1]
        midpoint = QPointF(
            (control.x() + next_point.x()) / 2,
            (control.y() + next_point.y()) / 2,
        )
        path.quadTo(control, midpoint)
    path.quadTo(points[-1], points[-1])
    return path


def _trim_index_for_trace_position(read: SangerRead, trim_trace_position: int) -> int | None:
    positions = tuple(getattr(read, "trimmed_base_positions", ()) or ())
    if trim_trace_position in positions:
        return positions.index(trim_trace_position)
    return None


def _record_index(records: tuple[object, ...], sample_name: str) -> int | None:
    for index, record in enumerate(records):
        if record.id == sample_name:
            return index
    return None


def _alignment_length(alignment: object) -> int:
    length_method = getattr(alignment, "get_alignment_length", None)
    if callable(length_method):
        return int(length_method())
    return max((len(str(record.seq)) for record in alignment), default=0)


def _alignment_column_x(alignment_column: int) -> int:
    return NAME_WIDTH + (alignment_column - 1) * BASE_WIDTH


def _base_color(base: str) -> QColor:
    return _BASE_COLORS.get(base.upper(), QColor("gray"))


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )


def _dash(value: object | None) -> object:
    return "—" if value is None else value
