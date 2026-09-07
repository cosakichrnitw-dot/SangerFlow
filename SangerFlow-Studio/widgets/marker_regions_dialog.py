"""Small dialogs for editing named AlignmentDataset marker regions."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.alignment_dataset import MarkerRegion


def validate_marker_regions(
    regions: Iterable[MarkerRegion],
    alignment_length: int,
) -> tuple[MarkerRegion, ...]:
    """Validate the UI contract before an immutable AlignmentDataset is made.

    ``AlignmentDataset`` already validates names and individual bounds.  The
    Partition exporters additionally reject overlap, but it remains a warning
    rather than an input error here so existing ``MarkerRegion`` semantics are
    preserved.
    """

    if alignment_length < 1:
        raise ValueError("alignment must contain at least one column")
    values = tuple(regions)
    names: set[str] = set()
    for region in values:
        if not isinstance(region, MarkerRegion):
            raise ValueError("marker regions must be MarkerRegion values")
        if region.name in names:
            raise ValueError(f"marker region name already exists: {region.name}")
        if region.end > alignment_length:
            raise ValueError(
                f"marker region '{region.name}' is outside the alignment length ({alignment_length})"
            )
        names.add(region.name)
    return values


def marker_regions_overlap(regions: Iterable[MarkerRegion]) -> bool:
    """Return whether any two named alignment-column intervals overlap."""

    previous_end = 0
    for region in sorted(regions, key=lambda value: (value.start, value.end, value.name)):
        if region.start <= previous_end:
            return True
        previous_end = region.end
    return False


class MarkerRegionEditDialog(QDialog):
    """Edit one 1-based inclusive marker interval."""

    def __init__(
        self,
        *,
        alignment_length: int,
        existing_regions: Iterable[MarkerRegion],
        initial: MarkerRegion | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Marker Region" if initial is None else "Edit Marker Region")
        self._alignment_length = int(alignment_length)
        self._existing_regions = tuple(existing_regions)
        self._initial = initial

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(self)
        if initial is not None:
            self.name_edit.setText(initial.name)
        self.start_spin = QSpinBox()
        self.end_spin = QSpinBox()
        for spin in (self.start_spin, self.end_spin):
            spin.setRange(1, self._alignment_length)
        self.start_spin.setValue(initial.start if initial is not None else 1)
        self.end_spin.setValue(initial.end if initial is not None else self._alignment_length)
        form.addRow("Name:", self.name_edit)
        form.addRow("Start column:", self.start_spin)
        form.addRow("End column:", self.end_spin)
        layout.addLayout(form)

        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #9a6700;")
        layout.addWidget(self.warning)
        self._update_warning()
        self.name_edit.textChanged.connect(self._update_warning)
        self.start_spin.valueChanged.connect(self._update_warning)
        self.end_spin.valueChanged.connect(self._update_warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Add" if initial is None else "Apply"
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def marker_region(self) -> MarkerRegion:
        return MarkerRegion(
            self.name_edit.text().strip(),
            int(self.start_spin.value()),
            int(self.end_spin.value()),
        )

    def _candidate_regions(self) -> tuple[MarkerRegion, ...]:
        return tuple(
            region
            for region in self._existing_regions
            if region != self._initial
        ) + (self.marker_region(),)

    def _update_warning(self, *_args) -> None:
        try:
            candidate = self.marker_region()
            if candidate.end < candidate.start:
                self.warning.setText("End column must be greater than or equal to start column.")
                return
            regions = self._candidate_regions()
            validate_marker_regions(regions, self._alignment_length)
            if marker_regions_overlap(regions):
                self.warning.setText(
                    "Warning: overlapping marker regions cannot currently be exported "
                    "as partition definitions."
                )
            else:
                self.warning.clear()
        except ValueError as error:
            self.warning.setText(str(error))

    def _accept_if_valid(self) -> None:
        try:
            candidate = self.marker_region()
            if candidate.end < candidate.start:
                raise ValueError("end column must be greater than or equal to start column")
            validate_marker_regions(self._candidate_regions(), self._alignment_length)
        except ValueError as error:
            QMessageBox.warning(self, self.windowTitle(), str(error))
            return
        self.accept()


class MarkerRegionsDialog(QDialog):
    """Manage staged regions without mutating the AlignmentDataset itself."""

    def __init__(
        self,
        regions: Iterable[MarkerRegion],
        *,
        alignment_length: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Marker Regions")
        self._alignment_length = int(alignment_length)
        self._regions = list(validate_marker_regions(regions, self._alignment_length))
        layout = QVBoxLayout(self)
        description = QLabel(
            "Marker Region coordinates are 1-based inclusive alignment columns; gaps count as columns."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(("Name", "Start", "End"))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color: #9a6700;")
        layout.addWidget(self.warning)

        controls = QHBoxLayout()
        self.edit_button = QPushButton("Edit…")
        self.delete_button = QPushButton("Delete")
        self.edit_button.clicked.connect(self._edit_selected)
        self.delete_button.clicked.connect(self._delete_selected)
        controls.addWidget(self.edit_button)
        controls.addWidget(self.delete_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    @property
    def regions(self) -> tuple[MarkerRegion, ...]:
        return tuple(self._regions)

    def _selected_index(self) -> int | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        index = selected[0].row()
        return index if 0 <= index < len(self._regions) else None

    def _edit_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        current = self._regions[index]
        dialog = MarkerRegionEditDialog(
            alignment_length=self._alignment_length,
            existing_regions=self._regions,
            initial=current,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._regions[index] = dialog.marker_region()
        self._refresh(select_row=index)

    def _delete_selected(self) -> None:
        index = self._selected_index()
        if index is None:
            return
        del self._regions[index]
        self._refresh(select_row=min(index, len(self._regions) - 1))

    def _refresh(self, *, select_row: int | None = None) -> None:
        self.table.setRowCount(len(self._regions))
        for row, region in enumerate(self._regions):
            for column, value in enumerate((region.name, str(region.start), str(region.end))):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, column, item)
        self.edit_button.setEnabled(bool(self._regions))
        self.delete_button.setEnabled(bool(self._regions))
        if select_row is not None and select_row >= 0:
            self.table.selectRow(select_row)
        if marker_regions_overlap(self._regions):
            self.warning.setText(
                "Warning: overlapping marker regions cannot currently be exported as partition definitions."
            )
        else:
            self.warning.clear()
