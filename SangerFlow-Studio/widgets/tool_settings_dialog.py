"""Small machine-local external-tool configuration dialog."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
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
    mafft_info_for_executable_path,
    set_configured_mafft_executable,
    store_validated_mafft_executable,
)
from widgets.mafft_setup_dialog import choose_existing_mafft_executable


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
        choose = QPushButton("Choose Executable…")
        choose.setIcon(studio_icon("folder"))
        choose.clicked.connect(self._choose)
        test = QPushButton("Test MAFFT")
        test.setIcon(studio_icon("quality"))
        test.clicked.connect(self._test)
        reset = QPushButton("Reset to Automatic Detection")
        reset.clicked.connect(self._reset_automatic)
        path_row = QHBoxLayout()
        path_row.addWidget(self._mafft_path, 1)
        path_row.addWidget(choose)
        path_row.addWidget(test)
        form.addRow("MAFFT status:", self._status)
        form.addRow("Executable:", path_row)
        self._version = QLabel()
        form.addRow("Version:", self._version)
        layout.addLayout(form)
        layout.addWidget(reset)
        self._mafft_path.editingFinished.connect(self._refresh_status)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _choose(self) -> None:
        info = choose_existing_mafft_executable(self, settings=self._settings)
        if info is not None and info.status is ToolStatus.AVAILABLE:
            self._mafft_path.setText(info.executable_path or "")
        self._refresh_status()

    def _reset_automatic(self) -> None:
        set_configured_mafft_executable(None, self._settings)
        self._mafft_path.clear()
        self._refresh_status()

    def _refresh_status(self) -> None:
        info = studio_mafft_info_for_path(self.mafft_executable, settings=self._settings)
        if info.status is ToolStatus.AVAILABLE:
            version = f" ({info.version})" if info.version else ""
            self._status.setText(f"✓ Found{version}")
            self._version.setText(info.version or "Detected (version unavailable)")
        elif self.mafft_executable:
            self._status.setText("Not found or not executable")
            self._version.setText("—")
        else:
            self._status.setText("Not found on PATH")
            self._version.setText("—")

    def _test(self) -> None:
        info = studio_mafft_info_for_path(self.mafft_executable, settings=self._settings)
        if info.status is ToolStatus.AVAILABLE:
            QMessageBox.information(
                self,
                "Test MAFFT",
                f"MAFFT is working correctly.\n\nExecutable:\n{info.executable_path}\n\nVersion:\n{info.version or 'Detected'}",
            )
        else:
            detail = str(info.metadata.get("detection_error") or info.metadata.get("version_error") or "")
            message = "MAFFT could not be executed. Choose an executable or check your installation."
            if detail:
                message = f"{message}\n\nDetails: {detail}"
            QMessageBox.warning(self, "Test MAFFT", message)
        self._refresh_status()

    def accept(self) -> None:  # noqa: N802 - Qt API
        if self.mafft_executable:
            info = store_validated_mafft_executable(self.mafft_executable, self._settings)
            if info.status is not ToolStatus.AVAILABLE:
                QMessageBox.warning(
                    self,
                    "MAFFT Could Not Be Used",
                    "The configured file could not be executed as MAFFT. It was not saved.",
                )
                self._refresh_status()
                return
        else:
            set_configured_mafft_executable(None, self._settings)
        super().accept()


def studio_mafft_info_for_path(path: str | None, *, settings: QSettings | None = None):
    """Keep dialog probing separate from Project/controller state."""

    return mafft_info_for_executable_path(path, settings=settings)
