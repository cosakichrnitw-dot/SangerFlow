"""Offscreen tests for machine-local MAFFT configuration."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(studio_root.parent))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from services.application_settings import configured_mafft_executable
from widgets.tool_settings_dialog import ToolSettingsDialog


class ToolSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_accept_stores_machine_local_mafft_path_not_project_data(self) -> None:
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / "settings.ini"), QSettings.Format.IniFormat)
            dialog = ToolSettingsDialog(settings=settings)
            dialog._mafft_path.setText(r"C:\Tools\mafft.bat")
            dialog.accept()
            self.assertEqual(configured_mafft_executable(settings), r"C:\Tools\mafft.bat")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
