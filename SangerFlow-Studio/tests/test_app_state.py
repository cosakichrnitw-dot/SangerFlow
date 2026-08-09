"""Headless checks for the Studio state and controller boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.app_state import AppState
from controllers.project_controller import ProjectController


class AppStateTests(unittest.TestCase):
    def test_controller_publishes_project_selection_and_active_tab(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        project = object()
        selection = {"kind": "dataset"}
        controller.open_project(project)
        controller.select_item(selection)
        controller.activate_tab("Project Summary")
        self.assertIs(state.project, project)
        self.assertEqual(state.selected_item, selection)
        self.assertEqual(state.active_tab, "Project Summary")
