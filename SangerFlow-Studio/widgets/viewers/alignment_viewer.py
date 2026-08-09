"""Mesquite-style high-density alignment table viewer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.alignment_dataset import AlignmentDataset
from core.models import SangerRead
from widgets.viewers.alignment_chromatogram_viewer import AlignmentChromatogramViewer
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


class AlignmentViewer(BaseViewer):
    """Display an AlignmentDataset without chromatogram waveforms."""

    def __init__(
        self,
        alignment_dataset: AlignmentDataset,
        *,
        context: object | None = None,
    ) -> None:
        if not isinstance(alignment_dataset, AlignmentDataset):
            raise ValueError("AlignmentViewer requires an AlignmentDataset")
        self._dataset = alignment_dataset
        self._context = context
        self._selected_cell: tuple[str, int] | None = None
        self._selected_column: int | None = None
        self._action_provider = AlignmentViewerActionProvider(context)
        super().__init__(
            viewer_id=f"alignment-viewer-{_safe_identifier(alignment_dataset.alignment_id)}",
            viewer_title=f"Alignment: {alignment_dataset.name}",
            viewer_kind="alignment",
            source_object_id=alignment_dataset.alignment_id,
        )
        self._build_ui()

    @property
    def dataset(self) -> AlignmentDataset:
        return self._dataset

    @property
    def selected_cell(self) -> tuple[str, int] | None:
        return self._selected_cell

    @property
    def selected_column(self) -> int | None:
        return self._selected_column

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return ("alignment.review_chromatograms",)

    def open_dataset(self, dataset: object) -> None:
        if not isinstance(dataset, AlignmentDataset):
            raise ValueError("AlignmentViewer requires an AlignmentDataset")
        self._dataset = dataset
        self.refresh()

    def select_alignment_cell(self, row_index: int, column_index: int) -> tuple[str, int, str] | None:
        if row_index < 0 or row_index >= len(self._dataset.records):
            return None
        record = self._dataset.records[row_index]
        if column_index < 0 or column_index >= self._dataset.length:
            return None
        alignment_column = column_index + 1
        self._selected_cell = (record.record_id, alignment_column)
        self._selected_column = alignment_column
        self._table.setCurrentCell(row_index + 1, column_index + 1)
        self._status.setText(
            f"Read: {record.record_id}    Column: {alignment_column}    Base: {record.aligned_sequence[column_index]}"
        )
        return record.record_id, alignment_column, record.aligned_sequence[column_index]

    def select_column(self, column_index: int) -> None:
        if column_index < 0 or column_index >= self._dataset.length:
            return
        self._selected_column = column_index + 1
        self._selected_cell = None
        self._table.setCurrentCell(0, column_index + 1)
        self._status.setText(f"Column: {column_index + 1}")

    def review_chromatograms(self) -> object | None:
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        if tab_manager is None:
            self.open_related_requested.emit(
                {"action": "REVIEW_CHROMATOGRAMS", "viewer": self, "dataset": self._dataset}
            )
            return None
        reads = _reads_from_alignment_dataset(self._dataset, self._context)
        if not reads:
            self.status_message_changed.emit(
                "No SangerRead references are attached to this AlignmentDataset."
            )
            return None
        alignment = tuple(
            _AlignmentRecord(record.record_id, record.aligned_sequence)
            for record in self._dataset.records
        )
        viewer = AlignmentChromatogramViewer(
            reads,
            alignment=alignment,
            context=context,
            source_object_id=self._dataset.alignment_id,
        )
        return tab_manager.open_viewer(
            viewer,
            resource_key=f"alignment-chromatograms:{self._dataset.alignment_id}",
        )

    def refresh(self) -> None:
        self._summary.setText(
            f"Records: {self._dataset.sequence_count}    Alignment length: {self._dataset.length}"
        )
        self._populate_table()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        layout.addWidget(self._summary)
        self._status = QLabel("Select an alignment cell or column.")
        layout.addWidget(self._status)
        self._table = QTableWidget()
        self._table.setObjectName("alignmentViewerTable")
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.horizontalHeader().sectionClicked.connect(self.select_column)
        self._table.cellClicked.connect(self._cell_clicked)
        self._table.verticalHeader().hide()
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        layout.addWidget(self._table, 1)
        self.refresh()

    def _populate_table(self) -> None:
        self._table.setColumnCount(self._dataset.length + 1)
        self._table.setRowCount(self._dataset.sequence_count + 1)
        self._table.setHorizontalHeaderLabels(
            ("Read",) + tuple(str(index + 1) for index in range(self._dataset.length))
        )
        self._table.setItem(0, 0, QTableWidgetItem("Consensus"))
        for column, base in enumerate(_consensus_sequence(self._dataset), start=1):
            self._table.setItem(0, column, _base_item(base))
        for row, record in enumerate(self._dataset.records, start=1):
            name_item = QTableWidgetItem(record.record_id)
            name_item.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
            self._table.setItem(row, 0, name_item)
            for column, base in enumerate(record.aligned_sequence, start=1):
                self._table.setItem(row, column, _base_item(base))
        self._table.setColumnWidth(0, 180)
        for column in range(1, self._dataset.length + 1):
            self._table.setColumnWidth(column, 22)

    def _cell_clicked(self, row: int, column: int) -> None:
        if column <= 0:
            return
        if row <= 0:
            self.select_column(column - 1)
            return
        self.select_alignment_cell(row - 1, column - 1)


class AlignmentViewerActionProvider:
    def __init__(self, context: object | None) -> None:
        self._context = context

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="alignment.review_chromatograms",
                label="Review Chromatograms",
                tooltip="Open alignment-coordinate chromatogram review when Sanger reads are attached",
                callback=getattr(viewer, "review_chromatograms"),
            ),
        )


@dataclass(frozen=True)
class _AlignmentRecord:
    id: str
    seq: str


def create_alignment_viewer(context: object, dataset: object) -> AlignmentViewer:
    return AlignmentViewer(dataset, context=context)


def _consensus_sequence(dataset: AlignmentDataset) -> str:
    bases: list[str] = []
    for column in range(dataset.length):
        counts = Counter(
            record.aligned_sequence[column]
            for record in dataset.records
            if record.aligned_sequence[column] != "-"
        )
        if not counts:
            bases.append("-")
        else:
            bases.append(counts.most_common(1)[0][0])
    return "".join(bases)


def _base_item(base: str) -> QTableWidgetItem:
    item = QTableWidgetItem(base)
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setFont(QFont("Menlo", 10, QFont.Weight.Bold))
    item.setForeground(_base_color(base))
    if base == "-":
        item.setBackground(QColor("#F3F3F3"))
    return item


def _base_color(base: str) -> QColor:
    colors = {
        "A": QColor("green"),
        "T": QColor("red"),
        "G": QColor("black"),
        "C": QColor("blue"),
        "-": QColor("gray"),
    }
    return colors.get(base.upper(), QColor("#555555"))


def _reads_from_alignment_dataset(
    dataset: AlignmentDataset,
    context: object | None = None,
) -> tuple[SangerRead, ...]:
    metadata_reads = dataset.metadata.get("source_reads") if dataset.metadata else None
    if metadata_reads:
        reads = tuple(read for read in metadata_reads if isinstance(read, SangerRead))
        if reads:
            return reads
    project = getattr(getattr(context, "app_state", None), "project", None)
    if project is not None:
        try:
            parent_dataset = project.get_dataset(dataset.parent_dataset_id)
        except (AttributeError, KeyError):
            parent_dataset = None
        if parent_dataset is not None:
            by_id = {
                getattr(record, "sequence_id", None): getattr(record, "source_reference", None)
                for record in getattr(parent_dataset, "records", ())
            }
            reads = tuple(
                by_id.get(record.source_record_id)
                for record in dataset.records
                if isinstance(by_id.get(record.source_record_id), SangerRead)
            )
            if reads:
                return reads
    reads: list[SangerRead] = []
    for record in dataset.records:
        source = record.metadata.get("source_reference") if record.metadata else None
        if isinstance(source, SangerRead):
            reads.append(source)
    return tuple(reads)


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return ""
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in str(value)
    )
