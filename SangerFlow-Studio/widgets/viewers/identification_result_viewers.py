"""Studio BLAST/BOLD result viewers and selection-to-dataset actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.blast_filter import BlastResultFilter, BlastResultSelection, apply_blast_filter
from core.blast_result import BlastHit, BlastResultDataset
from core.bold_filter import BoldResultFilter, BoldResultSelection, apply_bold_filter
from core.bold_result import BoldHit, BoldResultDataset
from export.blast_export import export_blast_result_to_csv, export_blast_result_to_excel, export_blast_result_to_excel_selected, export_blast_result_to_tsv
from export.bold_export import export_bold_result_to_excel, export_bold_result_to_tsv
from widgets.blast_export_dialog import BlastExportDialog
from widgets.identification_service_dialogs import BlastMetadataDialog
from app.icon_registry import studio_icon
from widgets.viewers.base_viewer import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


class BlastResultStudioViewer(BaseViewer):
    """PySide Studio viewer for immutable BLAST result payloads."""

    def __init__(self, blast_result: BlastResultDataset, *, context: object | None = None) -> None:
        if not isinstance(blast_result, BlastResultDataset):
            raise ValueError("BlastResultStudioViewer requires a BlastResultDataset")
        self._result = blast_result
        self._context = context
        self._filter = BlastResultFilter()
        self._filtered_ids: tuple[str, ...] = blast_result.query_ids()
        self._selected_ids: set[str] = set()
        self._action_provider = _IdentificationActionProvider()
        super().__init__(
            viewer_id=f"blast-result-viewer-{_safe_identifier(blast_result.result_id)}",
            viewer_title=f"BLAST Results: {blast_result.name}",
            viewer_kind="blast-result",
            source_object_id=blast_result.result_id,
        )
        self._build_ui()
        self._refresh_table()

    @property
    def result(self) -> BlastResultDataset:
        return self._result

    @property
    def current_selection(self) -> BlastResultSelection:
        return BlastResultSelection(
            self._result.result_id,
            tuple(query_id for query_id in self._result.query_ids() if query_id in self._selected_ids),
            {
                **dict(self._filter.metadata()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "identification.apply_filter",
            "identification.clear_filter",
            "identification.select_all_filtered",
            "identification.clear_selection",
            "identification.create_dataset",
            "identification.export_excel",
            "identification.export_tsv",
            "identification.export_results",
            "identification.apply_blast_metadata",
        )

    def apply_filter_from_fields(self) -> BlastResultSelection:
        self._filter = BlastResultFilter(
            scientific_name=_text_or_none(self._scientific_name.text()),
            organism=_text_or_none(self._organism.text()),
            min_identity=_float_or_none(self._min_identity.text()),
            min_coverage=_float_or_none(self._min_coverage.text()),
            max_evalue=_float_or_none(self._max_evalue.text()),
            top_hit_only=self._top_hit_only.isChecked(),
        )
        selection = apply_blast_filter(self._result, self._filter)
        self._filtered_ids = tuple(
            query_id
            for query_id in selection.selected_query_ids
            if self._query_text_matches(query_id)
        )
        self._selected_ids = set(self._filtered_ids)
        self._refresh_table()
        return self.current_selection

    def request_apply_filter(self) -> BlastResultSelection | None:
        """Apply valid UI criteria without allowing parsing errors to escape Qt."""

        try:
            return self.apply_filter_from_fields()
        except ValueError as error:
            QMessageBox.warning(self, "Filter BLAST Results", str(error))
            return None

    def clear_filter(self) -> None:
        """Restore all result rows while leaving explicit selection unchanged."""

        self._scientific_name.clear()
        self._organism.clear()
        self._query_text.clear()
        self._accession.clear()
        self._min_identity.clear()
        self._min_coverage.clear()
        self._max_evalue.clear()
        self._top_hit_only.setChecked(True)
        self._filter = BlastResultFilter()
        self._filtered_ids = self._result.query_ids()
        self._refresh_table()

    def select_all_filtered(self) -> None:
        self._selected_ids = set(self._filtered_ids)
        self._refresh_table()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        self._refresh_table()

    def create_dataset_from_selection(self) -> object | None:
        if not self._selected_ids:
            self.status_message_changed.emit("No BLAST queries are selected.")
            return None
        name, accepted = QInputDialog.getText(
            self,
            "Create Dataset from BLAST Selection",
            "Dataset name:",
            text=_suggest_dataset_name(self._result.name, self._filter.metadata()),
        )
        if not accepted:
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_dataset_from_blast_result_selection", None)
        if not callable(method):
            self.status_message_changed.emit("Project registration is not configured.")
            return None
        try:
            dataset = method(self, self.current_selection, name=name)
        except ValueError as error:
            QMessageBox.warning(self, "Create Dataset from BLAST Selection", str(error))
            return None
        self.status_message_changed.emit(f"Derived Dataset created: {dataset.dataset_id}")
        return dataset

    def request_export_excel(self) -> str | None:
        return _request_result_export(
            self,
            self._result,
            title="Export BLAST Result as Excel",
            default_suffix=".xlsx",
            name_filter="Excel Workbook (*.xlsx);;All files (*)",
            exporter=export_blast_result_to_excel,
        )

    def request_export_tsv(self) -> str | None:
        return _request_result_export(
            self,
            self._result,
            title="Export BLAST Result as TSV",
            default_suffix=".tsv",
            name_filter="TSV files (*.tsv);;All files (*)",
            exporter=export_blast_result_to_tsv,
        )

    def request_export_results(self) -> str | None:
        dialog = BlastExportDialog(self)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        try:
            format_name, columns = dialog.options()
        except ValueError as error:
            QMessageBox.warning(self, "Export BLAST Results", str(error))
            return None
        suffix = ".csv" if format_name == "csv" else ".xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export BLAST Results", f"{_safe_identifier(self._result.result_id)}{suffix}",
            "CSV files (*.csv);;Excel Workbook (*.xlsx);;All files (*)",
        )
        if not filepath:
            return None
        try:
            if format_name == "csv":
                export_blast_result_to_csv(self._result, filepath, columns=columns)
            else:
                export_blast_result_to_excel_selected(self._result, filepath, columns=columns)
        except ValueError as error:
            QMessageBox.warning(self, "Export BLAST Results", str(error))
            return None
        self.status_message_changed.emit(f"Exported: {filepath}")
        return filepath

    def apply_results_to_metadata(self) -> object | None:
        if not self._top_hit_only.isChecked():
            QMessageBox.warning(
                self,
                "Apply BLAST Metadata",
                "Enable Top hit only before applying metadata. "
                "Metadata application records the Rank 1 hit for each selected query.",
            )
            return None
        selected_query_ids = self.current_selection.selected_query_ids
        if not selected_query_ids:
            QMessageBox.warning(
                self,
                "Apply BLAST Metadata",
                "Select at least one query before applying BLAST metadata.",
            )
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "apply_blast_result_metadata", None)
        if not callable(method):
            self.status_message_changed.emit("Project metadata revision is not configured.")
            return None
        dialog = BlastMetadataDialog(
            dataset_name=self._result.parent_dataset_id,
            query_count=len(selected_query_ids), parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted:
            return None
        try:
            dataset = method(
                self._result,
                dialog.settings(),
                selected_query_ids=selected_query_ids,
            )
        except ValueError as error:
            QMessageBox.warning(self, "Apply BLAST Metadata", str(error))
            return None
        self.status_message_changed.emit(
            f"BLAST metadata applied to {len(selected_query_ids)} selected query record(s) "
            f"in revision: {dataset.dataset_id}"
        )
        return dataset

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        self._project_storage_feedback = QLabel(
            "Stored in Project Results. Save Project to persist it to disk."
        )
        self._project_storage_feedback.setObjectName("blastProjectStorageFeedback")
        self._project_storage_feedback.setToolTip(
            "This refers to the current Project, not an Excel or TSV export file."
        )
        layout.addWidget(self._summary)
        layout.addWidget(self._project_storage_feedback)
        filter_box = QWidget()
        form = QFormLayout(filter_box)
        self._scientific_name = QLineEdit()
        self._organism = QLineEdit()
        self._query_text = QLineEdit()
        self._accession = QLineEdit()
        self._min_identity = QLineEdit()
        self._min_coverage = QLineEdit()
        self._max_evalue = QLineEdit()
        self._top_hit_only = QCheckBox("Top hit only")
        self._top_hit_only.setChecked(True)
        self._top_hit_only.setToolTip(
            "Show and use only Rank 1 for each query. Turn this off to show all hits."
        )
        form.addRow("Scientific name", self._scientific_name)
        form.addRow("Organism contains", self._organism)
        form.addRow("Query / sample contains", self._query_text)
        form.addRow("Accession contains", self._accession)
        form.addRow("Identity >=", self._min_identity)
        form.addRow("Coverage >=", self._min_coverage)
        form.addRow("E-value <=", self._max_evalue)
        form.addRow("", self._top_hit_only)
        layout.addWidget(filter_box)
        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply Filter")
        self._apply_button.setIcon(studio_icon("filter"))
        self._apply_button.clicked.connect(self.request_apply_filter)
        self._clear_filter_button = QPushButton("Clear Filter")
        self._clear_filter_button.setIcon(studio_icon("clear"))
        self._clear_filter_button.clicked.connect(self.clear_filter)
        self._select_all_button = QPushButton("Select All Filtered")
        self._select_all_button.setIcon(studio_icon("select"))
        self._select_all_button.clicked.connect(self.select_all_filtered)
        self._clear_button = QPushButton("Clear Selection")
        self._clear_button.setIcon(studio_icon("clear"))
        self._clear_button.clicked.connect(self.clear_selection)
        self._create_button = QPushButton("Create Dataset from Selection")
        self._create_button.setIcon(studio_icon("create_dataset"))
        self._create_button.clicked.connect(self.create_dataset_from_selection)
        self._apply_metadata_button = QPushButton("Apply Selected Top Hits to Metadata…")
        self._apply_metadata_button.setIcon(studio_icon("apply_metadata"))
        self._apply_metadata_button.clicked.connect(self.apply_results_to_metadata)
        for button in (
            self._apply_button,
            self._clear_filter_button,
            self._select_all_button,
            self._clear_button,
            self._create_button,
            self._apply_metadata_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._table = QTableWidget()
        # Selection is query-based because Dataset derivation uses stable query
        # IDs.  With Top hit only, each selected query visibly means Rank 1.
        self._table.setColumnCount(11)
        self._table.setHorizontalHeaderLabels(
            (
                "Selected", "Query ID", "Rank", "Scientific Name", "Accession",
                "Identity %", "Coverage %", "Alignment length", "E-value", "Bit Score", "Description",
            )
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setSortingEnabled(True)
        self._table.itemChanged.connect(self._item_changed)
        self._top_hit_only.toggled.connect(self._refresh_table)
        self._top_hit_only.toggled.connect(self._apply_metadata_button.setEnabled)
        layout.addWidget(self._table, 1)

    def show_project_storage_feedback(self, message: str) -> None:
        """Show Controller-confirmed Project Results storage without implying export."""

        self._project_storage_feedback.setText(str(message))
        self.status_message_changed.emit(str(message))

    def _refresh_table(self) -> None:
        displayed_hits = tuple(
            (query_id, rank, hit)
            for query_id in self._filtered_ids
            for rank, hit in enumerate(
                self._result.get_hits(query_id)[:1]
                if self._top_hit_only.isChecked()
                else self._result.get_hits(query_id),
                start=1,
            )
        )
        self._summary.setText(
            f"Queries: {len(self._result.query_ids())}    "
            f"Filtered: {len(self._filtered_ids)}    "
            f"Hits shown: {len(displayed_hits)}    "
            f"Selected: {len(self._selected_ids)} / {len(self._result.query_ids())}"
        )
        self._table.blockSignals(True)
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(displayed_hits))
        for row_index, (query_id, rank, hit) in enumerate(displayed_hits):
            selected = QTableWidgetItem()
            selected.setCheckState(_check_state(query_id in self._selected_ids))
            self._table.setItem(row_index, 0, selected)
            values = (
                query_id,
                rank,
                hit.scientific_name,
                hit.hit_accession,
                f"{hit.identity:.3f}",
                f"{hit.query_coverage:.3f}",
                hit.alignment_length,
                f"{hit.evalue:g}",
                "-" if hit.bit_score is None else f"{hit.bit_score:.3f}",
                hit.description or "",
            )
            for column, value in enumerate(values, start=1):
                self._table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self._table.blockSignals(False)
        self._table.setSortingEnabled(True)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        query_id_item = self._table.item(item.row(), 1)
        if query_id_item is None:
            return
        query_id = query_id_item.text()
        if item.checkState().value:
            self._selected_ids.add(query_id)
        else:
            self._selected_ids.discard(query_id)
        self._summary.setText(
            f"Total: {len(self._result.query_ids())}    Filtered: {len(self._filtered_ids)}    "
            f"Selected: {len(self._selected_ids)} / {len(self._result.query_ids())}"
        )

    def _query_text_matches(self, query_id: str) -> bool:
        """Apply viewer-only text criteria against stable hit/query identities."""

        query_text = _text_or_none(self._query_text.text())
        accession = _text_or_none(self._accession.text())
        if query_text is not None and query_text.casefold() not in query_id.casefold():
            return False
        if accession is None:
            return True
        hits = self._result.get_hits(query_id)
        candidates = hits[:1] if self._filter.top_hit_only else hits
        return any(accession.casefold() in hit.hit_accession.casefold() for hit in candidates)


class BoldResultStudioViewer(BaseViewer):
    """PySide Studio viewer for immutable BOLD result payloads."""

    def __init__(self, bold_result: BoldResultDataset, *, context: object | None = None) -> None:
        if not isinstance(bold_result, BoldResultDataset):
            raise ValueError("BoldResultStudioViewer requires a BoldResultDataset")
        self._result = bold_result
        self._context = context
        self._filter = BoldResultFilter()
        self._filtered_ids: tuple[str, ...] = bold_result.query_ids()
        self._selected_ids: set[str] = set()
        self._action_provider = _IdentificationActionProvider()
        super().__init__(
            viewer_id=f"bold-result-viewer-{_safe_identifier(bold_result.result_id)}",
            viewer_title=f"BOLD Results: {bold_result.name}",
            viewer_kind="bold-result",
            source_object_id=bold_result.result_id,
        )
        self._build_ui()
        self._refresh_table()

    @property
    def result(self) -> BoldResultDataset:
        return self._result

    @property
    def current_selection(self) -> BoldResultSelection:
        return BoldResultSelection(
            self._result.result_id,
            tuple(query_id for query_id in self._result.query_ids() if query_id in self._selected_ids),
            {
                **dict(self._filter.metadata()),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._action_provider,)

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return (
            "identification.apply_filter",
            "identification.select_all_filtered",
            "identification.clear_selection",
            "identification.create_dataset",
            "identification.export_excel",
            "identification.export_tsv",
        )

    def apply_filter_from_fields(self) -> BoldResultSelection:
        self._filter = BoldResultFilter(
            species_name=_text_or_none(self._species_name.text()),
            genus=_text_or_none(self._genus.text()),
            bin_uri=_text_or_none(self._bin_uri.text()),
            min_similarity=_float_or_none(self._min_similarity.text()),
            top_hit_only=self._top_hit_only.isChecked(),
        )
        selection = apply_bold_filter(self._result, self._filter)
        self._filtered_ids = selection.selected_query_ids
        self._selected_ids = set(self._filtered_ids)
        self._refresh_table()
        return selection

    def select_all_filtered(self) -> None:
        self._selected_ids = set(self._filtered_ids)
        self._refresh_table()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        self._refresh_table()

    def create_dataset_from_selection(self) -> object | None:
        if not self._selected_ids:
            self.status_message_changed.emit("No BOLD queries are selected.")
            return None
        name, accepted = QInputDialog.getText(
            self,
            "Create Dataset from BOLD Selection",
            "Dataset name:",
            text=_suggest_dataset_name(self._result.name, self._filter.metadata()),
        )
        if not accepted:
            return None
        controller = getattr(self._context, "project_controller", None)
        method = getattr(controller, "create_dataset_from_bold_result_selection", None)
        if not callable(method):
            self.status_message_changed.emit("Project registration is not configured.")
            return None
        dataset = method(self, self.current_selection, name=name)
        self.status_message_changed.emit(f"Derived Dataset created: {dataset.dataset_id}")
        return dataset

    def request_export_excel(self) -> str | None:
        return _request_result_export(
            self,
            self._result,
            title="Export BOLD Result as Excel",
            default_suffix=".xlsx",
            name_filter="Excel Workbook (*.xlsx);;All files (*)",
            exporter=export_bold_result_to_excel,
        )

    def request_export_tsv(self) -> str | None:
        return _request_result_export(
            self,
            self._result,
            title="Export BOLD Result as TSV",
            default_suffix=".tsv",
            name_filter="TSV files (*.tsv);;All files (*)",
            exporter=export_bold_result_to_tsv,
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        layout.addWidget(self._summary)
        filter_box = QWidget()
        form = QFormLayout(filter_box)
        self._species_name = QLineEdit()
        self._genus = QLineEdit()
        self._bin_uri = QLineEdit()
        self._min_similarity = QLineEdit()
        self._top_hit_only = QCheckBox("Top hit only")
        self._top_hit_only.setChecked(True)
        form.addRow("Species", self._species_name)
        form.addRow("Genus", self._genus)
        form.addRow("BIN URI", self._bin_uri)
        form.addRow("Similarity >=", self._min_similarity)
        form.addRow("", self._top_hit_only)
        layout.addWidget(filter_box)
        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply Filter")
        self._apply_button.setIcon(studio_icon("filter"))
        self._apply_button.clicked.connect(self.apply_filter_from_fields)
        self._select_all_button = QPushButton("Select All Filtered")
        self._select_all_button.setIcon(studio_icon("select"))
        self._select_all_button.clicked.connect(self.select_all_filtered)
        self._clear_button = QPushButton("Clear Selection")
        self._clear_button.setIcon(studio_icon("clear"))
        self._clear_button.clicked.connect(self.clear_selection)
        self._create_button = QPushButton("Create Dataset from Selection")
        self._create_button.setIcon(studio_icon("create_dataset"))
        self._create_button.clicked.connect(self.create_dataset_from_selection)
        for button in (self._apply_button, self._select_all_button, self._clear_button, self._create_button):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        self._table = QTableWidget()
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels(
            ("Selected", "Query ID", "Identification", "Similarity %", "BOLD ID", "Status")
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.itemChanged.connect(self._item_changed)
        layout.addWidget(self._table, 1)

    def _refresh_table(self) -> None:
        self._summary.setText(
            f"Total: {len(self._result.query_ids())}    "
            f"Filtered: {len(self._filtered_ids)}    "
            f"Selected: {len(self._selected_ids)} / {len(self._result.query_ids())}"
        )
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._filtered_ids))
        for row_index, query_id in enumerate(self._filtered_ids):
            hit = self._result.get_hits(query_id)[0]
            selected = QTableWidgetItem()
            selected.setCheckState(_check_state(query_id in self._selected_ids))
            self._table.setItem(row_index, 0, selected)
            values = (
                query_id,
                hit.species_name or hit.genus or "-",
                "-" if hit.similarity is None else f"{hit.similarity:.3f}",
                hit.process_id or hit.record_id or hit.bin_uri or "-",
                "Identified" if hit.species_name else "No species name",
            )
            for column, value in enumerate(values, start=1):
                self._table.setItem(row_index, column, QTableWidgetItem(str(value)))
        self._table.blockSignals(False)

    def _item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        query_id_item = self._table.item(item.row(), 1)
        if query_id_item is None:
            return
        query_id = query_id_item.text()
        if item.checkState().value:
            self._selected_ids.add(query_id)
        else:
            self._selected_ids.discard(query_id)
        self._summary.setText(
            f"Total: {len(self._result.query_ids())}    Filtered: {len(self._filtered_ids)}    "
            f"Selected: {len(self._selected_ids)} / {len(self._result.query_ids())}"
        )


class _IdentificationActionProvider:
    def actions_for(self, viewer: object) -> tuple[ViewerAction, ...]:
        actions = [
            ViewerAction(
                action_id="identification.apply_filter",
                label="Apply Filter",
                callback=getattr(
                    viewer,
                    "request_apply_filter",
                    getattr(viewer, "apply_filter_from_fields"),
                ),
            ),
            ViewerAction(
                action_id="identification.select_all_filtered",
                label="Select All Filtered",
                callback=getattr(viewer, "select_all_filtered"),
            ),
            ViewerAction(
                action_id="identification.clear_selection",
                label="Clear Selection",
                callback=getattr(viewer, "clear_selection"),
            ),
            ViewerAction(
                action_id="identification.create_dataset",
                label="Create Dataset from Selection",
                callback=getattr(viewer, "create_dataset_from_selection"),
            ),
            ViewerAction(
                action_id="identification.export_excel",
                label="Export Excel",
                tooltip="Export all result hits using the existing Excel exporter",
                callback=getattr(viewer, "request_export_excel"),
            ),
            ViewerAction(
                action_id="identification.export_tsv",
                label="Export TSV",
                tooltip="Export all result hits using the existing TSV exporter",
                callback=getattr(viewer, "request_export_tsv"),
            ),
        ]
        if isinstance(viewer, BlastResultStudioViewer):
            actions.append(
                ViewerAction(
                    action_id="identification.clear_filter",
                    label="Clear Filter",
                    callback=viewer.clear_filter,
                )
            )
            actions.append(
                ViewerAction(
                    action_id="identification.export_results",
                    label="Export Results...",
                    tooltip="Choose CSV/XLSX and BLAST result columns",
                    callback=viewer.request_export_results,
                )
            )
            actions.append(
                ViewerAction(
                    action_id="identification.apply_blast_metadata",
                    label="Apply Selected Top Hits to Metadata…",
                    tooltip="Create a metadata revision from the Rank 1 hit of each selected query",
                    callback=viewer.apply_results_to_metadata,
                )
            )
        return tuple(actions)


def create_blast_result_viewer(context: object, result: object) -> BlastResultStudioViewer:
    if not isinstance(result, BlastResultDataset):
        result = _resolve_payload(context, result)
    return BlastResultStudioViewer(result, context=context)


def create_bold_result_viewer(context: object, result: object) -> BoldResultStudioViewer:
    if not isinstance(result, BoldResultDataset):
        result = _resolve_payload(context, result)
    return BoldResultStudioViewer(result, context=context)


def _text_or_none(value: str) -> str | None:
    value = value.strip()
    return value or None


def _float_or_none(value: str) -> float | None:
    value = value.strip()
    if not value:
        return None
    return float(value)


def _check_state(selected: bool):
    from PySide6.QtCore import Qt

    return Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked


def _safe_identifier(value: str | None) -> str:
    if value is None:
        return "result"
    return "".join(character if character.isalnum() or character in {"-", "_"} else "_" for character in value).strip("_") or "result"


def _suggest_dataset_name(result_name: str, metadata: object) -> str:
    if isinstance(metadata, dict):
        for key in ("scientific_name", "species_name", "genus", "bin_uri"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
    return f"{result_name} selection"


def _resolve_payload(context: object, analysis_result: object) -> object:
    repository = getattr(getattr(context, "app_state", None), "current_repository", None)
    getter = getattr(repository, "get_for_analysis_result", None)
    if not callable(getter):
        raise ValueError("Analysis result payload repository is not configured")
    return getter(analysis_result)


def _request_result_export(
    viewer: BaseViewer,
    result: object,
    *,
    title: str,
    default_suffix: str,
    name_filter: str,
    exporter: object,
) -> str | None:
    result_id = getattr(result, "result_id", "result")
    controller = getattr(getattr(viewer, "_context", None), "project_controller", None)
    directory_getter = getattr(controller, "export_default_directory", None)
    try:
        directory = str(directory_getter() or "") if callable(directory_getter) else ""
    except Exception:
        directory = ""
    filename = f"{_safe_identifier(result_id)}{default_suffix}"
    filepath, _selected_filter = QFileDialog.getSaveFileName(
        viewer,
        title,
        str(Path(directory) / filename) if directory else filename,
        name_filter,
    )
    if not filepath:
        return None
    filepath = _ensure_suffix(filepath, default_suffix)
    try:
        exporter(result, filepath)  # type: ignore[misc]
    except Exception as error:
        QMessageBox.warning(viewer, title, str(error))
        return None
    viewer.status_message_changed.emit(f"Exported: {filepath}")
    return filepath


def _ensure_suffix(filepath: str, suffix: str) -> str:
    path = Path(filepath)
    if path.suffix:
        return str(path)
    return str(path.with_suffix(suffix))
