"""Offscreen tests for machine-local MAFFT configuration."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(studio_root.parent))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialog

from app.app_state import AppState
from controllers.project_controller import ProjectController
from core.tool_manager import ToolInfo, ToolStatus
from services.application_settings import (
    configured_mafft_executable,
    store_validated_mafft_executable,
)
from widgets.mafft_setup_dialog import (
    MafftSetupDialog,
    choose_existing_mafft_executable,
    ensure_studio_mafft_available,
)
from widgets.tool_settings_dialog import ToolSettingsDialog


class ToolSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_validated_path_is_stored_machine_locally(self) -> None:
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            available = ToolInfo(
                name="MAFFT", executable_path=r"C:\Tools\mafft.bat",
                version="v7", status=ToolStatus.AVAILABLE,
            )
            with patch("services.application_settings.detect_mafft", return_value=available):
                result = store_validated_mafft_executable(r"C:\Tools\mafft.bat", settings)
            self.assertIs(result, available)
            self.assertEqual(configured_mafft_executable(settings), r"C:\Tools\mafft.bat")

    def test_invalid_path_is_not_saved(self) -> None:
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            invalid = ToolInfo(name="MAFFT", status=ToolStatus.INVALID)
            with patch("services.application_settings.detect_mafft", return_value=invalid):
                result = store_validated_mafft_executable("/not/mafft", settings)
            self.assertIs(result, invalid)
            self.assertIsNone(configured_mafft_executable(settings))

    def test_choose_existing_path_validates_before_persisting(self) -> None:
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            available = ToolInfo(
                name="MAFFT", executable_path="/selected/mafft",
                version="v7", status=ToolStatus.AVAILABLE,
            )
            with (
                patch("widgets.mafft_setup_dialog.QFileDialog.getOpenFileName", return_value=("/selected/mafft", "")),
                patch("services.application_settings.detect_mafft", return_value=available),
            ):
                result = choose_existing_mafft_executable(settings=settings)
            self.assertIs(result, available)
            self.assertEqual(configured_mafft_executable(settings), "/selected/mafft")

    def test_tool_settings_reset_uses_automatic_detection(self) -> None:
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            settings.setValue("tools/mafft/executable_path", "/configured/mafft")
            dialog = ToolSettingsDialog(settings=settings)
            dialog._reset_automatic()
            self.assertIsNone(configured_mafft_executable(settings))

    def test_setup_choose_success_closes_guide(self) -> None:
        available = ToolInfo(
            name="MAFFT", executable_path="/opt/homebrew/bin/mafft",
            version="v7", status=ToolStatus.AVAILABLE,
        )
        dialog = MafftSetupDialog()
        with patch("widgets.mafft_setup_dialog.choose_existing_mafft_executable", return_value=available):
            dialog._choose_existing()
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_setup_check_again_accepts_when_mafft_becomes_available(self) -> None:
        available = ToolInfo(
            name="MAFFT", executable_path="/opt/homebrew/bin/mafft",
            version="v7", status=ToolStatus.AVAILABLE,
        )
        with patch("widgets.mafft_setup_dialog.mafft_info_for_executable_path", return_value=available):
            dialog = MafftSetupDialog()
            dialog._check_again()
        self.assertEqual(dialog.result(), dialog.DialogCode.Accepted)

    def test_ensure_missing_mafft_uses_setup_then_rechecks(self) -> None:
        missing = ToolInfo(name="MAFFT", status=ToolStatus.MISSING)
        available = ToolInfo(
            name="MAFFT", executable_path="/opt/homebrew/bin/mafft",
            version="v7", status=ToolStatus.AVAILABLE,
        )
        with (
            patch("widgets.mafft_setup_dialog.mafft_info_for_executable_path", side_effect=(missing, available)),
            patch("widgets.mafft_setup_dialog.MafftNotFoundDialog.exec", return_value=QDialog.DialogCode.Accepted),
            patch("widgets.mafft_setup_dialog.resolve_studio_mafft_executable", return_value="/opt/homebrew/bin/mafft"),
        ):
            self.assertEqual(ensure_studio_mafft_available(), "/opt/homebrew/bin/mafft")

    def test_chromatogram_alignment_missing_mafft_does_not_mutate_project(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        controller.configure_viewer_framework(
            viewer_registry=object(), viewer_context=object(), tab_manager=object()
        )
        viewer = SimpleNamespace(
            visible_read_views=(SimpleNamespace(read=object()),),
            source_dataset=None,
        )
        with patch("controllers.project_controller.ensure_studio_mafft_available", return_value=None) as setup:
            self.assertIsNone(controller.align_chromatogram_viewer(viewer))
        setup.assert_called_once_with(viewer)
        self.assertIsNone(state.project)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
