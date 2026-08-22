"""Settings that map directly to the existing consensus-v2.1 scoring model."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel, QVBoxLayout

from core.consensus_v2_1 import ConsensusV21Scoring


@dataclass(frozen=True)
class ConsensusSettings:
    minimum_base_quality: float = 20.0

    def scoring(self) -> ConsensusV21Scoring:
        return ConsensusV21Scoring(legacy_minimum_usable_quality=self.minimum_base_quality)

    def metadata(self) -> dict[str, object]:
        scoring = self.scoring()
        return {
            "consensus_engine": scoring.algorithm_version,
            "minimum_base_quality": self.minimum_base_quality,
            "conflict_resolution": "existing quality-based consensus-v2.1",
            "low_confidence_positions": "manual review",
        }


class ConsensusSettingsDialog(QDialog):
    """Keep consensus configuration honest: only engine-supported input is editable."""

    def __init__(self, *, read_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Consensus Settings")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Visible reads: {read_count}\n"
            "Conflict resolution: existing quality-based consensus-v2.1\n"
            "Low-confidence positions remain available for manual review."
        ))
        form = QFormLayout()
        self._minimum_quality = QDoubleSpinBox()
        self._minimum_quality.setRange(0.0, 60.0)
        self._minimum_quality.setDecimals(1)
        self._minimum_quality.setValue(20.0)
        form.addRow("Minimum base quality", self._minimum_quality)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Open Consensus Review")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> ConsensusSettings:
        return ConsensusSettings(minimum_base_quality=float(self._minimum_quality.value()))
