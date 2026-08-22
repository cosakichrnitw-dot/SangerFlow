"""Small input-only dialogs for Project lifecycle actions."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.icon_registry import studio_icon


class NewProjectDialog(QDialog):
    """Gather a Project name and an optional Studio Workspace location."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("New Project")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.location_edit = QLineEdit(self._default_location())
        browse = QPushButton("Choose…")
        browse.setIcon(studio_icon("folder"))
        browse.clicked.connect(self._choose_location)
        location_row = QHBoxLayout()
        location_row.addWidget(self.location_edit, 1)
        location_row.addWidget(browse)
        self.workspace_checkbox = QCheckBox("Create Project Workspace")
        self.workspace_checkbox.setChecked(True)
        form.addRow("Project Name:", self.name_edit)
        form.addRow("Location:", location_row)
        form.addRow("", self.workspace_checkbox)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def project_name(self) -> str:
        return self.name_edit.text().strip()

    @property
    def location(self) -> str:
        return self.location_edit.text().strip()

    @property
    def create_workspace(self) -> bool:
        return self.workspace_checkbox.isChecked()

    def accept(self) -> None:  # noqa: N802 - Qt API
        if self.project_name and (not self.create_workspace or self.location):
            super().accept()

    def _choose_location(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Project Location", self.location)
        if selected:
            self.location_edit.setText(selected)

    @staticmethod
    def _default_location() -> str:
        documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        return str(Path(documents)) if documents else str(Path.home())
