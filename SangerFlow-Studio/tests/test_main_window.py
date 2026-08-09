"""Offscreen smoke checks for the Studio window composition."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtGui import QAction
from app.main import build_application
from views.project_view import ProjectView


class MainWindowTests(unittest.TestCase):
    def test_main_window_has_resizable_three_pane_shell(self) -> None:
        application, window = build_application()
        window.show()
        application.processEvents()

        self.assertEqual(window.windowTitle(), "SangerFlow-Studio")
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["File", "Project", "Tools", "Help"],
        )
        self.assertIn(
            "Open Project Bundle...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Welcome",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Dev: Start Chromatogram Paint Profile",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Dev: Stop Chromatogram Paint Profile",
            [action.text() for action in window.findChildren(QAction)],
        )
        project_view = window.centralWidget()
        self.assertIsInstance(project_view, ProjectView)
        self.assertEqual(project_view.count(), 3)
        self.assertEqual(project_view.widget(1).count(), 2)
        self.assertEqual(project_view.widget(0).topLevelItem(0).text(0), "No project open")
        self.assertGreater(sum(project_view.sizes()), 0)
        project_view.setSizes([180, 980, 220])
        application.processEvents()
        self.assertGreater(project_view.sizes()[1], project_view.sizes()[0])
        self.assertGreater(project_view.sizes()[1], project_view.sizes()[2])

        window.close()
