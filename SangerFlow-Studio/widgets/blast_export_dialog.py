"""Column-selection dialog for BLAST flat result export."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from export.blast_export import BLAST_EXPORT_COLUMNS, IDENTIFICATION_SUMMARY_COLUMNS


_LABELS = {
    "query_id": "Query ID", "rank": "Rank", "scientific_name": "Scientific Name",
    "organism": "Organism", "description": "Description", "hit_accession": "Accession",
    "identity": "Identity", "query_coverage": "Query Coverage",
    "alignment_length": "Alignment Length", "evalue": "E-value",
    "bit_score": "Bit Score", "database": "Database",
}


class BlastExportDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export BLAST Results")
        layout = QVBoxLayout(self)
        self._format = QComboBox()
        self._format.addItems(("CSV", "XLSX"))
        self._preset = QComboBox()
        self._preset.addItems(("Identification Summary", "Full Result"))
        self._preset.currentTextChanged.connect(self._apply_preset)
        layout.addWidget(QLabel("Format")); layout.addWidget(self._format)
        layout.addWidget(QLabel("Column preset")); layout.addWidget(self._preset)
        self._columns: dict[str, QCheckBox] = {}
        for key in BLAST_EXPORT_COLUMNS:
            box = QCheckBox(_LABELS[key])
            self._columns[key] = box
            layout.addWidget(box)
        self._apply_preset()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self) -> tuple[str, tuple[str, ...]]:
        columns = tuple(key for key, box in self._columns.items() if box.isChecked())
        if not columns:
            raise ValueError("Select at least one BLAST export column.")
        return self._format.currentText().lower(), columns

    def _apply_preset(self, *_ignored) -> None:
        selected = IDENTIFICATION_SUMMARY_COLUMNS if self._preset.currentText() == "Identification Summary" else BLAST_EXPORT_COLUMNS
        for key, box in self._columns.items():
            box.setChecked(key in selected)
