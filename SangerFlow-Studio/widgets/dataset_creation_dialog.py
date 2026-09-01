"""Shared naming dialog for user-created derived Datasets."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)


class CreateDatasetDialog(QDialog):
    """Collect a display name and a distinct internal Dataset ID."""

    def __init__(self, parent: QWidget, *, suggested_id: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create Dataset from Selected Records")
        self._name = QLineEdit()
        self._dataset_id = QLineEdit(suggested_id)
        form = QFormLayout()
        form.addRow("Dataset name", self._name)
        form.addRow("Dataset ID", self._dataset_id)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
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

    def accept(self) -> None:
        if not self.dataset_name or not self.dataset_id:
            QMessageBox.warning(self, "Create Dataset", "Dataset name and Dataset ID are required.")
            return
        super().accept()
