"""Read-only Dataset viewer for the Studio workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QFormLayout,
    QInputDialog,
    QHeaderView,
    QLineEdit,
    QLabel,
    QMenu,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QToolButton,
    QHBoxLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.sequence_dataset import SequenceDataset
from app.icon_registry import studio_icon
from core.project import RevisionOperation
from export.sequence_export import (
    export_dataset_to_fasta,
    export_dataset_to_nexus,
    export_dataset_to_phylip,
)
from export.popart_export import export_dataset_to_popart_nexus
from export.metadata_export import export_dataset_metadata_to_csv, export_dataset_metadata_to_xlsx
from widgets.popart_export_dialog import PopArtExportDialog
from widgets.metadata_export_dialog import MetadataExportDialog
from workflow.ncbi_blast_xml_import import preview_ncbi_blast_xml
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.chromatogram_viewer import (
    create_chromatogram_viewer_from_dataset,
    has_chromatogram_sources,
    reads_from_dataset,
)
from widgets.viewers.placeholder_viewer import PlaceholderViewer
from widgets.viewers.viewer_actions import ViewerAction
from widgets.metadata_presentation import (
    metadata_summary,
    show_source_filepaths_dialog,
    source_filepaths,
)
from widgets.quality_metrics import format_hq_percent
from widgets.batch_rename_dialog import BatchRenameDialog
from widgets.dataset_creation_dialog import CreateDatasetDialog


_BASE_COLUMN_KEYS = (
    "selected",
    "record_id",
    "length",
    "hq_percent",
    "description_source",
    "sequence_preview",
)
_REQUIRED_COLUMN_KEYS = frozenset({"selected", "record_id"})
_DEFAULT_VISIBLE_COLUMN_KEYS = frozenset({
    "selected",
    "record_id",
    "length",
    "hq_percent",
    "sequence_preview",
})
_COLUMN_LABELS = {
    "selected": "Selected",
    "record_id": "Record ID",
    "length": "Length",
    "hq_percent": "HQ%",
    "description_source": "Description / Source",
    "sequence_preview": "Sequence preview",
}
_COLUMN_WIDTHS = {
    "selected": 76,
    "record_id": 160,
    "length": 72,
    "hq_percent": 88,
    "description_source": 240,
    "sequence_preview": 280,
}
_COMMON_METADATA_FIELDS = ("source_batch", "Species", "Location", "Population", "Country")
_DEFAULT_VISIBLE_METADATA_FIELDS = ("Species", "Location", "Population", "Country")


class _DatasetTableItem(QTableWidgetItem):
    """Display item whose ordering stays typed while Dataset stays immutable."""

    def __init__(self, text: str, sort_value: object) -> None:
        super().__init__(text)
        self._sort_value = sort_value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        other_value = getattr(other, "_sort_value", other.text())
        return _sortable_value(self._sort_value) < _sortable_value(other_value)


@dataclass(frozen=True)
class _DatasetRecordRow:
    record_id: str
    length: int
    hq_percent: str
    description: str
    source: str
    sequence_preview: str
    metadata: dict[str, object]

    def metadata_value(self, field: str) -> str:
        wanted = field.casefold()
        for key, value in self.metadata.items():
            if str(key).casefold() == wanted:
                return "—" if value is None or str(value) == "" else str(value)
        return "—"

    def value(self, key: str) -> str:
        values = {
            "record_id": self.record_id,
            "length": str(self.length),
            "hq_percent": self.hq_percent,
            "description_source": self.description or self.source or "—",
            "sequence_preview": self.sequence_preview,
        }
        return values.get(key, self.metadata_value(key))

    def sort_value(self, key: str) -> object:
        if key == "length":
            return self.length
        if key == "hq_percent":
            return _hq_numeric(self.hq_percent)
        return self.value(key)


class DatasetViewer(BaseViewer):
    """Display SequenceDataset or AlignmentDataset values without modifying them."""

    def __init__(self, dataset: object, context: object | None = None) -> None:
        self._dataset = dataset
        self._context = context
        self._action_provider = DatasetViewerActionProvider(context)
        self._updating_inclusion = False
        self._search_text = ""
        self._available_metadata_fields: tuple[str, ...] = ()
        self._visible_column_keys: set[str] = set(_DEFAULT_VISIBLE_COLUMN_KEYS)
        self._auto_visible_metadata_fields: set[str] = set()
        self._included_record_ids: set[str] = set(
            getattr(record, "sequence_id", getattr(record, "record_id", ""))
            for record in getattr(dataset, "records", ())
        )
        super().__init__(
            viewer_id=f"dataset-viewer-{_dataset_identifier(dataset)}",
            viewer_title=getattr(dataset, "name", _dataset_identifier(dataset)),
            viewer_kind="dataset",
            source_object_id=_dataset_identifier(dataset),
        )
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self._build_ui()

    @property
    def dataset(self) -> object:
        return self._dataset

    @property
    def included_record_ids(self) -> frozenset[str]:
        """Exact IDs currently enabled in this viewer's Include column."""

        return frozenset(self._included_record_ids)

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "dataset.open_chromatogram_viewer",
            "dataset.edit_sequences",
            "dataset.align_sequences",
            "dataset.open_alignment_viewer",
            "dataset.export_fasta",
            "dataset.export_nexus",
            "dataset.export_phylip",
            "dataset.export_popart",
            "dataset.export_metadata_table",
            "dataset.import_sample_metadata",
            "dataset.create_metadata_template",
            "dataset.rename_dataset",
            "dataset.remove_dataset",
            "dataset.create_selection_dataset",
            "dataset.rename_record",
            "dataset.batch_rename_records",
            "dataset.run_blast",
            "dataset.import_blast_xml",
            "dataset.open_quality_report",
            "dataset.open_placeholder_viewer",
        )

    def open_dataset(self, dataset: object) -> None:
        self._dataset = dataset
        self.refresh()

    def request_export_fasta(self) -> str | None:
        return self._request_export(
            title="Export Dataset as FASTA",
            default_suffix=".fasta",
            name_filter="FASTA files (*.fasta *.fas *.fa *.fna);;All files (*)",
            exporter=export_dataset_to_fasta,
        )

    def request_export_nexus(self) -> str | None:
        return self._request_export(
            title="Export Dataset as NEXUS",
            default_suffix=".nex",
            name_filter="NEXUS files (*.nex *.nexus);;All files (*)",
            exporter=lambda dataset, filepath: export_dataset_to_nexus(
                dataset,
                filepath,
                metadata=dataset.metadata,
            ),
        )

    def request_export_phylip(self) -> str | None:
        return self._request_export(
            title="Export Dataset as PHYLIP",
            default_suffix=".phy",
            name_filter="PHYLIP files (*.phy *.phylip);;All files (*)",
            exporter=export_dataset_to_phylip,
        )

    def request_export_popart(self) -> str | None:
        if not isinstance(self._dataset, SequenceDataset):
            QMessageBox.warning(self, "Export for PopART", "PopART export requires a SequenceDataset.")
            return None
        dialog = PopArtExportDialog(self._dataset, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        try:
            trait_field, category_order, missing_values = dialog.export_options()
        except ValueError as error:
            QMessageBox.warning(self, "Export for PopART", str(error))
            return None
        default = f"{_dataset_identifier(self._dataset)}_popart.nex"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export for PopART", default, "NEXUS files (*.nex *.nexus);;All files (*)"
        )
        if not filepath:
            return None
        try:
            export_dataset_to_popart_nexus(
                self._dataset, filepath, trait_field=trait_field,
                category_order=category_order, missing_values=missing_values,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Export for PopART", str(error))
            return None
        self.status_message_changed.emit(f"Exported PopART NEXUS: {filepath}")
        return filepath

    def request_export_metadata_table(self) -> str | None:
        if not isinstance(self._dataset, SequenceDataset):
            return None
        dialog = MetadataExportDialog(self._dataset, self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        format_name, fields = dialog.options()
        suffix = ".csv" if format_name == "csv" else ".xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Metadata Table", f"{_dataset_identifier(self._dataset)}_metadata{suffix}",
            "CSV files (*.csv);;Excel Workbook (*.xlsx);;All files (*)",
        )
        if not filepath:
            return None
        try:
            exporter = export_dataset_metadata_to_csv if format_name == "csv" else export_dataset_metadata_to_xlsx
            exporter(self._dataset, filepath, fields=fields)
        except ValueError as error:
            QMessageBox.warning(self, "Export Metadata Table", str(error))
            return None
        self.status_message_changed.emit(f"Exported metadata table: {filepath}")
        return filepath

    def request_import_blast_xml(self) -> object | None:
        if not isinstance(self._dataset, SequenceDataset):
            return None
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import NCBI BLAST XML", "", "NCBI BLAST XML (*.xml);;All files (*)"
        )
        if not filepath:
            return None
        try:
            preview = preview_ncbi_blast_xml(filepath, self._dataset)
        except ValueError as error:
            QMessageBox.warning(self, "Import NCBI BLAST XML", str(error))
            return None
        preview_text = (
            f"Matched queries: {len(preview.matched_query_ids)}\n"
            f"Unmatched XML queries: {len(preview.unmatched_xml_query_ids)}\n"
            f"Dataset-only records: {len(preview.dataset_only_record_ids)}\n"
            f"Duplicate XML query IDs: {len(preview.duplicate_query_ids)}"
        )
        if preview.unmatched_xml_query_ids or preview.duplicate_query_ids:
            QMessageBox.warning(self, "Import NCBI BLAST XML", preview_text + "\n\nImport was not started.")
            return None
        if QMessageBox.question(self, "Import NCBI BLAST XML", preview_text + "\n\nImport these results?") != QMessageBox.StandardButton.Yes:
            return None
        controller = getattr(self._context, "project_controller", None)
        importer = getattr(controller, "import_ncbi_blast_xml_for_dataset", None)
        if not callable(importer):
            QMessageBox.warning(self, "Import NCBI BLAST XML", "Project XML import is not configured.")
            return None
        try:
            result, _preview = importer(self._dataset, filepath)
        except ValueError as error:
            QMessageBox.warning(self, "Import NCBI BLAST XML", str(error))
            return None
        QMessageBox.information(
            self, "Imported NCBI BLAST XML",
            f"Matched queries: {len(preview.matched_query_ids)}\n"
            f"Dataset-only records: {len(preview.dataset_only_record_ids)}\n"
            f"Hits: {result.hit_count()}",
        )
        return result

    def request_import_sample_metadata(self) -> object | None:
        """Choose an existing metadata table and delegate immutable derivation."""

        if not isinstance(self._dataset, SequenceDataset):
            QMessageBox.warning(
                self,
                "Import Sample Metadata",
                "Sample metadata can only be attached to a SequenceDataset.",
            )
            return None
        filepath, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Import Sample Metadata",
            self._controller_default_directory("metadata_default_directory"),
            "Metadata files (*.csv *.xlsx);;CSV files (*.csv);;Excel workbooks (*.xlsx);;All files (*)",
        )
        if not filepath:
            return None
        controller = getattr(self._context, "project_controller", None)
        import_method = getattr(controller, "import_sample_metadata_for_dataset", None)
        if not callable(import_method):
            QMessageBox.warning(
                self,
                "Import Sample Metadata",
                "Project metadata import is not configured.",
            )
            return None
        try:
            derived = import_method(self._dataset, filepath)
        except Exception as error:
            QMessageBox.warning(self, "Import Sample Metadata", str(error))
            return None
        self.status_message_changed.emit(
            f"Sample metadata imported into derived Dataset: {derived.dataset_id}"
        )
        return derived

    def request_create_metadata_template(self) -> str | None:
        if not isinstance(self._dataset, SequenceDataset):
            QMessageBox.warning(self, "Create Excel Template", "Metadata templates require a SequenceDataset.")
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_metadata_excel_template", None)
        if not callable(method):
            QMessageBox.warning(self, "Create Excel Template", "Project metadata templates are not configured.")
            return None
        default_name = f"{_dataset_identifier(self._dataset)}_metadata_template.xlsx"
        directory = self._controller_default_directory("metadata_default_directory")
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Create Excel Metadata Template",
            str(Path(directory) / default_name) if directory else default_name,
            "Excel Workbook (*.xlsx);;All files (*)",
        )
        if not filepath:
            return None
        try:
            output = method(self._dataset, filepath)
        except Exception as error:
            QMessageBox.warning(self, "Create Excel Template", str(error))
            return None
        self.status_message_changed.emit(f"Metadata template created: {output}")
        return output

    def request_rename_dataset(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "rename_dataset", None)
        if not callable(method):
            return None
        current_name = getattr(self._dataset, "name", _dataset_identifier(self._dataset))
        display_name, accepted = QInputDialog.getText(
            self,
            "Rename Dataset",
            "Dataset display name:",
            text=current_name,
        )
        if not accepted:
            return None
        display_name = display_name.strip()
        if not display_name:
            QMessageBox.warning(self, "Rename Dataset", "Dataset display name cannot be empty.")
            return None
        try:
            updated = method(_dataset_identifier(self._dataset), display_name)
        except Exception as error:
            QMessageBox.warning(self, "Rename Dataset", str(error))
            return None
        self.status_message_changed.emit(f"Dataset renamed: {display_name}")
        return updated

    def request_remove_dataset(self) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "remove_dataset", None)
        if not callable(method):
            return None
        name = getattr(self._dataset, "name", _dataset_identifier(self._dataset))
        response = QMessageBox.question(
            self,
            "Remove Dataset",
            f"Remove '{name}' from this Project? Dataset contents will not be modified.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if response != QMessageBox.StandardButton.Yes:
            return None
        try:
            updated = method(_dataset_identifier(self._dataset))
        except Exception as error:
            QMessageBox.warning(self, "Remove Dataset", str(error))
            return None
        self.status_message_changed.emit(f"Dataset removed: {name}")
        return updated

    def _request_export(
        self,
        *,
        title: str,
        default_suffix: str,
        name_filter: str,
        exporter: object,
    ) -> str | None:
        if not isinstance(self._dataset, SequenceDataset):
            QMessageBox.warning(self, title, "This export requires a SequenceDataset.")
            return None
        default_name = f"{_dataset_identifier(self._dataset)}{default_suffix}"
        directory = self._controller_default_directory("export_default_directory")
        filepath, _selected_filter = QFileDialog.getSaveFileName(
            self,
            title,
            str(Path(directory) / default_name) if directory else default_name,
            name_filter,
        )
        if not filepath:
            return None
        filepath = _ensure_suffix(filepath, default_suffix)
        try:
            exporter(self._dataset, filepath)  # type: ignore[misc]
        except Exception as error:
            QMessageBox.warning(self, title, str(error))
            return None
        self.status_message_changed.emit(f"Exported: {filepath}")
        return filepath

    def _controller_default_directory(self, method_name: str) -> str:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, method_name, None)
        if not callable(method):
            return ""
        try:
            return str(method() or "")
        except Exception:
            return ""

    def refresh(self) -> None:
        self._name_value.setText(getattr(self._dataset, "name", "-"))
        self._type_value.setText(_dataset_type_label(self._dataset))
        self._count_value.setText(str(getattr(self._dataset, "sequence_count", 0)))
        metadata = getattr(self._dataset, "metadata", {})
        self._metadata_value.setText(metadata_summary(metadata))
        paths = source_filepaths(metadata)
        self._source_files_button.setVisible(bool(paths))
        self._source_files_button.setText(f"Show… ({len(paths)} files)")
        self._available_metadata_fields = _metadata_fields(self._dataset)
        available_by_folded = {
            field.casefold(): field for field in self._available_metadata_fields
        }
        for preferred_field in _DEFAULT_VISIBLE_METADATA_FIELDS:
            canonical_field = preferred_field.casefold()
            available_field = available_by_folded.get(canonical_field)
            if available_field is not None and canonical_field not in self._auto_visible_metadata_fields:
                self._visible_column_keys.add(available_field)
                self._auto_visible_metadata_fields.add(canonical_field)
        self._visible_column_keys.intersection_update(
            set(_BASE_COLUMN_KEYS) | set(self._available_metadata_fields)
        )
        self._visible_column_keys.update(_REQUIRED_COLUMN_KEYS)
        self._metadata_button.setEnabled(isinstance(self._dataset, SequenceDataset))
        self._rebuild_columns_menu()
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
        self._metadata_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._metadata_value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._source_files_button = QPushButton("Show…")
        self._source_files_button.setIcon(studio_icon("folder"))
        self._source_files_button.clicked.connect(self._show_source_files)
        self._source_files_button.setVisible(False)
        metadata_row = QWidget(summary)
        metadata_layout = QHBoxLayout(metadata_row)
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        metadata_layout.addWidget(self._metadata_value, 1)
        metadata_layout.addWidget(self._source_files_button)
        metadata_row.setMinimumWidth(0)
        metadata_row.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        form.addRow("Dataset name", self._name_value)
        form.addRow("Dataset type", self._type_value)
        form.addRow("Record count", self._count_value)
        form.addRow("Metadata", metadata_row)
        summary.setMinimumWidth(0)
        summary.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(summary)

        table_controls = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search this dataset…")
        self._columns_button = QToolButton()
        self._columns_button.setText("Columns…")
        self._columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._columns_menu = QMenu(self._columns_button)
        self._columns_button.setMenu(self._columns_menu)
        self._metadata_button = QToolButton()
        self._metadata_button.setText("Metadata…")
        self._metadata_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._metadata_menu = QMenu(self._metadata_button)
        self._metadata_menu.addAction("Import Sample Metadata…", self.request_import_sample_metadata)
        self._metadata_menu.addAction("Create Excel Template…", self.request_create_metadata_template)
        self._metadata_button.setMenu(self._metadata_menu)
        self._metadata_button.setEnabled(isinstance(self._dataset, SequenceDataset))
        table_controls.addWidget(self._search, 1)
        table_controls.addWidget(self._metadata_button)
        table_controls.addWidget(self._columns_button)
        layout.addLayout(table_controls)

        self._records_table = QTableWidget()
        self._records_table.setColumnCount(len(_BASE_COLUMN_KEYS))
        self._records_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._records_table.setWordWrap(False)
        self._records_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._records_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._records_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._records_table.setSortingEnabled(True)
        self._records_table.itemChanged.connect(self._record_include_changed)
        self._search.textChanged.connect(self._search_changed)
        layout.addWidget(self._records_table, 1)
        controls = QHBoxLayout()
        for label, icon_name, callback in (
            ("Select All", "select", self.select_all_records),
            ("Deselect All", "clear", self.deselect_all_records),
            ("Invert Selection", "select", self.invert_record_selection),
            ("Create Dataset from Selection", "create_dataset", self.create_dataset_from_selection),
            ("Rename", "rename", self.request_rename_selected_record),
            ("Batch Rename", "rename", self.request_batch_rename),
        ):
            button = QPushButton(label)
            button.setIcon(studio_icon(icon_name))
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.refresh()

    def _show_source_files(self) -> None:
        show_source_filepaths_dialog(self, source_filepaths(getattr(self._dataset, "metadata", {})))

    def _populate_records(self) -> None:
        rows = tuple(row for row in _record_rows(self._dataset) if self._matches_search(row))
        column_keys = self._column_keys()
        self._updating_inclusion = True
        sorting_enabled = self._records_table.isSortingEnabled()
        try:
            self._records_table.setSortingEnabled(False)
            self._records_table.setColumnCount(len(column_keys))
            self._records_table.setHorizontalHeaderLabels(
                tuple(_column_label(key) for key in column_keys)
            )
            for column_index, key in enumerate(column_keys):
                header_item = self._records_table.horizontalHeaderItem(column_index)
                if header_item is not None and key == "selected":
                    header_item.setToolTip("Select records for actions in this Dataset view.")
                self._records_table.setColumnHidden(column_index, key not in self._visible_column_keys)
                self._records_table.setColumnWidth(column_index, _column_width(key))
            self._records_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                record_id = row.record_id
                include = _DatasetTableItem("", record_id)
                include.setFlags(include.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                include.setCheckState(
                    Qt.CheckState.Checked if record_id in self._included_record_ids else Qt.CheckState.Unchecked
                )
                self._records_table.setItem(row_index, 0, include)
                for column_index, key in enumerate(column_keys[1:], start=1):
                    value = row.value(key)
                    self._records_table.setItem(
                        row_index,
                        column_index,
                        _DatasetTableItem(str(value), row.sort_value(key)),
                    )
        finally:
            self._updating_inclusion = False
            self._records_table.setSortingEnabled(sorting_enabled)

    def _column_keys(self) -> tuple[str, ...]:
        return _BASE_COLUMN_KEYS + self._available_metadata_fields

    def _rebuild_columns_menu(self) -> None:
        self._columns_menu.clear()
        for key in self._column_keys():
            action = self._columns_menu.addAction(_column_label(key))
            action.setCheckable(True)
            action.setChecked(key in self._visible_column_keys)
            action.setEnabled(key not in _REQUIRED_COLUMN_KEYS)
            action.toggled.connect(lambda checked, column_key=key: self._set_column_visible(column_key, checked))

    def _set_column_visible(self, key: str, visible: bool) -> None:
        if key in _REQUIRED_COLUMN_KEYS:
            return
        if visible:
            self._visible_column_keys.add(key)
        else:
            self._visible_column_keys.discard(key)
        self._populate_records()

    def _search_changed(self, value: str) -> None:
        self._search_text = value.casefold().strip()
        self._populate_records()

    def _matches_search(self, row: "_DatasetRecordRow") -> bool:
        if not self._search_text:
            return True
        return any(
            self._search_text in value.casefold()
            for value in (
                row.record_id,
                row.description,
                row.source,
                *(str(value) for value in row.metadata.values()),
            )
        )

    def _record_include_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_inclusion or item.column() != 0 or item.row() < 0:
            return
        id_item = self._records_table.item(item.row(), 1)
        if id_item is None:
            return
        if item.checkState() == Qt.CheckState.Checked:
            self._included_record_ids.add(id_item.text())
        else:
            self._included_record_ids.discard(id_item.text())

    def select_all_records(self) -> None:
        self._included_record_ids = {row.record_id for row in _record_rows(self._dataset)}
        self._populate_records()

    def deselect_all_records(self) -> None:
        self._included_record_ids.clear()
        self._populate_records()

    def invert_record_selection(self) -> None:
        all_ids = {row.record_id for row in _record_rows(self._dataset)}
        self._included_record_ids = all_ids - self._included_record_ids
        self._populate_records()

    def create_dataset_from_selection(
        self,
        *,
        renamed_record_ids: dict[str, str] | None = None,
    ) -> object | None:
        if not isinstance(self._dataset, SequenceDataset):
            self.status_message_changed.emit("Record selection is available for SequenceDataset only.")
            return None
        selected_ids = tuple(
            record.sequence_id
            for record in self._dataset.records
            if record.sequence_id in self._included_record_ids
        )
        if not selected_ids:
            QMessageBox.warning(self, "Create Dataset from Selection", "Select at least one record.")
            return None
        dialog = CreateDatasetDialog(
            self,
            suggested_id=f"{_dataset_identifier(self._dataset)}_selection",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_dataset_from_record_selection", None)
        if not callable(method):
            QMessageBox.warning(self, "Create Dataset from Selection", "Project dataset creation is not configured.")
            return None
        try:
            derived = method(
                self._dataset,
                selected_ids,
                name=dialog.dataset_name,
                dataset_id=dialog.dataset_id,
                renamed_record_ids=renamed_record_ids,
            )
        except Exception as error:
            QMessageBox.warning(self, "Create Dataset from Selection", str(error))
            return None
        self.status_message_changed.emit(f"Derived Dataset created: {derived.dataset_id}")
        return derived

    def request_rename_selected_record(self) -> object | None:
        selected_rows = self._records_table.selectionModel().selectedRows()
        if len(selected_rows) != 1:
            QMessageBox.warning(self, "Rename Record", "Select exactly one record row.")
            return None
        record_id_item = self._records_table.item(selected_rows[0].row(), 1)
        if record_id_item is None:
            return None
        previous = record_id_item.text()
        replacement, accepted = QInputDialog.getText(self, "Rename Record", "Record ID:", text=previous)
        if not accepted:
            return None
        replacement = replacement.strip()
        if not replacement:
            QMessageBox.warning(self, "Rename Record", "Record ID cannot be empty.")
            return None
        return self._create_rename_revision(
            {previous: replacement},
            operation=RevisionOperation.RECORD_RENAME,
        )

    def request_batch_rename(self) -> object | None:
        selected_ids = tuple(
            record.sequence_id
            for record in getattr(self._dataset, "records", ())
            if record.sequence_id in self._included_record_ids
        )
        if not selected_ids:
            QMessageBox.warning(self, "Batch Rename", "Select at least one record to rename.")
            return None
        dialog = BatchRenameDialog(
            selected_ids,
            self,
            existing_record_ids=tuple(record.sequence_id for record in self._dataset.records),
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        return self._create_rename_revision(
            dialog.rename_by_id,
            operation=RevisionOperation.BATCH_RENAME,
        )

    def _create_rename_revision(
        self,
        rename_by_id: dict[str, str],
        *,
        operation: RevisionOperation,
    ) -> object | None:
        if not isinstance(self._dataset, SequenceDataset):
            QMessageBox.warning(self, "Rename Record", "Record rename requires a SequenceDataset.")
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_dataset_revision_with_record_renames", None)
        if not callable(method):
            QMessageBox.warning(self, "Rename Record", "Project revision registration is not configured.")
            return None
        try:
            derived = method(self._dataset, rename_by_id, operation=operation)
        except Exception as error:
            QMessageBox.warning(self, "Rename Record", str(error))
            return None
        self.status_message_changed.emit(f"Dataset revision created: {derived.dataset_id}")
        return derived


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
                toolbar=True,
                menu_group="Dataset",
                priority=100,
            ),
            ViewerAction(
                action_id="dataset.edit_sequences",
                label="Open Sequence Editor",
                tooltip="Open this SequenceDataset in Sequence Editor — Unaligned",
                callback=lambda: self._open_sequence_editor(viewer),
                enabled=has_tab_manager and _is_sequence_dataset(dataset),
                toolbar=True,
                menu_group="Dataset",
                priority=90,
            ),
            ViewerAction(
                action_id="dataset.align_sequences",
                label="Align…",
                tooltip="Create a new AlignmentDataset with MAFFT",
                callback=lambda: self._align_sequences(viewer),
                enabled=has_tab_manager
                and _is_sequence_dataset(dataset)
                and callable(
                    getattr(getattr(self._context, "project_controller", None), "align_sequence_dataset_from_editor", None)
                ),
                toolbar=True,
                menu_group="Align",
                priority=85,
            ),
            ViewerAction(
                action_id="dataset.open_alignment_viewer",
                label="Open Sequence Editor — Aligned",
                tooltip="Open this AlignmentDataset in Sequence Editor — Aligned",
                callback=lambda: self._open_alignment(viewer),
                enabled=has_tab_manager and _is_alignment_dataset(dataset),
                toolbar=True,
                menu_group="Align",
                priority=90,
            ),
            ViewerAction(
                action_id="dataset.export_fasta",
                label="Export FASTA",
                tooltip="Export the full SequenceDataset as FASTA",
                callback=getattr(viewer, "request_export_fasta"),
                enabled=_is_sequence_dataset(dataset),
                toolbar_group="Export",
                menu_group="Export",
            ),
            ViewerAction(
                action_id="dataset.export_nexus",
                label="Export NEXUS",
                tooltip="Export the full equal-length SequenceDataset as NEXUS",
                callback=getattr(viewer, "request_export_nexus"),
                enabled=_is_sequence_dataset(dataset),
                toolbar_group="Export",
                menu_group="Export",
            ),
            ViewerAction(
                action_id="dataset.export_phylip",
                label="Export PHYLIP",
                tooltip="Export the full equal-length SequenceDataset as PHYLIP",
                callback=getattr(viewer, "request_export_phylip"),
                enabled=_is_sequence_dataset(dataset),
                toolbar_group="Export",
                menu_group="Export",
            ),
            ViewerAction(
                action_id="dataset.export_popart",
                label="Export for PopART...",
                tooltip="Export an equal-length DNA matrix with categorical metadata traits",
                callback=getattr(viewer, "request_export_popart"),
                enabled=_is_sequence_dataset(dataset),
                menu_group="Export",
            ),
            ViewerAction(
                action_id="dataset.export_metadata_table",
                label="Export Metadata Table...",
                tooltip="Export Sample_ID, sequence length, source type, and selected metadata fields",
                callback=getattr(viewer, "request_export_metadata_table"),
                enabled=_is_sequence_dataset(dataset),
                menu_group="Export",
            ),
            ViewerAction(
                action_id="dataset.import_sample_metadata",
                label="Import Sample Metadata...",
                tooltip="Create a derived SequenceDataset by matching Sample_ID from CSV or XLSX",
                callback=getattr(viewer, "request_import_sample_metadata"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Metadata",
            ),
            ViewerAction(
                action_id="dataset.create_metadata_template",
                label="Create Excel Template...",
                tooltip="Create an XLSX Sample_ID template in Dataset record order",
                callback=getattr(viewer, "request_create_metadata_template"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Metadata",
            ),
            ViewerAction(
                action_id="dataset.rename_dataset",
                label="Rename Dataset...",
                tooltip="Change only this Project entry's display name",
                callback=getattr(viewer, "request_rename_dataset"),
                enabled=dataset is not None
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Dataset",
                context_scope="dataset",
            ),
            ViewerAction(
                action_id="dataset.remove_dataset",
                label="Remove Dataset...",
                tooltip="Remove a leaf Dataset from this Project",
                callback=getattr(viewer, "request_remove_dataset"),
                enabled=dataset is not None
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Dataset",
                context_scope="dataset",
            ),
            ViewerAction(
                action_id="dataset.create_selection_dataset",
                label="Create Dataset from Selection",
                tooltip="Create an immutable derived SequenceDataset from included records",
                callback=getattr(viewer, "create_dataset_from_selection"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Dataset",
            ),
            ViewerAction(
                action_id="dataset.rename_record",
                label="Rename Record",
                tooltip="Create a derived Dataset with one renamed record",
                callback=getattr(viewer, "request_rename_selected_record"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Edit",
                context_scope="record",
            ),
            ViewerAction(
                action_id="dataset.batch_rename_records",
                label="Batch Rename Records",
                tooltip="Create a derived Dataset after find/replace/prefix/suffix renaming",
                callback=getattr(viewer, "request_batch_rename"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Edit",
                context_scope="record",
            ),
            ViewerAction(
                action_id="dataset.run_blast",
                label="BLAST…",
                tooltip="Choose NCBI Online or the official NCBI Website workflow",
                callback=lambda: self._run_blast(viewer),
                enabled=has_tab_manager and dataset is not None,
                toolbar=True,
                menu_group="Identify",
                priority=80,
            ),
            ViewerAction(
                action_id="dataset.import_blast_xml",
                label="Import NCBI BLAST XML...",
                tooltip="Import an exact-query matched result downloaded from NCBI Web BLAST",
                callback=getattr(viewer, "request_import_blast_xml"),
                enabled=_is_sequence_dataset(dataset)
                and getattr(self._context, "project_controller", None) is not None,
                menu_group="Identify",
            ),
            ViewerAction(
                action_id="dataset.open_quality_report",
                label="Quality Report",
                tooltip="Open the quality report for AB1-backed records",
                callback=lambda: self._open_quality_report(viewer),
                enabled=has_tab_manager
                and dataset is not None
                and has_chromatogram_sources(dataset),
                toolbar_group="More",
                menu_group="Dataset",
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

    def _open_sequence_editor(self, viewer: object) -> None:
        context = self._context
        tab_manager = getattr(context, "tab_manager", None)
        dataset = getattr(viewer, "dataset", None)
        if tab_manager is None or not isinstance(dataset, SequenceDataset):
            return
        from widgets.viewers.sequence_editor import SequenceEditor

        editor = SequenceEditor(dataset, context=context)
        tab_manager.open_viewer(editor, resource_key=f"sequence-editor:{dataset.dataset_id}")

    def _align_sequences(self, viewer: object) -> object | None:
        """Use the existing Sequence Editor alignment Controller workflow.

        Dataset Viewer is intentionally only an additional entry point.  The
        settings dialog, MAFFT call, and immutable AlignmentDataset creation
        remain owned by ``ProjectController``.
        """

        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "align_sequence_dataset_from_editor", None)
        if not callable(method):
            return None
        try:
            return method(viewer)
        except ValueError as error:
            QMessageBox.warning(viewer, "Align Sequences", str(error))
            return None

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

    def _run_blast(self, viewer: object) -> None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "run_blast_for_dataset_interactive", None)
        if not callable(method):
            method = getattr(controller, "run_blast_for_dataset", None)
        dataset = getattr(viewer, "dataset", None)
        included_record_ids = getattr(viewer, "included_record_ids", None)
        if callable(method) and dataset is not None:
            try:
                method(dataset, included_record_ids=included_record_ids, parent_widget=viewer)
            except TypeError:
                try:
                    method(dataset, parent_widget=viewer)
                except TypeError:
                    method(dataset)

    def _run_bold(self, viewer: object) -> None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "run_bold_for_dataset_interactive", None)
        if not callable(method):
            method = getattr(controller, "run_bold_for_dataset", None)
        dataset = getattr(viewer, "dataset", None)
        if callable(method) and dataset is not None:
            try:
                method(dataset, parent_widget=viewer)
            except TypeError:
                method(dataset)


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


def _is_sequence_dataset(dataset: object) -> bool:
    return isinstance(dataset, SequenceDataset)


def _record_rows(dataset: object) -> tuple[_DatasetRecordRow, ...]:
    if hasattr(dataset, "records"):
        return tuple(_record_row(record) for record in getattr(dataset, "records", ()))
    return ()


def _record_row(record: object) -> _DatasetRecordRow:
    sequence = getattr(record, "sequence", None)
    if sequence is None:
        sequence = getattr(record, "aligned_sequence", "")
    record_id = getattr(record, "sequence_id", None) or getattr(record, "record_id", "-")
    description = getattr(record, "description", None)
    if description is None:
        description = getattr(record, "source_record_id", "-")
    source = getattr(record, "source_reference", None)
    quality_summary = format_hq_percent(source)
    record_metadata = dict(getattr(record, "metadata", {}) or {})
    return _DatasetRecordRow(
        record_id=str(record_id),
        length=len(sequence),
        hq_percent=quality_summary,
        description=str(description or ""),
        source=str(record_metadata.get("source_filename") or ""),
        sequence_preview=_preview(sequence),
        metadata=record_metadata,
    )


def _metadata_fields(dataset: object) -> tuple[str, ...]:
    """Discover record metadata using Project Records' case-insensitive rule."""

    by_folded: dict[str, str] = {}
    for row in _record_rows(dataset):
        for key in row.metadata:
            by_folded.setdefault(str(key).casefold(), str(key))
    ordered = [
        by_folded.pop(field.casefold())
        for field in _COMMON_METADATA_FIELDS
        if field.casefold() in by_folded
    ]
    return tuple(ordered + sorted(by_folded.values(), key=str.casefold))


def _column_label(key: str) -> str:
    return _COLUMN_LABELS.get(key, " ".join(part.capitalize() for part in key.replace("_", " ").split()))


def _column_width(key: str) -> int:
    return _COLUMN_WIDTHS.get(key, 150)


def _sortable_value(value: object) -> tuple[int, object]:
    """Return a stable natural-sort key without changing Dataset record order."""

    if isinstance(value, (int, float)):
        return (0, value)
    text = str(value)
    if text == "—":
        return (2, "")
    parts = tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", text)
    )
    return (1, parts)


def _hq_numeric(value: str) -> float:
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return -1.0


def _preview(sequence: str, limit: int = 80) -> str:
    if len(sequence) <= limit:
        return sequence
    return f"{sequence[:limit]}..."


def _ensure_suffix(filepath: str, suffix: str) -> str:
    path = Path(filepath)
    if path.suffix:
        return str(path)
    return str(path.with_suffix(suffix))
