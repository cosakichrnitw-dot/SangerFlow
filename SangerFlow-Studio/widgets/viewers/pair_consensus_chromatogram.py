"""Pair-alignment-coordinate chromatogram evidence panel for consensus review.

This is display glue only.  Its X axis is the existing PairAlignment column
stored in each ``ReviewEvidence``; raw trace positions are consumed exactly as
provided by that evidence.  In particular, the reverse read is not reversed
again in this widget.
"""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from core.models import SangerRead
from widgets.font_utils import fixed_width_font
from widgets.viewers.alignment_trace_geometry import (
    alignment_column_x,
    peak_to_peak_trace_segments,
    raw_trace_path,
)


PAIR_NAME_WIDTH = 118
PAIR_COLUMN_WIDTH = 18
PAIR_ROW_HEIGHT = 94
PAIR_RULER_HEIGHT = 30
PAIR_TRACE_GAIN = 0.022
PAIR_BASE_Y_OFFSET = -22
PAIR_TRACE_BOTTOM_OFFSET = -12

_TRACE_COLORS = {
    "A": QColor("green"),
    "T": QColor("red"),
    "G": QColor("black"),
    "C": QColor("blue"),
}


class PairConsensusChromatogramPanel(QWidget):
    """Forward/Reverse evidence in one common PairAlignment-column X axis."""

    column_selected = Signal(int)  # zero-based PairAlignment/consensus column

    def __init__(
        self,
        forward_read: SangerRead,
        reverse_read: SangerRead,
        columns: Iterable[object],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._forward_read = forward_read
        self._reverse_read = reverse_read
        self._columns = tuple(columns)
        # A sample can legitimately have no selected PairAlignment column while
        # a multiple-consensus review switches its evidence source.  Keep that
        # state explicit instead of manufacturing a selection at column zero.
        self._selected_column: int | None = None
        self._forward_mapping: dict[int, int | None] = {}
        self._reverse_mapping: dict[int, int | None] = {}
        self._rebuild_mappings()
        self._canvas = _PairConsensusChromatogramCanvas(self)
        self._scroll = QScrollArea()
        self._scroll.setWidget(self._canvas)
        self._scroll.setWidgetResizable(False)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QScrollArea.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._scroll)
        self.setMinimumHeight(PAIR_RULER_HEIGHT + PAIR_ROW_HEIGHT * 2 + 28)

    @property
    def selected_column(self) -> int | None:
        return self._selected_column

    @property
    def forward_mapping(self) -> dict[int, int | None]:
        return dict(self._forward_mapping)

    @property
    def reverse_mapping(self) -> dict[int, int | None]:
        return dict(self._reverse_mapping)

    def select_column(
        self,
        column: int | None,
        *,
        center: bool = True,
        emit: bool = False,
    ) -> bool:
        """Select a valid PairAlignment column without coercing an empty selection."""

        if column is None:
            return False
        try:
            column_index = int(column)
        except (TypeError, ValueError):
            return False
        if not 0 <= column_index < len(self._columns):
            return False
        self._selected_column = column_index
        if center:
            x = alignment_column_x(
                self._selected_column + 1,
                left_margin=PAIR_NAME_WIDTH,
                column_width=PAIR_COLUMN_WIDTH,
            )
            viewport_width = max(1, self._scroll.viewport().width())
            self._scroll.horizontalScrollBar().setValue(max(0, int(x - viewport_width / 2)))
        self._canvas.update()
        if emit:
            self.column_selected.emit(self._selected_column)
        return True

    def clear_selection(self) -> None:
        """Show no evidence selection for a MAFFT-only gap column."""

        self._selected_column = None
        self._canvas.update()

    def set_evidence_source(
        self,
        forward_read: SangerRead,
        reverse_read: SangerRead,
        columns: Iterable[object],
    ) -> None:
        """Switch samples without deriving or altering any scientific state."""

        self._forward_read = forward_read
        self._reverse_read = reverse_read
        self._columns = tuple(columns)
        self._selected_column = None
        self._rebuild_mappings()
        self._canvas.setFixedSize(self.content_width(), self.content_height())
        self._canvas.update()

    def _rebuild_mappings(self) -> None:
        self._forward_mapping = {
            index + 1: getattr(column.review_evidence, "forward_raw_trace_position", None)
            for index, column in enumerate(self._columns)
        }
        self._reverse_mapping = {
            index + 1: getattr(column.review_evidence, "reverse_raw_trace_position", None)
            for index, column in enumerate(self._columns)
        }

    def select_from_canvas(self, column: int) -> None:
        self.select_column(column, emit=True)

    def content_width(self) -> int:
        return PAIR_NAME_WIDTH + max(1, len(self._columns)) * PAIR_COLUMN_WIDTH + 30

    def content_height(self) -> int:
        return PAIR_RULER_HEIGHT + PAIR_ROW_HEIGHT * 2 + 12

    def evidence_for(self, column: int | None) -> object | None:
        """Return evidence only for a concrete in-range PairAlignment column."""

        if column is None:
            return None
        try:
            column_index = int(column)
        except (TypeError, ValueError):
            return None
        if not 0 <= column_index < len(self._columns):
            return None
        return getattr(self._columns[column_index], "review_evidence", None)


