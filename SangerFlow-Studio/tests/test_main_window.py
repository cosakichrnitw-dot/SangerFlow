"""Offscreen smoke checks for the Studio window composition."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QPushButton, QToolBar, QToolButton
from app.main import build_application
from core.project import Project
from views.project_view import ProjectView


class MainWindowTests(unittest.TestCase):
    def test_main_window_has_resizable_three_pane_shell(self) -> None:
        application, window = build_application()
        window.show()
        application.processEvents()

        self.assertEqual(window.windowTitle(), "SangerFlow-Studio")
        self.assertEqual(
            [action.text() for action in window.menuBar().actions()],
            ["File", "Edit", "View", "Dataset", "Metadata", "Align", "Identify", "Export", "Project", "Tools", "Help"],
        )
        self.assertIn(
            "New Project...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Open Project...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Open AB1 Folder...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Open AB1 File...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Open Sequence File...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Save Project",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Save Project As...",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Close Project",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIn(
            "Exit",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertIsNotNone(window.findChild(QAction, "workflowToolbarBack"))

    def test_workflow_toolbar_is_restored_on_active_viewer_transition(self) -> None:
        application, window = build_application()
        window.show()
        application.processEvents()
        toolbar = window.findChild(QToolBar, "mainToolbar")
        self.assertIsNotNone(toolbar)

        # The permanent strip is MainWindow-owned.  An old viewer path that
        # accidentally hides it cannot make the workflow unreachable after a
        # normal active-viewer transition.
        toolbar.hide()
        window._state.set_active_viewer(object())
        application.processEvents()
        self.assertTrue(toolbar.isVisible())
        window.close()
        self.assertNotIn(
            "Dev: Start Chromatogram Paint Profile",
            [action.text() for action in window.findChildren(QAction)],
        )
        self.assertNotIn(
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

    def test_window_title_reflects_project_and_dirty_state(self) -> None:
        application, window = build_application()
        project = Project.create("project-1", "Central Java")

        window._state.set_project(project)
        application.processEvents()
        self.assertEqual(window.windowTitle(), "SangerFlow-Studio — Central Java")

        window._state.mark_dirty()
        application.processEvents()
        self.assertEqual(window.windowTitle(), "SangerFlow-Studio — Central Java *")

        window._state.mark_clean()
        application.processEvents()
        self.assertEqual(window.windowTitle(), "SangerFlow-Studio — Central Java")

        window.close()

    def test_project_save_actions_use_standard_shortcuts(self) -> None:
        _application, window = build_application()
        self.assertEqual(window._save_project_action.shortcut(), QKeySequence(QKeySequence.StandardKey.Save))
        self.assertEqual(window._save_project_as_action.shortcut(), QKeySequence(QKeySequence.StandardKey.SaveAs))
        self.assertEqual(window._select_all_action.shortcut(), QKeySequence(QKeySequence.StandardKey.SelectAll))
        window.close()

    def test_main_window_close_cancels_summary_refresh_and_state_callbacks(self) -> None:
        application, window = build_application()
        state = window._state
        state.set_project(Project.create("first", "First"))

        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        state.set_project(Project.create("second", "Second"))
        application.processEvents()

    def test_view_menu_hides_panels_and_focus_mode_restores_them(self) -> None:
        application, window = build_application()
        window.show()
        application.processEvents()
        explorer = next(action for action in window.findChildren(QAction) if action.text() == "Project Explorer")
        inspector = next(action for action in window.findChildren(QAction) if action.text() == "Inspector / Quality Panel")
        focus = next(action for action in window.findChildren(QAction) if action.text() == "Focus Mode")

        explorer.setChecked(False)
        self.assertFalse(window._project_view.project_explorer_visible)
        explorer.setChecked(True)
        self.assertTrue(window._project_view.project_explorer_visible)
        focus.setChecked(True)
        self.assertFalse(window._project_view.project_explorer_visible)
        self.assertFalse(window._project_view.inspector_visible)
        focus.setChecked(False)
        self.assertTrue(window._project_view.project_explorer_visible)
        self.assertTrue(window._project_view.inspector_visible)
        self.assertTrue(inspector.isChecked())
        window.close()

    def test_project_explorer_shared_toggle_remains_available_when_explorer_is_hidden(self) -> None:
        application, window = build_application()
        window.show()
        application.processEvents()
        explorer_action = next(
            action for action in window.findChildren(QAction) if action.text() == "Project Explorer"
        )
        toolbar = window.findChild(QToolBar, "mainToolbar")
        self.assertIsNotNone(toolbar)
        self.assertNotIn(explorer_action, toolbar.actions())
        toggle = window._project_view.widget(0).findChild(
            QToolButton, "projectExplorerVisibilityButton"
        )
        self.assertIsNotNone(toggle)
        self.assertEqual(explorer_action.shortcut().toString(), "Ctrl+Alt+P")

        # View menu QAction remains the stable Explorer visibility control.
        explorer_action.setChecked(False)
        self.assertFalse(window._project_view.project_explorer_visible)
        explorer = window._project_view.widget(0)
        self.assertTrue(explorer._content.isHidden())
        self.assertFalse(explorer._search.isVisible())
        self.assertTrue(toggle.isVisible())
        self.assertTrue(explorer._rail.isVisible())
        self.assertLessEqual(window._project_view.sizes()[0], 32)
        explorer_action.trigger()
        self.assertTrue(window._project_view.project_explorer_visible)
        self.assertFalse(explorer._content.isHidden())
        self.assertTrue(explorer._search.isVisible())
        self.assertFalse(explorer._rail.isVisible())
        self.assertIs(toggle.parentWidget(), explorer._content)

        # Explorer visibility has a single source of truth: the shared action
        # in the View menu and MainWindow toolbar.  The panel has no duplicate
        # local collapse button that can disappear with the panel itself.
        self.assertFalse(
            any(
                button.text() == "‹"
                for button in window._project_view.widget(0).findChildren(QPushButton)
            )
        )

        focus = next(action for action in window.findChildren(QAction) if action.text() == "Focus Mode")
        focus.setChecked(True)
        self.assertFalse(window._project_view.project_explorer_visible)
        focus.setChecked(False)
        self.assertTrue(window._project_view.project_explorer_visible)

        # The shared toggle remains valid across Project close/new state.
        window._state.set_project(Project.create("first", "First"))
        window._controller.close_project()
        window._state.set_project(Project.create("second", "Second"))
        explorer_action.setChecked(False)
        explorer_action.trigger()
        self.assertTrue(window._project_view.project_explorer_visible)
        window.close()
