"""Read-only Dataset viewer for the Studio workspace."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtWidgets import (
    QFormLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.chromatogram_viewer import (
    create_chromatogram_viewer_from_dataset,
    has_chromatogram_sources,
    reads_from_dataset,
)
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.viewer_actions import ViewerAction


class DatasetViewer(BaseViewer):
    """Display SequenceDataset or AlignmentDataset values without modifying them."""

    def __init__(self, dataset: object, context: object | None = None) -> None:
        self._dataset = dataset
        self._context = context
        self._action_provider = DatasetViewerActionProvider(context)
        super().__init__(
            viewer_id=f"dataset-viewer-{_dataset_identifier(dataset)}",
            viewer_title=getattr(dataset, "name", _dataset_identifier(dataset)),
            viewer_kind="dataset",
            source_object_id=_dataset_identifier(dataset),
        )
        self._build_ui()

    @property
    def dataset(self) -> object:
        return self._dataset

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "dataset.open_chromatogram_viewer",
            "dataset.open_alignment_viewer",
            "dataset.open_quality_report",
            "dataset.open_placeholder_viewer",
        )

    def open_dataset(self, dataset: object) -> None:
        self._dataset = dataset
        self.refresh()

    def refresh(self) -> None:
        self._name_value.setText(getattr(self._dataset, "name", "-"))
        self._type_value.setText(_dataset_type_label(self._dataset))
        self._count_value.setText(str(getattr(self._dataset, "sequence_count", 0)))
        self._metadata_value.setText(_format_metadata(getattr(self._dataset, "metadata", {})))
        self._populate_records()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        summary = QWidget()
        form = QFormLayout(summary)
        self._name_value = QLabel()
        self._type_value = QLabel()
        self._count_value = QLabel()
        self._metadata_value = QLabel()
        self._metadata_value.setWordWrap(True)
        form.addRow("Dataset name", self._name_value)
        form.addRow("Dataset type", self._type_value)
        form.addRow("Record count", self._count_value)
        form.addRow("Metadata", self._metadata_value)
        layout.addWidget(summary)

        self._records_table = QTableWidget()
        self._records_table.setColumnCount(4)
        self._records_table.setHorizontalHeaderLabels(
            ("Record ID", "Length", "Description / Source", "Sequence preview")
        )
        self._records_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._records_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._records_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        layout.addWidget(self._records_table, 1)
        self.refresh()

    def _populate_records(self) -> None:
        rows = _record_rows(self._dataset)
        self._records_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self._records_table.setItem(
                    row_index,
                    column_index,
                    QTableWidgetItem(str(value)),
                )


class DatasetViewerActionProvider:
    """Open actions exposed when DatasetViewer is the active tab."""

    def __init__(self, context: object | None) -> None:
        self._context = context

    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        dataset = getattr(viewer, "dataset", None)
        has_tab_manager = (
            self._context is not None
            and getattr(self._context, "tab_manager", None) is not None
        )
        return (
            ViewerAction(
                action_id="dataset.open_chromatogram_viewer",
                label="Open Chromatograms",
                tooltip="Open chromatogram traces for AB1-backed records",
                callback=lambda: self._open_chromatogram(viewer),
                enabled=has_tab_manager
                and dataset is not None
                and has_chromatogram_sources(dataset),
            ),
            ViewerAction(
                action_id="dataset.open_alignment_viewer",
                label="Open Alignment",
                tooltip="Open this AlignmentDataset in the Mesquite-style Alignment Viewer",
                callback=lambda: self._open_alignment(viewer),
                enabled=has_tab_manager and _is_alignment_dataset(dataset),
            ),
            ViewerAction(
                action_id="dataset.open_placeholder_viewer",
                label="Open Viewer",
                tooltip="Open a placeholder viewer for this dataset",
                callback=lambda: self._open_placeholder(viewer),
                enabled=has_tab_manager,
            ),
            ViewerAction(
                action_id="dataset.open_quality_report",
                label="Quality Report",
                tooltip="Open a Tkinter-style quality report for AB1-backed records",
                callback=lambda: self._open_quality_report(viewer),
                enabled=has_tab_manager
                and dataset is not None
                and has_chromatogram_sources(dataset),
            ),
        )

    def _open_chromatogram(self, viewer: object) -> None:
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        if tab_manager is None:
            return
        dataset = getattr(viewer, "dataset", None)
        if dataset is None or not has_chromatogram_sources(dataset):
            return
        chromatogram_viewer = create_chromatogram_viewer_from_dataset(context, dataset)
        tab_manager.open_viewer(
            chromatogram_viewer,
            resource_key=f"chromatogram:{_dataset_identifier(dataset)}",
        )

    def _open_alignment(self, viewer: object) -> None:
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        if tab_manager is None:
            return
        dataset = getattr(viewer, "dataset", None)
        if not _is_alignment_dataset(dataset):
            return
        from widgets.viewers.alignment_viewer import AlignmentViewer

        alignment_viewer = AlignmentViewer(dataset, context=context)
        tab_manager.open_viewer(
            alignment_viewer,
            resource_key=f"alignment:{_dataset_identifier(dataset)}",
        )

    def _open_quality_report(self, viewer: object) -> None:
        context = self._context
        dataset = getattr(viewer, "dataset", None)
        reads = reads_from_dataset(dataset)
        if not reads:
            return
        from widgets.viewers.chromatogram_viewer import _read_view

        read_views = tuple(_read_view(read) for read in reads)
        source_key = _dataset_identifier(dataset)
        dock_manager = getattr(context, "dock_manager", None)
        if dock_manager is not None:
            dock = dock_manager.show_quality_report(read_views, source_key=source_key)
            if dock is not None:
                return
        return

    def _open_placeholder(self, viewer: object) -> None:
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        if tab_manager is None:
            return
        dataset = getattr(viewer, "dataset", None)
        if dataset is None:
            return
        placeholder = PlaceholderViewer(dataset=dataset, viewer_kind="placeholder")
        tab_manager.open_viewer(
            placeholder,
            resource_key=f"placeholder:{_dataset_identifier(dataset)}",
        )


def create_dataset_viewer(context: object, dataset: object) -> DatasetViewer:
    return DatasetViewer(dataset, context)


def _dataset_identifier(dataset: object) -> str:
    return (
        getattr(dataset, "dataset_id", None)
        or getattr(dataset, "alignment_id", None)
        or str(id(dataset))
    )


def _dataset_type_label(dataset: object) -> str:
    if hasattr(dataset, "source_type"):
        return getattr(dataset.source_type, "value", str(dataset.source_type))
    if hasattr(dataset, "alignment_id"):
        return "AlignmentDataset"
    return type(dataset).__name__


def _is_alignment_dataset(dataset: object) -> bool:
    return hasattr(dataset, "alignment_id") and hasattr(dataset, "records") and hasattr(dataset, "length")


def _record_rows(dataset: object) -> tuple[tuple[str, int, str, str], ...]:
    if hasattr(dataset, "records"):
        return tuple(_record_row(record) for record in getattr(dataset, "records", ()))
    return ()


def _record_row(record: object) -> tuple[str, int, str, str]:
    sequence = getattr(record, "sequence", None)
    if sequence is None:
        sequence = getattr(record, "aligned_sequence", "")
    record_id = getattr(record, "sequence_id", None) or getattr(record, "record_id", "-")
    description = getattr(record, "description", None)
    if description is None:
        description = getattr(record, "source_record_id", "-")
    return (
        str(record_id),
        len(sequence),
        str(description or "-"),
        _preview(sequence),
    )


def _preview(sequence: str, limit: int = 80) -> str:
    if len(sequence) <= limit:
        return sequence
    return f"{sequence[:limit]}..."


def _format_metadata(metadata: object) -> str:
    if not metadata:
        return "-"
    if isinstance(metadata, Mapping):
        return "; ".join(f"{key}={value}" for key, value in metadata.items())
    return str(metadata)
