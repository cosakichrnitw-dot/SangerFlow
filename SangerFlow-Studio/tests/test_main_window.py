"""Offscreen smoke checks for the Studio window composition."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QMessageBox, QPushButton, QToolBar, QToolButton
from app.main import build_application
from core.project import Project
from views.project_view import ProjectView
from widgets.viewers import BaseViewer


class _CancelCloseViewer(BaseViewer):
    """A dirty-editor stand-in whose modal prompt was answered Cancel."""

    def __init__(self) -> None:
        super().__init__(
            viewer_id="unsaved-editor",
            viewer_title="Unsaved Editor",
            viewer_kind="test",
            source_object_id="test-source",
        )
        self.allow_close = False
        self.close_calls = 0

    def close_viewer(self) -> bool:
        self.close_calls += 1
        return self.allow_close


class _SavingCloseViewer(_CancelCloseViewer):
    """Represents an Editor whose close-time Save created a new revision."""

    def __init__(self, state) -> None:
        super().__init__()
        self._viewer_id = "saving-editor"
        self._state = state

    def close_viewer(self) -> bool:
        self._state.mark_dirty()
        return True


class _TransactionalCloseViewer(BaseViewer):
    """Test double for a dirty Editor with split prepare/commit close hooks."""

    def __init__(self, viewer_id: str, intent: str | None, state) -> None:
        super().__init__(
            viewer_id=viewer_id,
            viewer_title=viewer_id,
            viewer_kind="test",
            source_object_id=viewer_id,
        )
        self.intent = intent
        self._state = state
        self.dirty = True
        self.prepare_calls = 0
        self.commit_calls = 0

    @property
    def is_dirty(self) -> bool:
        return self.dirty

    def prepare_close(self) -> str | None:
        self.prepare_calls += 1
        return self.intent

    def commit_close(self, intent: object) -> bool:
        self.commit_calls += 1
        if intent == "save":
            self._state.mark_dirty()
        self.dirty = False
        return True


class MainWindowTests(unittest.TestCase):
    @staticmethod
    def _open_transactional_viewers(window, *viewers: _TransactionalCloseViewer) -> None:
        for viewer in viewers:
            window._project_view.tab_manager.open_viewer(
                viewer,
                resource_key=f"dataset:{viewer.viewer_id}",
            )

    def test_project_close_honors_save_discard_and_cancel(self) -> None:
        for answer, should_close in (
            (QMessageBox.StandardButton.Save, True),
            (QMessageBox.StandardButton.Discard, True),
            (QMessageBox.StandardButton.Cancel, False),
        ):
            with self.subTest(answer=answer):
                _application, window = build_application()
                window._state.set_project(Project.create("project", "Project"), dirty=True)
                with patch(
                    "app.main_window.QMessageBox.warning",
                    return_value=answer,
                ), patch.object(window, "_save_project", return_value=True) as save:
                    window._close_project()

                self.assertEqual(window._state.current_project is None, should_close)
                self.assertEqual(save.called, answer == QMessageBox.StandardButton.Save)
                if not should_close:
                    window._state.mark_clean()
                window.close()

    def test_application_quit_honors_save_discard_and_cancel(self) -> None:
        for answer, should_close in (
            (QMessageBox.StandardButton.Save, True),
            (QMessageBox.StandardButton.Discard, True),
            (QMessageBox.StandardButton.Cancel, False),
        ):
            with self.subTest(answer=answer):
                application, window = build_application()
                window._state.set_project(Project.create("project", "Project"), dirty=True)
                event = QCloseEvent()
                with patch(
                    "app.main_window.QMessageBox.warning",
                    return_value=answer,
                ), patch.object(window, "_save_project", return_value=True) as save:
                    window.closeEvent(event)
                application.processEvents()

                self.assertEqual(event.isAccepted(), should_close)
                self.assertEqual(window._state.current_project is None, should_close)
                self.assertEqual(save.called, answer == QMessageBox.StandardButton.Save)
                if not should_close:
                    window._state.mark_clean()
                window.close()

    def test_application_quit_respects_editor_cancel_and_keeps_project_open(self) -> None:
        application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        viewer = _CancelCloseViewer()
        window._project_view.tab_manager.open_viewer(
            viewer,
            resource_key="dataset:unsaved",
        )

        event = QCloseEvent()
        window.closeEvent(event)
        application.processEvents()

        self.assertFalse(event.isAccepted())
        self.assertIsNotNone(window._state.current_project)
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("unsaved-editor",))

        # Avoid leaving a real Qt top-level widget open while preserving the
        # production assertion above: only the explicit later close may pass.
        viewer.allow_close = True
        window.close()

    def test_project_close_confirms_project_save_after_editor_save_creates_revision(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=True)
        viewer = _SavingCloseViewer(window._state)
        window._project_view.tab_manager.open_viewer(
            viewer,
            resource_key="dataset:saving",
        )
        with patch(
            "app.main_window.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Save,
        ), patch.object(window, "_save_project", return_value=True) as save:
            window._close_project()

        self.assertEqual(save.call_count, 1)
        self.assertIsNone(window._state.current_project)
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ())
        window.close()

    def test_project_and_quit_cancel_do_not_begin_partial_editor_close(self) -> None:
        for via_quit in (False, True):
            with self.subTest(via_quit=via_quit):
                application, window = build_application()
                window._state.set_project(Project.create("project", "Project"), dirty=True)
                viewer = _CancelCloseViewer()
                window._project_view.tab_manager.open_viewer(
                    viewer,
                    resource_key="dataset:unsaved",
                )
                with patch(
                    "app.main_window.QMessageBox.warning",
                    return_value=QMessageBox.StandardButton.Cancel,
                ):
                    if via_quit:
                        event = QCloseEvent()
                        window.closeEvent(event)
                        application.processEvents()
                        self.assertFalse(event.isAccepted())
                    else:
                        window._close_project()

                self.assertEqual(viewer.close_calls, 0)
                self.assertIsNotNone(window._state.current_project)
                self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("unsaved-editor",))
                window._state.mark_clean()
                viewer.allow_close = True
                window.close()

    def test_project_close_is_all_or_nothing_when_later_editor_cancels(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        first = _TransactionalCloseViewer("editor-a", "discard", window._state)
        second = _TransactionalCloseViewer("editor-b", None, window._state)
        self._open_transactional_viewers(window, first, second)

        window._close_project()

        self.assertIsNotNone(window._state.current_project)
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("editor-a", "editor-b"))
        self.assertTrue(first.dirty)
        self.assertTrue(second.dirty)
        self.assertEqual(first.commit_calls, 0)
        self.assertEqual(second.commit_calls, 0)
        first.intent = second.intent = "discard"
        window.close()

    def test_project_close_does_not_save_early_when_later_editor_cancels(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=True)
        first = _TransactionalCloseViewer("editor-a", "save", window._state)
        second = _TransactionalCloseViewer("editor-b", None, window._state)
        self._open_transactional_viewers(window, first, second)

        with patch(
            "app.main_window.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Save,
        ), patch.object(window, "_save_project", return_value=True) as save_project:
            window._close_project()

        self.assertIsNotNone(window._state.current_project)
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("editor-a", "editor-b"))
        self.assertTrue(first.dirty)
        self.assertEqual(first.commit_calls, 0)
        save_project.assert_not_called()
        first.intent = second.intent = "discard"
        window._state.mark_clean()
        window.close()

    def test_project_close_commits_after_every_editor_confirms(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        first = _TransactionalCloseViewer("editor-a", "save", window._state)
        second = _TransactionalCloseViewer("editor-b", "discard", window._state)
        self._open_transactional_viewers(window, first, second)

        with patch(
            "app.main_window.QMessageBox.warning",
            return_value=QMessageBox.StandardButton.Save,
        ), patch.object(window, "_save_project", return_value=True) as save_project:
            window._close_project()

        self.assertEqual(first.commit_calls, 1)
        self.assertEqual(second.commit_calls, 1)
        self.assertTrue(save_project.called)
        self.assertIsNone(window._state.current_project)
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ())
        window.close()

    def test_project_close_keeps_clean_tabs_when_dirty_editor_cancels(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        clean = _TransactionalCloseViewer("clean-editor", "close", window._state)
        clean.dirty = False
        dirty = _TransactionalCloseViewer("dirty-editor", None, window._state)
        self._open_transactional_viewers(window, clean, dirty)

        window._close_project()

        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("clean-editor", "dirty-editor"))
        self.assertEqual(clean.commit_calls, 0)
        self.assertTrue(dirty.dirty)
        clean.intent = dirty.intent = "discard"
        window.close()

    def test_project_close_keeps_all_three_editors_when_last_cancels(self) -> None:
        _application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        first = _TransactionalCloseViewer("editor-a", "save", window._state)
        second = _TransactionalCloseViewer("editor-b", "discard", window._state)
        third = _TransactionalCloseViewer("editor-c", None, window._state)
        self._open_transactional_viewers(window, first, second, third)

        window._close_project()

        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("editor-a", "editor-b", "editor-c"))
        self.assertTrue(first.dirty)
        self.assertTrue(second.dirty)
        self.assertTrue(third.dirty)
        self.assertEqual((first.commit_calls, second.commit_calls, third.commit_calls), (0, 0, 0))
        first.intent = second.intent = third.intent = "discard"
        window.close()

    def test_application_quit_uses_the_same_all_or_nothing_close_transaction(self) -> None:
        application, window = build_application()
        window._state.set_project(Project.create("project", "Project"), dirty=False)
        first = _TransactionalCloseViewer("editor-a", "discard", window._state)
        second = _TransactionalCloseViewer("editor-b", None, window._state)
        self._open_transactional_viewers(window, first, second)

        event = QCloseEvent()
        window.closeEvent(event)
        application.processEvents()

        self.assertFalse(event.isAccepted())
        self.assertEqual(window._project_view.tab_manager.viewer_ids(), ("editor-a", "editor-b"))
        self.assertTrue(first.dirty)
        self.assertEqual(first.commit_calls, 0)
        first.intent = second.intent = "discard"
        window.close()

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
