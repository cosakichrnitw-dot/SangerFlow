"""Field-selection dialog for tabular Dataset metadata exports."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from core.sequence_dataset import SequenceDataset
from export.metadata_export import metadata_field_names


class MetadataExportDialog(QDialog):
    def __init__(self, dataset: SequenceDataset, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Metadata Table")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Standard columns: Sample_ID, Sequence length, Source type"))
        self._format = QComboBox()
        self._format.addItems(("CSV", "XLSX"))
        layout.addWidget(self._format)
        self._fields: dict[str, QCheckBox] = {}
        for field in metadata_field_names(dataset):
            box = QCheckBox(field)
            box.setChecked(True)
            self._fields[field] = box
            layout.addWidget(box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self) -> tuple[str, tuple[str, ...]]:
        return self._format.currentText().lower(), tuple(key for key, box in self._fields.items() if box.isChecked())
