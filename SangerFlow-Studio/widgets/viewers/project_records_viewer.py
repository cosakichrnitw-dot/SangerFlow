"""Project-wide current-record search, metadata filtering, and selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import csv
from pathlib import Path

from openpyxl import Workbook
from app.icon_registry import studio_icon

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QFileDialog,
)

from core.lineage import RecordRef
from core.project import Project, RevisionState
from core.sequence_dataset import SequenceDataset
from widgets.quality_metrics import format_hq_percent
from widgets.viewers.base_viewer import BaseViewer
from workflow.cross_dataset_builder import CrossDatasetSelectionValidation, validate_record_refs


_BASE_COLUMNS = ("Select", "Record ID", "Dataset", "Length", "HQ%", "Source Type", "Description")
_COMMON_METADATA_FIELDS = ("source_batch", "Species", "Location", "Population", "Country")
_CATEGORICAL_METADATA_FIELDS = frozenset({
    "source_batch",
    "blast_identification_status",
})
_NUMERIC_METADATA_FIELDS = frozenset({
    "blast_identity",
    "blast_query_coverage",
    "blast_evalue",
})
_STRING_OPERATORS = ("contains", "does not contain", "is", "is not")
_CATEGORICAL_OPERATORS = ("is", "is not")
_NUMERIC_OPERATORS = ("=", ">", ">=", "<", "<=")


def _metadata_matches(value: str, operator: str, expected: str) -> bool:
    """Compare one displayed metadata value without coercing scientific data."""

    if value == "—":
        return False
    actual = value.casefold()
    if operator == "is":
        return actual == expected
    if operator == "is not":
        return actual != expected
    if operator == "contains":
        return expected in actual
    if operator == "does not contain":
        return expected not in actual
    if operator in {"=", ">=", "<=", ">", "<"}:
        try:
            actual_number = float(value)
            expected_number = float(expected)
        except ValueError:
            return False
        return {
            "=": actual_number == expected_number,
            ">=": actual_number >= expected_number,
            "<=": actual_number <= expected_number,
            ">": actual_number > expected_number,
            "<": actual_number < expected_number,
        }[operator]
    return False


def _as_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_matches(actual: float, operator: str, expected: float) -> bool:
    return {
        "=": actual == expected,
        ">=": actual >= expected,
        "<=": actual <= expected,
        ">": actual > expected,
        "<": actual < expected,
    }.get(operator, False)


def _metadata_operators(field: str, values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = field.casefold()
    if normalized in _CATEGORICAL_METADATA_FIELDS:
        return _CATEGORICAL_OPERATORS
    if normalized in _NUMERIC_METADATA_FIELDS or (values and all(_as_float(value) is not None for value in values)):
        return _NUMERIC_OPERATORS
    return _STRING_OPERATORS


@dataclass(frozen=True)
class ProjectRecordRow:
    """One Project-local record; selection identity remains immutable RecordRef."""

    record_ref: RecordRef
    record_id: str
    dataset_name: str
    dataset_id: str
    length: int
    hq_percent: str
    source_type: str
    description: str
    metadata: Mapping[str, object]
    revision_state: RevisionState

    def metadata_value(self, field: str) -> str:
        wanted = field.casefold()
        for key, value in self.metadata.items():
            if str(key).casefold() == wanted:
                return "—" if value is None or str(value) == "" else str(value)
        return "—"


class _MetadataValueCombo(QComboBox):
    """Editable metadata value picker with a small QLineEdit compatibility shim."""

    def __init__(self) -> None:
        super().__init__()
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)

    def setText(self, value: str) -> None:
        self.setEditText(value)

    def text(self) -> str:
        return self.currentText()


class ProjectRecordsModel(QAbstractTableModel):
    """Table model with stable selection outside filter/sort state."""

    selection_toggled = Signal(object, bool)

    def __init__(self) -> None:
        super().__init__()
        self._all_rows: tuple[ProjectRecordRow, ...] = ()
        self._visible_rows: tuple[ProjectRecordRow, ...] = ()
        self._selected_refs: set[RecordRef] = set()
        self._search = ""
        self._dataset_id: str | None = None
        self._source_type: str | None = None
        self._include_previous = False
        self._include_archived = False
        self._metadata_conditions: tuple[tuple[str, str, str], ...] = ()
        self._metadata_columns: tuple[str, ...] = ()
        self._length_value: int | None = None
        self._length_operator = ">="
        self._hq_value: float | None = None
        self._hq_operator = ">="

    @property
    def columns(self) -> tuple[str, ...]:
        return _BASE_COLUMNS + tuple(_metadata_label(field) for field in self._metadata_columns)

    @property
    def column_keys(self) -> tuple[str, ...]:
        """Canonical keys backing visible table headers."""

        return _BASE_COLUMNS + self._metadata_columns

    @property
    def all_rows(self) -> tuple[ProjectRecordRow, ...]:
        return self._all_rows

    @property
    def visible_rows(self) -> tuple[ProjectRecordRow, ...]:
        return self._visible_rows

    @property
    def metadata_columns(self) -> tuple[str, ...]:
        return self._metadata_columns

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible_rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation is Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.columns[section] if 0 <= section < len(self.columns) else None
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid() or not 0 <= index.row() < len(self._visible_rows):
            return None
        row = self._visible_rows[index.row()]
        if role == Qt.ItemDataRole.UserRole:
            return row.record_ref
        if role == Qt.ItemDataRole.ToolTipRole and index.column() == 2:
            return row.dataset_id
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            return Qt.CheckState.Checked if row.record_ref in self._selected_refs else Qt.CheckState.Unchecked
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        values = ("", row.record_id, row.dataset_name, str(row.length), row.hq_percent, row.source_type, row.description)
        if index.column() < len(values):
            return values[index.column()]
        return row.metadata_value(self._metadata_columns[index.column() - len(_BASE_COLUMNS)])

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(self, index: QModelIndex, value: object, role: int = Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802
        if not index.isValid() or index.column() != 0 or role != Qt.ItemDataRole.CheckStateRole:
            return False
        record_ref = self._visible_rows[index.row()].record_ref
        checked = value == Qt.CheckState.Checked or value == int(Qt.CheckState.Checked.value)
        if checked:
            self._selected_refs.add(record_ref)
        else:
            self._selected_refs.discard(record_ref)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        self.selection_toggled.emit(record_ref, checked)
        return True

    def set_rows(self, rows: tuple[ProjectRecordRow, ...], selected_refs: set[RecordRef]) -> None:
        self.beginResetModel()
        self._all_rows = rows
        self._selected_refs = set(selected_refs)
        self._apply_filters()
        self.endResetModel()

    def set_metadata_columns(self, fields: tuple[str, ...]) -> None:
        normalized = tuple(dict.fromkeys(field for field in fields if field))
        if normalized == self._metadata_columns:
            return
        self.beginResetModel()
        self._metadata_columns = normalized
        self._apply_filters()
        self.endResetModel()

    def set_filters(
        self,
        *,
        search: str,
        dataset_id: str | None,
        source_type: str | None,
        include_previous: bool,
        include_archived: bool,
        metadata_conditions: tuple[tuple[str, ...], ...] = (),
        minimum_length: str = "",
        minimum_hq: str = "",
        length_operator: str = ">=",
        hq_operator: str = ">=",
    ) -> None:
        self.beginResetModel()
        self._search = search.casefold().strip()
        self._dataset_id = dataset_id
        self._source_type = source_type
        self._include_previous = include_previous
        self._include_archived = include_archived
        normalized_conditions = []
        for condition in metadata_conditions:
            if len(condition) == 2:  # compatibility with the original UI API
                field, value = condition
                operator = "is"
            elif len(condition) == 3:
                field, operator, value = condition
            else:
                continue
            if field and str(value).strip():
                normalized_conditions.append(
                    (str(field), str(operator), str(value).casefold().strip())
                )
        self._metadata_conditions = tuple(normalized_conditions)
        self._length_value = _optional_nonnegative_int(minimum_length)
        self._length_operator = length_operator if length_operator in _NUMERIC_OPERATORS else ">="
        self._hq_value = _optional_nonnegative_float(minimum_hq)
        self._hq_operator = hq_operator if hq_operator in _NUMERIC_OPERATORS else ">="
        self._apply_filters()
        self.endResetModel()

    def refresh_selection(self) -> None:
        if not self._visible_rows:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._visible_rows) - 1, 0)
        self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.CheckStateRole])

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:  # noqa: N802
        if not 0 <= column < len(self.columns):
            return
        reverse = order is Qt.SortOrder.DescendingOrder
        self.layoutAboutToBeChanged.emit()
        self._visible_rows = tuple(sorted(self._visible_rows, key=lambda row: _sort_value(row, self.column_keys[column]), reverse=reverse))
        self.layoutChanged.emit()

    def _apply_filters(self) -> None:
        self._visible_rows = tuple(row for row in self._all_rows if self._matches(row))

    def _matches(self, row: ProjectRecordRow) -> bool:
        if row.revision_state is RevisionState.SUPERSEDED and not self._include_previous:
            return False
        if row.revision_state is RevisionState.ARCHIVED and not self._include_archived:
            return False
        if self._dataset_id is not None and row.dataset_id != self._dataset_id:
            return False
        if self._source_type is not None and row.source_type != self._source_type:
            return False
        if self._length_value is not None and not _numeric_matches(
            float(row.length), self._length_operator, float(self._length_value)
        ):
            return False
        if self._hq_value is not None and not _numeric_matches(
            _hq_numeric(row.hq_percent), self._hq_operator, self._hq_value
        ):
            return False
        if not _matches_search(row, self._search):
            return False
        return all(
            _metadata_matches(row.metadata_value(field), operator, value)
            for field, operator, value in self._metadata_conditions
        )


class _CreateDatasetDialog(QDialog):
    def __init__(self, parent: QWidget, *, suggested_id: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Dataset from Selected Records")
        self._name = QLineEdit()
        self._dataset_id = QLineEdit(suggested_id)
        form = QFormLayout()
        form.addRow("Dataset name", self._name)
        form.addRow("Dataset ID", self._dataset_id)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def dataset_name(self) -> str:
        return self._name.text().strip()

    @property
    def dataset_id(self) -> str:
        return self._dataset_id.text().strip()

    def accept(self) -> None:  # noqa: D401
        if not self.dataset_name or not self.dataset_id:
            QMessageBox.warning(self, "Create Dataset", "Dataset name and Dataset ID are required.")
            return
        super().accept()


class _ResolveRecordIdCollisionsDialog(QDialog):
    """Require an explicit, batch-based name decision for derived output."""

    def __init__(
        self,
        parent: QWidget,
        *,
        collisions: Mapping[str, tuple[RecordRef, ...]],
        source_batches: Mapping[RecordRef, str],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Duplicate Record Names")
        self._output_record_ids: dict[RecordRef, str] = {}
        details: list[str] = []
        unresolved: list[str] = []
        for record_id, refs in collisions.items():
            labels = []
            for record_ref in refs:
                batch = str(source_batches.get(record_ref, "")).strip()
                labels.append(f"- {batch or record_ref.dataset_id}")
                if not batch:
                    unresolved.append(record_id)
                    continue
                self._output_record_ids[record_ref] = f"{batch}_{record_id}"
            details.append(f"{record_id}:\n" + "\n".join(labels))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Duplicate record names were found in the selected source records."))
        layout.addWidget(QLabel("\n\n".join(details)))
        self._explanation = QLabel(
            "Only the output Dataset records will be renamed; source records remain unchanged."
        )
        self._explanation.setWordWrap(True)
        layout.addWidget(self._explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self._prefix_button = buttons.addButton(
            "Prefix duplicate names with Source Batch",
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        if unresolved:
            self._prefix_button.setEnabled(False)
            self._explanation.setText(
                "A Source Batch is required to resolve these collisions: " + ", ".join(sorted(set(unresolved)))
            )
        self._prefix_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def output_record_ids(self) -> Mapping[RecordRef, str]:
        return dict(self._output_record_ids)


class _CreateDatasetScopeDialog(QDialog):
    """Require an explicit scope when a saved selection is partly filtered out."""

    def __init__(self, parent: QWidget, *, visible_count: int, total_count: int) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Derived Dataset")
        self._visible = QRadioButton(f"Visible selected records only ({visible_count})")
        self._all = QRadioButton(f"All selected records ({total_count})")
        self._visible.setChecked(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"{visible_count} records are currently visible and selected."))
        layout.addWidget(QLabel(f"{total_count} records are selected in total."))
        layout.addWidget(self._visible)
        layout.addWidget(self._all)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        create_button = buttons.addButton("Create", QDialogButtonBox.ButtonRole.AcceptRole)
        create_button.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def use_visible_selection(self) -> bool:
        return self._visible.isChecked()


class ProjectRecordsViewer(BaseViewer):
    """Project tab for current-record browsing and cross-dataset derivation."""

    def __init__(self, project: Project, context: object) -> None:
        if not isinstance(project, Project):
            raise ValueError("project must be a Project")
        self._project = project
        self._context = context
        self._selection_order: list[RecordRef] = []
        self._selected_refs: set[RecordRef] = set()
        self._model = ProjectRecordsModel()
        self._project_state_connected = False
        self._available_metadata_fields: tuple[str, ...] = ()
        super().__init__(
            viewer_id=f"project-records-{project.project_id}",
            viewer_title="Project Records",
            viewer_kind="project-records",
            source_object_id=project.project_id,
        )
        self._build_ui()
        state = getattr(context, "app_state", None)
        signal = getattr(state, "project_changed", None)
        if signal is not None:
            signal.connect(self._project_changed)
            self._project_state_connected = True
        self._refresh_project(project)

    def close_viewer(self) -> bool:
        self._disconnect_project_state()
        return super().close_viewer()

    def _disconnect_project_state(self, *_args: object) -> None:
        state = getattr(self._context, "app_state", None)
        signal = getattr(state, "project_changed", None)
        if self._project_state_connected and signal is not None:
            signal.disconnect(self._project_changed)
        self._project_state_connected = False

    @property
    def selected_record_refs(self) -> tuple[RecordRef, ...]:
        return tuple(record_ref for record_ref in self._selection_order if record_ref in self._selected_refs)

    @property
    def table_model(self) -> ProjectRecordsModel:
        return self._model

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return ("project_records.create_dataset",)

    def refresh(self) -> None:
        state = getattr(self._context, "app_state", None)
        project = getattr(state, "current_project", None)
        self._refresh_project(project if isinstance(project, Project) else None)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search Records...")
        self._dataset_filter = QComboBox()
        self._source_type_filter = QComboBox()
        self._dataset_filter.addItem("Dataset: All", None)
        self._source_type_filter.addItem("Source Type: All", None)
        self._include_previous = QCheckBox("Include previous revisions")
        self._include_archived = QCheckBox("Include archived datasets")
        self._columns_button = QToolButton()
        self._columns_button.setText("Columns…")
        self._columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._columns_menu = QMenu(self._columns_button)
        self._columns_button.setMenu(self._columns_menu)
        filters.addWidget(self._search, 1)
        filters.addWidget(self._dataset_filter)
        filters.addWidget(self._source_type_filter)
        filters.addWidget(self._include_previous)
        filters.addWidget(self._include_archived)
        filters.addWidget(self._columns_button)
        layout.addLayout(filters)

        qc_filters = QHBoxLayout()
        self._minimum_length = QLineEdit()
        self._minimum_length.setPlaceholderText("Min length")
        self._minimum_length.setMaximumWidth(110)
        self._length_operator = QComboBox()
        self._length_operator.addItems(_NUMERIC_OPERATORS)
        self._length_operator.setCurrentText(">=")
        self._minimum_hq = QLineEdit()
        self._minimum_hq.setPlaceholderText("Min HQ%")
        self._minimum_hq.setMaximumWidth(110)
        self._hq_operator = QComboBox()
        self._hq_operator.addItems(_NUMERIC_OPERATORS)
        self._hq_operator.setCurrentText(">=")
        qc_filters.addWidget(QLabel("Length"))
        qc_filters.addWidget(self._length_operator)
        qc_filters.addWidget(self._minimum_length)
        qc_filters.addWidget(QLabel("HQ%"))
        qc_filters.addWidget(self._hq_operator)
        qc_filters.addWidget(self._minimum_hq)
        qc_filters.addStretch(1)
        layout.addLayout(qc_filters)

        advanced = QHBoxLayout()
        self._metadata_field_one = QComboBox()
        self._metadata_operator_one = QComboBox()
        self._metadata_value_one = _MetadataValueCombo()
        self._metadata_value_one.setPlaceholderText("Value")
        self._metadata_field_two = QComboBox()
        self._metadata_operator_two = QComboBox()
        self._metadata_value_two = _MetadataValueCombo()
        self._metadata_value_two.setPlaceholderText("Value")
        advanced.addWidget(QLabel("Metadata (AND):"))
        advanced.addWidget(self._metadata_field_one)
        advanced.addWidget(self._metadata_operator_one)
        advanced.addWidget(self._metadata_value_one)
        advanced.addWidget(self._metadata_field_two)
        advanced.addWidget(self._metadata_operator_two)
        advanced.addWidget(self._metadata_value_two)
        layout.addLayout(advanced)

        selection_controls = QHBoxLayout()
        select_visible = QPushButton("Select Visible")
        select_visible.setIcon(studio_icon("select"))
        clear_selection = QPushButton("Clear Selection")
        clear_selection.setIcon(studio_icon("clear"))
        invert_visible = QPushButton("Invert Visible Selection")
        invert_visible.setIcon(studio_icon("select"))
        select_visible.clicked.connect(self.select_visible)
        clear_selection.clicked.connect(self.clear_selection)
        invert_visible.clicked.connect(self.invert_visible_selection)
        selection_controls.addWidget(select_visible)
        selection_controls.addWidget(clear_selection)
        selection_controls.addWidget(invert_visible)
        selection_controls.addStretch(1)
        layout.addLayout(selection_controls)

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setColumnWidth(0, 56)
        self._table.setColumnWidth(1, 150)
        self._table.setColumnWidth(2, 180)
        self._table.setColumnWidth(3, 68)
        self._table.setColumnWidth(4, 70)
        self._table.setColumnWidth(5, 125)
        self._table.setColumnWidth(6, 260)
        layout.addWidget(self._table, 1)

        footer = QHBoxLayout()
        self._selection_summary = QLabel()
        self._create_button = QPushButton("Create Dataset from Selection...")
        self._create_button.setIcon(studio_icon("create_dataset"))
        self._export_button = QPushButton("Export Visible Metadata...")
        self._export_button.setIcon(studio_icon("export"))
        self._create_button.clicked.connect(self.request_create_dataset)
        self._export_button.clicked.connect(self.request_export_visible_metadata)
        footer.addWidget(self._selection_summary)
        footer.addStretch(1)
        footer.addWidget(self._create_button)
        footer.addWidget(self._export_button)
        layout.addLayout(footer)

        self._search.textChanged.connect(self._update_filters)
        # Scope changes also determine which concrete values are offered in
        # the metadata value pickers.  Keep both controls in sync instead of
        # leaving candidates from a previously selected Dataset visible.
        self._dataset_filter.currentIndexChanged.connect(self._metadata_field_changed)
        self._source_type_filter.currentIndexChanged.connect(self._metadata_field_changed)
        self._include_previous.toggled.connect(self._metadata_field_changed)
        self._include_archived.toggled.connect(self._metadata_field_changed)
        self._metadata_field_one.currentIndexChanged.connect(self._update_filters)
        self._metadata_field_two.currentIndexChanged.connect(self._update_filters)
        self._metadata_field_one.currentIndexChanged.connect(self._metadata_field_changed)
        self._metadata_field_two.currentIndexChanged.connect(self._metadata_field_changed)
        self._metadata_operator_one.currentIndexChanged.connect(self._update_filters)
        self._metadata_operator_two.currentIndexChanged.connect(self._update_filters)
        self._metadata_value_one.currentTextChanged.connect(self._update_filters)
        self._metadata_value_two.currentTextChanged.connect(self._update_filters)
        self._minimum_length.textChanged.connect(self._update_filters)
        self._minimum_hq.textChanged.connect(self._update_filters)
        self._length_operator.currentIndexChanged.connect(self._update_filters)
        self._hq_operator.currentIndexChanged.connect(self._update_filters)
        self._model.selection_toggled.connect(self._selection_toggled)

    def request_export_visible_metadata(self) -> str | None:
        """Export currently visible Project Records using their visible columns."""

        filepath, selected_filter = QFileDialog.getSaveFileName(
            self, "Export Project Records Metadata", "project_records_metadata.csv",
            "CSV files (*.csv);;Excel Workbook (*.xlsx);;All files (*)",
        )
        if not filepath:
            return None
        suffix = Path(filepath).suffix.lower()
        if suffix not in {".csv", ".xlsx"}:
            QMessageBox.warning(self, "Export Metadata", "Choose a .csv or .xlsx filename.")
            return None
        headers = self._model.columns[1:]
        rows = []
        for record in self._model.visible_rows:
            base = (record.record_id, record.dataset_name, record.length, record.hq_percent, record.source_type, record.description)
            metadata = tuple(record.metadata_value(field) for field in self._model.metadata_columns)
            rows.append((*base, *metadata))
        try:
            if suffix == ".csv":
                with Path(filepath).open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle); writer.writerow(headers); writer.writerows(rows)
            else:
                workbook = Workbook(); sheet = workbook.active; sheet.title = "Project Records"
                sheet.append(headers)
                for row in rows: sheet.append(row)
                workbook.save(filepath)
        except OSError as error:
            QMessageBox.warning(self, "Export Metadata", str(error))
            return None
        self.status_message_changed.emit(f"Exported project record metadata: {filepath}")
        return filepath

    def _project_changed(self, project: object | None) -> None:
        self._refresh_project(project if isinstance(project, Project) else None)

    def _refresh_project(self, project: Project | None) -> None:
        self._project = project
        rows = _project_record_rows(project) if project is not None else ()
        available_refs = {row.record_ref for row in rows}
        self._selected_refs.intersection_update(available_refs)
        self._selection_order = [ref for ref in self._selection_order if ref in self._selected_refs]
        self._populate_filter_choices(rows)
        self._model.set_rows(rows, self._selected_refs)
        self._update_filters()
        self._update_selection_summary()

    def _populate_filter_choices(self, rows: tuple[ProjectRecordRow, ...]) -> None:
        current_dataset = self._dataset_filter.currentData()
        current_source_type = self._source_type_filter.currentData()
        # The default Project Records scope is CURRENT datasets.  Do not let a
        # superseded or archived revision introduce metadata fields that are
        # absent from the records the researcher is currently selecting.
        fields = _metadata_fields(tuple(
            row for row in rows if row.revision_state is RevisionState.CURRENT
        ))
        self._available_metadata_fields = fields
        for combo, current in ((self._dataset_filter, current_dataset), (self._source_type_filter, current_source_type)):
            combo.blockSignals(True)
        try:
            self._dataset_filter.clear()
            self._dataset_filter.addItem("Dataset: All", None)
            for dataset_id, name in {row.dataset_id: row.dataset_name for row in rows}.items():
                self._dataset_filter.addItem(name, dataset_id)
            self._source_type_filter.clear()
            self._source_type_filter.addItem("Source Type: All", None)
            for source_type in sorted({row.source_type for row in rows}):
                self._source_type_filter.addItem(source_type, source_type)
            _restore_combo_data(self._dataset_filter, current_dataset)
            _restore_combo_data(self._source_type_filter, current_source_type)
        finally:
            self._dataset_filter.blockSignals(False)
            self._source_type_filter.blockSignals(False)
        self._populate_metadata_controls(fields)

    def _populate_metadata_controls(self, fields: tuple[str, ...]) -> None:
        previous_one, previous_two = self._metadata_field_one.currentData(), self._metadata_field_two.currentData()
        for combo in (self._metadata_field_one, self._metadata_field_two):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Field: Any", None)
            for field in fields:
                combo.addItem(_metadata_label(field), field)
            combo.blockSignals(False)
        _restore_combo_data(self._metadata_field_one, previous_one)
        _restore_combo_data(self._metadata_field_two, previous_two)
        # Common keys are a presentation convenience only; the registry is
        # always derived from actual record metadata and remains fully dynamic.
        if not self._model.metadata_columns:
            defaults = tuple(
                field
                for field in fields
                if field.casefold() in {"source_batch", "species", "location"}
            )
            self._model.set_metadata_columns(defaults)
        self._columns_menu.clear()
        selected = set(self._model.metadata_columns)
        for field in fields:
            action = self._columns_menu.addAction(_metadata_label(field))
            action.setCheckable(True)
            action.setChecked(field in selected)
            action.toggled.connect(lambda checked, value=field: self._toggle_metadata_column(value, checked))
        self._metadata_field_changed()

    def _metadata_field_changed(self) -> None:
        """Refresh operators and actual values for both dynamic field controls."""

        for field_combo, operator_combo, value_combo in (
            (self._metadata_field_one, self._metadata_operator_one, self._metadata_value_one),
            (self._metadata_field_two, self._metadata_operator_two, self._metadata_value_two),
        ):
            field = str(field_combo.currentData() or "")
            previous_operator = operator_combo.currentText()
            previous_value = value_combo.currentText()
            values = self._metadata_values_in_scope(field)
            operators = _metadata_operators(field, values)
            operator_combo.blockSignals(True)
            value_combo.blockSignals(True)
            try:
                operator_combo.clear()
                operator_combo.addItems(operators)
                index = operator_combo.findText(previous_operator)
                operator_combo.setCurrentIndex(index if index >= 0 else 0)
                value_combo.clear()
                value_combo.addItems(values)
                value_combo.setEditText(previous_value)
            finally:
                operator_combo.blockSignals(False)
                value_combo.blockSignals(False)
        self._update_filters()

    def _metadata_values_in_scope(self, field: str) -> tuple[str, ...]:
        """Distinct values from the current project scope, never hard-coded fields."""

        if not field:
            return ()
        rows = self._model.all_rows
        values = {
            row.metadata_value(field)
            for row in rows
            if self._row_is_in_current_scope(row) and row.metadata_value(field) != "—"
        }
        return tuple(sorted(values, key=str.casefold))

    def _row_is_in_current_scope(self, row: ProjectRecordRow) -> bool:
        if row.revision_state is RevisionState.SUPERSEDED and not self._include_previous.isChecked():
            return False
        if row.revision_state is RevisionState.ARCHIVED and not self._include_archived.isChecked():
            return False
        dataset_id = self._dataset_filter.currentData()
        if dataset_id is not None and row.dataset_id != dataset_id:
            return False
        source_type = self._source_type_filter.currentData()
        return source_type is None or row.source_type == source_type

    def _toggle_metadata_column(self, field: str, checked: bool) -> None:
        fields = list(self._model.metadata_columns)
        if checked and field not in fields:
            fields.append(field)
        elif not checked:
            fields = [value for value in fields if value != field]
        self._model.set_metadata_columns(tuple(fields))
        self._configure_dynamic_column_widths()

    def _configure_dynamic_column_widths(self) -> None:
        for offset in range(len(self._model.metadata_columns)):
            self._table.setColumnWidth(len(_BASE_COLUMNS) + offset, 150)

    def _update_filters(self) -> None:
        conditions = (
            (
                str(self._metadata_field_one.currentData() or ""),
                self._metadata_operator_one.currentText(),
                self._metadata_value_one.currentText(),
            ),
            (
                str(self._metadata_field_two.currentData() or ""),
                self._metadata_operator_two.currentText(),
                self._metadata_value_two.currentText(),
            ),
        )
        self._model.set_filters(
            search=self._search.text(),
            dataset_id=self._dataset_filter.currentData(),
            source_type=self._source_type_filter.currentData(),
            include_previous=self._include_previous.isChecked(),
            include_archived=self._include_archived.isChecked(),
            metadata_conditions=conditions,
            minimum_length=self._minimum_length.text(),
            minimum_hq=self._minimum_hq.text(),
            length_operator=self._length_operator.currentText(),
            hq_operator=self._hq_operator.currentText(),
        )
        self._update_selection_summary()

    def _selection_toggled(self, record_ref: RecordRef, checked: bool) -> None:
        if checked:
            if record_ref not in self._selected_refs:
                self._selected_refs.add(record_ref)
                self._selection_order.append(record_ref)
        else:
            self._selected_refs.discard(record_ref)
        self._update_selection_summary()

    def select_visible(self) -> None:
        for row in self._model.visible_rows:
            if row.record_ref not in self._selected_refs:
                self._selected_refs.add(row.record_ref)
                self._selection_order.append(row.record_ref)
        self._model._selected_refs = set(self._selected_refs)
        self._model.refresh_selection()
        self._update_selection_summary()

    def clear_selection(self) -> None:
        self._selected_refs.clear()
        self._selection_order.clear()
        self._model._selected_refs.clear()
        self._model.refresh_selection()
        self._update_selection_summary()

    def invert_visible_selection(self) -> None:
        for row in self._model.visible_rows:
            if row.record_ref in self._selected_refs:
                self._selected_refs.remove(row.record_ref)
            else:
                self._selected_refs.add(row.record_ref)
                self._selection_order.append(row.record_ref)
        self._selection_order = [ref for ref in self._selection_order if ref in self._selected_refs]
        self._model._selected_refs = set(self._selected_refs)
        self._model.refresh_selection()
        self._update_selection_summary()

    def _update_selection_summary(self) -> None:
        refs = self.selected_record_refs
        source_count = len({record_ref.dataset_id for record_ref in refs})
        self._selection_summary.setText(
            f"{len(refs)} records selected ({len(self._model.visible_rows)} visible) from {source_count} datasets"
        )
        self._create_button.setEnabled(bool(refs) and self._project is not None)

    def validation_for_selection(
        self,
        *,
        record_refs: tuple[RecordRef, ...] | None = None,
        output_record_ids: Mapping[RecordRef, str] | None = None,
    ) -> CrossDatasetSelectionValidation | None:
        if self._project is None:
            return None
        return validate_record_refs(
            self._project,
            self.selected_record_refs if record_refs is None else record_refs,
            output_record_ids=output_record_ids,
        )

    def request_create_dataset(self) -> object | None:
        selected_refs = self.selected_record_refs
        visible_selected_refs = tuple(
            row.record_ref
            for row in self._model.visible_rows
            if row.record_ref in self._selected_refs
        )
        if visible_selected_refs and len(visible_selected_refs) != len(selected_refs):
            scope_dialog = _CreateDatasetScopeDialog(
                self,
                visible_count=len(visible_selected_refs),
                total_count=len(selected_refs),
            )
            if scope_dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            if scope_dialog.use_visible_selection:
                selected_refs = visible_selected_refs
        validation = self.validation_for_selection(record_refs=selected_refs)
        if validation is None:
            QMessageBox.warning(self, "Create Dataset", "No Project is open.")
            return None
        output_record_ids: Mapping[RecordRef, str] | None = None
        if validation.output_id_collisions:
            source_batches = {
                row.record_ref: str(row.metadata.get("source_batch", ""))
                for row in self._model.all_rows
            }
            collision_dialog = _ResolveRecordIdCollisionsDialog(
                self,
                collisions=validation.output_id_collisions,
                source_batches=source_batches,
            )
            if collision_dialog.exec() != QDialog.DialogCode.Accepted:
                return None
            output_record_ids = collision_dialog.output_record_ids
            validation = self.validation_for_selection(
                record_refs=selected_refs,
                output_record_ids=output_record_ids,
            )
        if not validation.is_valid:
            self._show_validation(validation)
            return None
        if validation.shared_direct_source_warnings:
            QMessageBox.warning(self, "Provenance warning", "These records share a direct provenance source. Review them before combining.")
        dialog = _CreateDatasetDialog(self, suggested_id="derived_dataset")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return self.create_dataset(
            dialog.dataset_id,
            dialog.dataset_name,
            record_refs=selected_refs,
            output_record_ids=output_record_ids,
        )

    def create_dataset(
        self,
        dataset_id: str,
        name: str,
        *,
        record_refs: tuple[RecordRef, ...] | None = None,
        output_record_ids: Mapping[RecordRef, str] | None = None,
    ) -> object | None:
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_dataset_from_project_record_refs", None)
        if not callable(method):
            QMessageBox.warning(self, "Create Dataset", "Project dataset creation is not configured.")
            return None
        try:
            dataset = method(
                self.selected_record_refs if record_refs is None else record_refs,
                dataset_id=dataset_id,
                name=name,
                output_record_ids=dict(output_record_ids or {}),
            )
        except Exception as error:
            QMessageBox.warning(self, "Create Dataset", str(error))
            return None
        self.status_message_changed.emit(f"Derived Dataset created: {dataset.dataset_id}")
        return dataset

    def _show_validation(self, validation: CrossDatasetSelectionValidation) -> None:
        if validation.output_id_collisions:
            details = []
            for record_id, refs in validation.output_id_collisions.items():
                datasets = "\n".join(f"- {record_ref.dataset_id}" for record_ref in refs)
                details.append(f"{record_id} exists in:\n{datasets}\n\nChoose only one source record or resolve the output names using Source Batch.")
            QMessageBox.warning(self, "Record ID collision", "\n\n".join(details))
            return
        QMessageBox.warning(self, "Invalid record selection", _validation_text(validation))


def _project_record_rows(project: Project | None) -> tuple[ProjectRecordRow, ...]:
    if project is None:
        return ()
    rows: list[ProjectRecordRow] = []
    for entry in project.dataset_entries:
        dataset = entry.dataset
        if not isinstance(dataset, SequenceDataset):
            continue
        for record in dataset.records:
            metadata = dict(record.metadata)
            source_batch = _source_batch(metadata, dataset.metadata)
            if source_batch:
                metadata.setdefault("source_batch", source_batch)
            rows.append(ProjectRecordRow(
                record_ref=RecordRef(dataset.dataset_id, record.sequence_id),
                record_id=record.sequence_id,
                dataset_name=entry.display_name,
                dataset_id=dataset.dataset_id,
                length=len(record.sequence),
                hq_percent=format_hq_percent(record.source_reference),
                source_type=dataset.source_type.value,
                description=record.description or "",
                metadata=metadata,
                revision_state=entry.revision_state,
            ))
    return tuple(rows)


def _source_batch(record_metadata: Mapping[str, object], dataset_metadata: Mapping[str, object]) -> str:
    """Return canonical batch metadata, with a read-only legacy presentation fallback."""

    value = record_metadata.get("source_batch") or dataset_metadata.get("source_batch")
    if isinstance(value, str) and value.strip():
        return value.strip()
    legacy_source = dataset_metadata.get("source")
    if isinstance(legacy_source, str) and legacy_source.startswith("AB1 Folder:"):
        return legacy_source.partition(":")[2].strip()
    return ""


def _metadata_fields(rows: tuple[ProjectRecordRow, ...]) -> tuple[str, ...]:
    by_folded: dict[str, str] = {}
    for row in rows:
        for key in row.metadata:
            by_folded.setdefault(str(key).casefold(), str(key))
    ordered = [by_folded.pop(field.casefold()) for field in _COMMON_METADATA_FIELDS if field.casefold() in by_folded]
    return tuple(ordered + sorted(by_folded.values(), key=str.casefold))


def _metadata_label(field: str) -> str:
    """Display canonical arbitrary metadata keys without changing their identity."""

    return " ".join(part.capitalize() for part in field.replace("_", " ").split())


def _matches_search(row: ProjectRecordRow, search: str) -> bool:
    if not search:
        return True
    values = (row.record_id, row.dataset_name, row.dataset_id, row.description, row.source_type, *(str(value) for value in row.metadata.values()))
    return any(search in value.casefold() for value in values)


def _sort_value(row: ProjectRecordRow, column: str) -> object:
    if column == "Length":
        return row.length
    if column == "HQ%":
        return _hq_numeric(row.hq_percent)
    values = {
        "Select": "",
        "Record ID": row.record_id,
        "Dataset": row.dataset_name,
        "Source Type": row.source_type,
        "Description": row.description,
    }
    return str(values.get(column, row.metadata_value(column))).casefold()


def _restore_combo_data(combo: QComboBox, value: object) -> None:
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


def _optional_nonnegative_int(value: str) -> int | None:
    try:
        parsed = int(value.strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _optional_nonnegative_float(value: str) -> float | None:
    try:
        parsed = float(value.strip().rstrip("%"))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _hq_numeric(value: str) -> float:
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return -1.0


def _validation_text(validation: CrossDatasetSelectionValidation) -> str:
    if not validation.record_refs:
        return "Select at least one record."
    if validation.duplicate_refs:
        return "The same Project record was selected more than once."
    if validation.missing_datasets:
        return "A selected source Dataset no longer exists."
    if validation.unsupported_datasets:
        return "AlignmentDataset records cannot be used for cross-dataset selection."
    if validation.missing_records:
        return "A selected source record no longer exists."
    return "The selected records cannot be combined."


def create_project_records_viewer(context: object, project: object) -> ProjectRecordsViewer:
    if not isinstance(project, Project):
        raise ValueError("project must be a Project")
    return ProjectRecordsViewer(project, context)
