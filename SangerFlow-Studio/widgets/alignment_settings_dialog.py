"""Small, reproducible MAFFT settings dialog for Studio alignment runs."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QLabel, QLineEdit, QSpinBox, QVBoxLayout,
)


@dataclass(frozen=True)
class AlignmentSettings:
    strategy: str = "Auto"
    output_name: str = ""
    open_after_completion: bool = True
    gap_opening_penalty: float | None = None
    offset: float | None = None
    maxiterate: int | None = None
    adjust_direction: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "alignment_method": "MAFFT",
            "alignment_strategy": self.strategy,
            "alignment_parameters": {
                "gap_opening_penalty": self.gap_opening_penalty,
                "offset": self.offset,
                "maxiterate": self.maxiterate,
                "adjust_direction": self.adjust_direction,
            },
        }


class AlignmentSettingsDialog(QDialog):
    """Expose only MAFFT command options implemented by ``align_reads``."""

    STRATEGIES = ("Auto", "FFT-NS-2", "FFT-NS-i", "L-INS-i", "G-INS-i")

    def __init__(self, *, dataset_name: str, sequence_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alignment Settings")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Dataset: {dataset_name}\nSequences: {sequence_count}"))
        form = QFormLayout()
        self._strategy = QComboBox()
        self._strategy.addItems(self.STRATEGIES)
        self._output_name = QLineEdit(f"{dataset_name} alignment")
        self._open_after = QCheckBox("Open Alignment after completion")
        self._open_after.setChecked(True)
        form.addRow("Algorithm", QLabel("MAFFT"))
        form.addRow("Strategy", self._strategy)
        form.addRow("Output alignment name", self._output_name)
        form.addRow("", self._open_after)
        layout.addLayout(form)

        advanced = QGroupBox("Advanced MAFFT options")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_form = QFormLayout(advanced)
        self._gap_opening = QDoubleSpinBox()
        self._gap_opening.setRange(0.0, 20.0)
        self._gap_opening.setDecimals(3)
        self._gap_opening.setValue(1.53)
        self._offset = QDoubleSpinBox()
        self._offset.setRange(0.0, 20.0)
        self._offset.setDecimals(3)
        self._offset.setValue(0.0)
        self._maxiterate = QSpinBox()
        self._maxiterate.setRange(0, 10000)
        self._maxiterate.setValue(1000)
        self._adjust_direction = QCheckBox("Adjust direction")
        advanced_form.addRow("Gap opening penalty (--op)", self._gap_opening)
        advanced_form.addRow("Offset (--ep)", self._offset)
        advanced_form.addRow("Maximum iterations (--maxiterate)", self._maxiterate)
        advanced_form.addRow("", self._adjust_direction)
        layout.addWidget(advanced)
        self._advanced = advanced

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Run Alignment")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> AlignmentSettings:
        name = self._output_name.text().strip()
        if not name:
            raise ValueError("Output alignment name is required.")
        if not self._advanced.isChecked():
            return AlignmentSettings(
                strategy=self._strategy.currentText(), output_name=name,
                open_after_completion=self._open_after.isChecked(),
            )
        return AlignmentSettings(
            strategy=self._strategy.currentText(), output_name=name,
            open_after_completion=self._open_after.isChecked(),
            gap_opening_penalty=float(self._gap_opening.value()),
            offset=float(self._offset.value()), maxiterate=int(self._maxiterate.value()),
            adjust_direction=self._adjust_direction.isChecked(),
        )
