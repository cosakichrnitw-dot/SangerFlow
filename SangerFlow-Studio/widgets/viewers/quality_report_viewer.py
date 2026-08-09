"""Tkinter QualityPanel-derived read quality report for Studio."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.chromatogram_viewer import ChromatogramReadView


class QualityReportViewer(BaseViewer):
    """Read-only quality table with Tkinter-style HQ threshold selection."""

    def __init__(
        self,
        reads: Iterable[ChromatogramReadView],
        *,
        context: object | None = None,
        source_object_id: str | None = None,
    ) -> None:
        self._reads = tuple(reads)
        self._context = context
        super().__init__(
            viewer_id=f"quality-report-{_safe_identifier(source_object_id) if source_object_id else id(self)}",
            viewer_title="Quality Report",
            viewer_kind="quality-report",
            source_object_id=source_object_id,
        )
        self._build_ui()

    @property
    def read_views(self) -> tuple[ChromatogramReadView, ...]:
        return self._reads

    def selected_read_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                ids.append(self._reads[row].read_id)
        return tuple(ids)

    def select_by_hq_threshold(self, threshold: float | None = None) -> None:
        threshold_value = self._threshold.value() if threshold is None else float(threshold)
        for row, read_view in enumerate(self._reads):
            item = self._table.item(row, 0)
            if item is not None:
                item.setCheckState(
                    Qt.CheckState.Checked
                    if read_view.q20_rate >= threshold_value
                    else Qt.CheckState.Unchecked
                )

    def refresh(self) -> None:
        self._summary.setText(f"Reads: {len(self._reads)}")
        self._table.setRowCount(len(self._reads))
        for row, read_view in enumerate(self._reads):
            selected = QTableWidgetItem("")
            selected.setCheckState(Qt.CheckState.Checked)
            self._table.setItem(row, 0, selected)
            values = (
                read_view.read_id,
                str(read_view.sequence_length),
                f"{read_view.average_quality:.1f}",
                f"{read_view.q20_rate:.1f}",
                f"{read_view.q30_rate:.1f}",
                str(read_view.trim_length),
            )
            for column, value in enumerate(values, start=1):
                self._table.setItem(row, column, QTableWidgetItem(value))

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        layout.addWidget(self._summary)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(QLabel("HQ threshold (%)"))
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 100.0)
        self._threshold.setValue(70.0)
        controls_layout.addWidget(self._threshold)
        select_button = QPushButton("HQ > threshold Select")
        select_button.clicked.connect(self.select_by_hq_threshold)
        controls_layout.addWidget(select_button)
        controls_layout.addStretch(1)
        layout.addWidget(controls)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Selected", "Sample", "Length", "Mean Q", "Q20", "Q30", "Trim length")
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self._table, 1)
        self.refresh()


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )
