"""Dockable Quality Report and read visibility filter."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from widgets.quality_metrics import (
    DEFAULT_HQ_THRESHOLD as DEFAULT_STUDIO_HQ_THRESHOLD,
    quality_percent_at_or_above,
)


class QualityReportDock(QDockWidget):
    """Dock panel that owns per-read visibility for chromatogram viewers."""

    DEFAULT_HQ_THRESHOLD = DEFAULT_STUDIO_HQ_THRESHOLD

    def __init__(self, *, visibility_manager: object, parent: QWidget | None = None) -> None:
        super().__init__("Quality Report", parent)
        self.setObjectName("qualityReportDock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._visibility_manager = visibility_manager
        self._reads: tuple[object, ...] = ()
        self._source_key = ""
        self._updating = False
        self._hq_threshold = self.DEFAULT_HQ_THRESHOLD
        self._build_ui()

    @property
    def read_views(self) -> tuple[object, ...]:
        return self._reads

    def selected_read_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                ids.append(getattr(self._reads[row], "read_id"))
        return tuple(ids)

    def set_reads(self, reads: tuple[object, ...], *, source_key: str) -> None:
        self._reads = tuple(reads)
        self._source_key = source_key
        read_ids = tuple(getattr(read_view, "read_id") for read_view in self._reads)
        self._visibility_manager.initialize_source(source_key, read_ids)
        self.refresh()

    def refresh(self) -> None:
        visible_ids = set(
            self._visibility_manager.visible_ids(
                self._source_key,
                tuple(getattr(read_view, "read_id") for read_view in self._reads),
            )
        )
        self._summary.setText(
            f"Reads: {len(self._reads)} • {len(visible_ids)} shown in chromatogram viewers"
        )
        self._table.setRowCount(len(self._reads))
        self._updating = True
        try:
            for row, read_view in enumerate(self._reads):
                read_id = getattr(read_view, "read_id")
                selected = QTableWidgetItem(read_id)
                selected.setFlags(selected.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                selected.setCheckState(
                    Qt.CheckState.Checked
                    if read_id in visible_ids
                    else Qt.CheckState.Unchecked
                )
                self._table.setItem(row, 0, selected)
                values = (
                    str(getattr(read_view, "sequence_length", 0)),
                    f"{getattr(read_view, 'q20_rate', 0.0):.1f}",
                    f"{getattr(read_view, 'q30_rate', 0.0):.1f}",
                    f"{_rate_or_zero(read_view, 40):.1f}",
                    f"{_rate_or_zero(read_view, self._hq_threshold):.1f}",
                    str(getattr(read_view, "trim_length", 0)),
                )
                for column, value in enumerate(values, start=1):
                    self._table.setItem(row, column, QTableWidgetItem(value))
        finally:
            self._updating = False

    def _build_ui(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        self._summary = QLabel()
        self._summary.setToolTip(
            "Changing a check box only shows or hides that read in chromatogram "
            "viewers. It does not delete the read or alter any Dataset."
        )
        layout.addWidget(self._summary)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(QLabel(f"HQ threshold: Q{self._hq_threshold}"))
        controls_layout.addStretch(1)
        layout.addWidget(controls)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Read", "Length", "Q20%", "Q30%", "Q40%", "HQ%", "Trim")
        )
        self._table.horizontalHeaderItem(0).setToolTip(
            "Checked = included in the current chromatogram display only; "
            "unchecked reads remain in the Project and all Dataset revisions."
        )
        self._table.setToolTip(
            "Read visibility is a viewer setting. SangerFlow never removes a read "
            "because of its quality score."
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemChanged.connect(self._item_changed)
        layout.addWidget(self._table, 1)
        self.setWidget(content)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or item.column() != 0:
            return
        row = item.row()
        if row < 0 or row >= len(self._reads):
            return
        self._visibility_manager.set_visible(
            self._source_key,
            getattr(self._reads[row], "read_id"),
            item.checkState() == Qt.CheckState.Checked,
        )


def _rate_or_zero(read_view: object, threshold: float) -> float:
    """Keep existing dock empty-quality rendering while sharing the metric."""

    return quality_percent_at_or_above(read_view, threshold) or 0.0
