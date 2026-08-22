"""Small machine-local external-tool configuration dialog."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.tool_manager import ToolStatus
from app.icon_registry import studio_icon
from services.application_settings import (
    configured_mafft_executable,
    set_configured_mafft_executable,
    studio_mafft_info,
)


class ToolSettingsDialog(QDialog):
    """Configure MAFFT for this user machine, never for Project data."""

    def __init__(self, parent=None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Tool Settings")
        self._build_ui()
        self._refresh_status()

    @property
    def mafft_executable(self) -> str | None:
        text = self._mafft_path.text().strip()
        return text or None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._status = QLabel()
        self._mafft_path = QLineEdit(configured_mafft_executable(self._settings) or "")
        browse = QPushButton("Browse…")
        browse.setIcon(studio_icon("folder"))
        browse.clicked.connect(self._browse)
        test = QPushButton("Test")
        test.setIcon(studio_icon("quality"))
        test.clicked.connect(self._test)
        path_row = QHBoxLayout()
        path_row.addWidget(self._mafft_path, 1)
        path_row.addWidget(browse)
        path_row.addWidget(test)
        form.addRow("MAFFT status:", self._status)
        form.addRow("Executable:", path_row)
        layout.addLayout(form)
        self._mafft_path.editingFinished.connect(self._refresh_status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Choose MAFFT executable")
        if path:
            self._mafft_path.setText(path)
            self._refresh_status()

    def _refresh_status(self) -> None:
        info = studio_mafft_info_for_path(self.mafft_executable, settings=self._settings)
        if info.status is ToolStatus.AVAILABLE:
            version = f" ({info.version})" if info.version else ""
            self._status.setText(f"✓ Found{version}")
        elif self.mafft_executable:
            self._status.setText("Not found or not executable")
        else:
            self._status.setText("Not found on PATH")

    def _test(self) -> None:
        info = studio_mafft_info_for_path(self.mafft_executable, settings=self._settings)
        if info.status is ToolStatus.AVAILABLE:
            QMessageBox.information(self, "MAFFT", f"MAFFT is available at:\n{info.executable_path}")
        else:
            QMessageBox.warning(self, "MAFFT", "MAFFT was not found. Choose an executable or add it to PATH.")
        self._refresh_status()

    def accept(self) -> None:  # noqa: N802 - Qt API
        set_configured_mafft_executable(self.mafft_executable, self._settings)
        super().accept()


def studio_mafft_info_for_path(path: str | None, *, settings: QSettings | None = None):
    """Keep dialog probing separate from Project/controller state."""

    if path:
        from tools.mafft_tool import detect_mafft

        return detect_mafft(path)
    return studio_mafft_info(settings)