class _PairConsensusChromatogramCanvas(QWidget):
    def __init__(self, panel: PairConsensusChromatogramPanel) -> None:
        super().__init__()
        self._panel = panel
        self.setFixedSize(panel.content_width(), panel.content_height())
        self.setMouseTracking(True)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        position = event.position()
        if position.x() < PAIR_NAME_WIDTH or position.y() < PAIR_RULER_HEIGHT:
            return super().mousePressEvent(event)
        column = int((position.x() - PAIR_NAME_WIDTH) // PAIR_COLUMN_WIDTH)
        if self._panel.select_column(column, emit=True):
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QPainter(self)
        try:
            painter.fillRect(event.rect(), QColor("white"))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            self._draw_ruler(painter)
            self._draw_selected_column(painter)
            self._draw_read(painter, self._panel._forward_read, "Forward", "forward", 0, self._panel.forward_mapping)
            self._draw_read(painter, self._panel._reverse_read, "Reverse", "reverse", 1, self._panel.reverse_mapping)
        finally:
            # Never leave a native QPainter active if a UI-side display value
            # is absent or another Python exception is raised during painting.
            if painter.isActive():
                painter.end()

    def _draw_ruler(self, painter: QPainter) -> None:
        painter.save()
        painter.setFont(fixed_width_font(8))
        painter.setPen(QPen(QColor("#555555")))
        painter.drawText(5, 17, "Pair column")
        for column in range(1, len(self._panel._columns) + 1):
            x = alignment_column_x(column, left_margin=PAIR_NAME_WIDTH, column_width=PAIR_COLUMN_WIDTH)
            major = column == 1 or column % 10 == 0
            painter.drawLine(int(x), 20 if major else 23, int(x), PAIR_RULER_HEIGHT - 2)
            if major:
                painter.drawText(QRectF(x - 14, 2, 30, 15), Qt.AlignmentFlag.AlignCenter, str(column))
        painter.restore()

    def _draw_selected_column(self, painter: QPainter) -> None:
        if self._panel.selected_column is None:
            return
        x = alignment_column_x(
            self._panel.selected_column + 1,
            left_margin=PAIR_NAME_WIDTH,
            column_width=PAIR_COLUMN_WIDTH,
        ) - PAIR_COLUMN_WIDTH / 2
        painter.save()
        painter.setPen(QPen(QColor("#7B3FBF"), 1.5))
        painter.setBrush(QColor(180, 120, 230, 42))
        painter.drawRect(QRectF(x, PAIR_RULER_HEIGHT, PAIR_COLUMN_WIDTH, PAIR_ROW_HEIGHT * 2))
        painter.restore()

    def _draw_read(
        self,
        painter: QPainter,
        read: SangerRead,
        label: str,
        side: str,
        row_index: int,
        mapping: dict[int, int | None],
    ) -> None:
        top = PAIR_RULER_HEIGHT + row_index * PAIR_ROW_HEIGHT
        y_base = top + PAIR_ROW_HEIGHT + PAIR_TRACE_BOTTOM_OFFSET
        evidence = self._panel.evidence_for(self._panel.selected_column)
        quality_name = f"{side}_quality"
        quality = getattr(evidence, quality_name, None) if evidence is not None else None
        painter.save()
        try:
            painter.setFont(fixed_width_font(8, QFont.Weight.Bold))
            painter.setPen(QPen(QColor("#222222")))
            painter.drawText(5, top + 20, label)
            painter.setFont(fixed_width_font(7))
            painter.drawText(5, top + 36, _elide_filename(read.filename))
            painter.drawText(5, top + 52, f"Q: {_format_quality(quality)}")
            painter.setPen(QPen(QColor("#DDDDDD")))
            painter.drawLine(0, top + PAIR_ROW_HEIGHT - 1, self.width(), top + PAIR_ROW_HEIGHT - 1)
            painter.setClipRect(QRectF(PAIR_NAME_WIDTH, top, self.width() - PAIR_NAME_WIDTH, PAIR_ROW_HEIGHT))
            self._draw_quality_overlay(painter, mapping, side, top, y_base)
            self._draw_bases(painter, mapping, side, top)
            traces = getattr(read, "traces", {}) or {}
            for base, color in _TRACE_COLORS.items():
                trace = tuple(traces.get(base, ()))
                painter.setPen(QPen(color, 1.2))
                for segment in peak_to_peak_trace_segments(
                    mapping,
                    trace,
                    left_margin=PAIR_NAME_WIDTH,
                    column_width=PAIR_COLUMN_WIDTH,
                ):
                    if len(segment) >= 2:
                        painter.drawPath(raw_trace_path(segment, x_offset=0, y_base=y_base, gain=PAIR_TRACE_GAIN))
        finally:
            painter.restore()

    def _draw_quality_overlay(
        self,
        painter: QPainter,
        mapping: dict[int, int | None],
        side: str,
        top: int,
        y_base: int,
    ) -> None:
        """Reuse Main ChromatogramViewer's Q40-capped light-blue quality language.

        Evidence quality and raw trace mapping are both supplied by the existing
        PairAlignment/ReviewEvidence models.  A missing side or gap remains
        visually empty rather than being inferred in the UI.
        """

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#EEF9FF"))
        maximum_height = max(1, (y_base - top - 20) * 0.55)
        for column, trace_position in mapping.items():
            if trace_position is None:
                continue
            evidence = self._panel.evidence_for(column - 1)
            quality = getattr(evidence, f"{side}_quality", None) if evidence is not None else None
            if quality is None:
                continue
            height = min(max(float(quality), 0.0), 40.0) / 40.0 * maximum_height
            x = alignment_column_x(column, left_margin=PAIR_NAME_WIDTH, column_width=PAIR_COLUMN_WIDTH)
            painter.drawRect(
                QRectF(
                    x - PAIR_COLUMN_WIDTH / 2,
                    y_base - height,
                    PAIR_COLUMN_WIDTH,
                    height,
                )
            )
        painter.restore()

    def _draw_bases(
        self,
        painter: QPainter,
        mapping: dict[int, int | None],
        side: str,
        top: int,
    ) -> None:
        painter.setFont(fixed_width_font(8, QFont.Weight.Bold))
        for column, trace_position in mapping.items():
            x = alignment_column_x(column, left_margin=PAIR_NAME_WIDTH, column_width=PAIR_COLUMN_WIDTH)
            evidence = self._panel.evidence_for(column - 1)
            base = "-" if trace_position is None else getattr(evidence, f"{side}_base", "?")
            painter.setPen(QPen(_TRACE_COLORS.get(base.upper(), QColor("#666666"))))
            painter.drawText(
                QRectF(x - PAIR_COLUMN_WIDTH / 2, top + 3, PAIR_COLUMN_WIDTH, 14),
                Qt.AlignmentFlag.AlignCenter,
                base,
            )


def _format_quality(value: object | None) -> str:
    return "—" if value is None else f"{float(value):.0f}"


def _elide_filename(filename: str, maximum: int = 16) -> str:
    return filename if len(filename) <= maximum else f"{filename[: maximum - 1]}…"
