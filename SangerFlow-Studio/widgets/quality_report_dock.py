"""Dockable Quality Report and read visibility filter."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
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


class QualityReportDock(QDockWidget):
    """Dock panel that owns per-read visibility for chromatogram viewers."""

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

    def select_by_hq_threshold(self, threshold: float | None = None) -> None:
        threshold_value = self._threshold.value() if threshold is None else float(threshold)
        selected = tuple(
            getattr(read_view, "read_id")
            for read_view in self._reads
            if getattr(read_view, "q20_rate", 0.0) >= threshold_value
        )
        self._visibility_manager.set_visible_ids(self._source_key, selected)
        self.refresh()

    def refresh(self) -> None:
        visible_ids = set(
            self._visibility_manager.visible_ids(
                self._source_key,
                tuple(getattr(read_view, "read_id") for read_view in self._reads),
            )
        )
        self._summary.setText(f"Reads: {len(self._reads)}")
        self._table.setRowCount(len(self._reads))
        self._updating = True
        try:
            for row, read_view in enumerate(self._reads):
                read_id = getattr(read_view, "read_id")
                selected = QTableWidgetItem("")
                selected.setFlags(selected.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                selected.setCheckState(
                    Qt.CheckState.Checked
                    if read_id in visible_ids
                    else Qt.CheckState.Unchecked
                )
                self._table.setItem(row, 0, selected)
                values = (
                    read_id,
                    str(getattr(read_view, "sequence_length", 0)),
                    f"{getattr(read_view, 'average_quality', 0.0):.1f}",
                    f"{getattr(read_view, 'q20_rate', 0.0):.1f}",
                    f"{getattr(read_view, 'q30_rate', 0.0):.1f}",
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
        layout.addWidget(self._summary)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(QLabel("Q20 ≥"))
        self._threshold = QDoubleSpinBox()
        self._threshold.setRange(0.0, 100.0)
        self._threshold.setValue(70.0)
        controls_layout.addWidget(self._threshold)
        select_button = QPushButton("Filter")
        select_button.clicked.connect(self.select_by_hq_threshold)
        controls_layout.addWidget(select_button)
        controls_layout.addStretch(1)
        layout.addWidget(controls)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ("Read", "Name", "Length", "MeanQ", "Q20", "Q30", "Trim")
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
