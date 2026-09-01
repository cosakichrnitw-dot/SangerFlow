"""Small, machine-local MAFFT setup flow used before Studio alignment."""

from __future__ import annotations

from PySide6.QtCore import QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.tool_manager import ToolInfo, ToolStatus
from services.application_settings import (
    mafft_info_for_executable_path,
    resolve_studio_mafft_executable,
    store_validated_mafft_executable,
)


MAFFT_DOWNLOAD_URL = "https://mafft.cbrc.jp/alignment/software/"


def choose_existing_mafft_executable(
    parent=None,
    *,
    settings: QSettings | None = None,
) -> ToolInfo | None:
    """Choose, probe, and only then persist a MAFFT executable."""

    path, _ = QFileDialog.getOpenFileName(parent, "Choose MAFFT Executable")
    if not path:
        return None
    info = store_validated_mafft_executable(path, settings)
    if info.status is ToolStatus.AVAILABLE:
        return info
    detail = str(info.metadata.get("detection_error") or info.metadata.get("version_error") or "")
    message = "The selected file could not be executed as MAFFT."
    if detail:
        message = f"{message}\n\nDetails: {detail}"
    QMessageBox.warning(parent, "MAFFT Could Not Be Used", message)
    return info


class MafftSetupDialog(QDialog):
    """Explain external MAFFT installation without installing anything."""

    def __init__(self, parent=None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Set Up MAFFT")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        explanation = QLabel(
            "MAFFT is an external alignment program used by SangerFlow.\n\n"
            "On macOS, install MAFFT separately, then choose its executable here. "
            "SangerFlow does not install or modify system software for you."
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        actions = QHBoxLayout()
        download = QPushButton("Open MAFFT Download Page")
        download.clicked.connect(self._open_download_page)
        choose = QPushButton("Choose Existing MAFFT…")
        choose.clicked.connect(self._choose_existing)
        check = QPushButton("Check Again")
        check.clicked.connect(self._check_again)
        actions.addWidget(download)
        actions.addWidget(choose)
        actions.addWidget(check)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self._refresh_status()

    def _open_download_page(self) -> None:
        QDesktopServices.openUrl(QUrl(MAFFT_DOWNLOAD_URL))

    def _refresh_status(self) -> ToolInfo:
        info = mafft_info_for_executable_path(None, settings=self._settings)
        if info.status is ToolStatus.AVAILABLE:
            self._status.setText(f"MAFFT detected: {info.executable_path}\n{info.version or ''}".rstrip())
        else:
            self._status.setText("MAFFT is not currently available on this computer.")
        return info

    def _check_again(self) -> None:
        if self._refresh_status().status is ToolStatus.AVAILABLE:
            self.accept()

    def _choose_existing(self) -> None:
        info = choose_existing_mafft_executable(self, settings=self._settings)
        self._refresh_status()
        if info is not None and info.status is ToolStatus.AVAILABLE:
            self.accept()


class MafftNotFoundDialog(QDialog):
    """Focused preflight dialog shown instead of a generic alignment failure."""

    def __init__(self, parent=None, *, settings: QSettings | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("MAFFT Not Found")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        message = QLabel(
            "MAFFT is required for sequence alignment.\n\n"
            "SangerFlow could not find a working MAFFT installation on this computer."
        )
        message.setWordWrap(True)
        layout.addWidget(message)
        actions = QHBoxLayout()
        setup = QPushButton("Set Up MAFFT…")
        setup.clicked.connect(self._open_setup)
        choose = QPushButton("Choose Existing MAFFT…")
        choose.clicked.connect(self._choose_existing)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(setup)
        actions.addWidget(choose)
        actions.addStretch(1)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def _open_setup(self) -> None:
        if MafftSetupDialog(self, settings=self._settings).exec() == QDialog.DialogCode.Accepted:
            self.accept()

    def _choose_existing(self) -> None:
        info = choose_existing_mafft_executable(self, settings=self._settings)
        if info is not None and info.status is ToolStatus.AVAILABLE:
            self.accept()


def ensure_studio_mafft_available(parent=None, *, settings: QSettings | None = None) -> str | None:
    """Return a working MAFFT executable, or let the user cancel setup."""

    info = mafft_info_for_executable_path(None, settings=settings)
    if info.status is ToolStatus.AVAILABLE:
        return resolve_studio_mafft_executable(settings)
    if MafftNotFoundDialog(parent, settings=settings).exec() != QDialog.DialogCode.Accepted:
        return None
    refreshed = mafft_info_for_executable_path(None, settings=settings)
    if refreshed.status is not ToolStatus.AVAILABLE:
        return None
    return resolve_studio_mafft_executable(settings)
