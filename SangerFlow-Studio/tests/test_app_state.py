"""Headless checks for the Studio state and controller boundary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

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

    def test_dirty_state_and_bundle_path_are_explicit_project_state(self) -> None:
        state = AppState()
        dirty_events: list[bool] = []
        path_events: list[object] = []
        state.dirty_changed.connect(dirty_events.append)
        state.bundle_path_changed.connect(path_events.append)

        project = object()
        state.set_project(project, bundle_path="/tmp/project.sangerflow")
        self.assertFalse(state.is_dirty)
        self.assertEqual(state.current_bundle_path, "/tmp/project.sangerflow")

        state.replace_project(project, dirty=True)
        self.assertTrue(state.is_dirty)
        state.mark_clean()
        state.set_bundle_path("/tmp/other.sangerflow")

        self.assertEqual(dirty_events, [True, False])
        self.assertEqual(path_events, ["/tmp/project.sangerflow", "/tmp/other.sangerflow"])
