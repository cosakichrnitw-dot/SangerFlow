"""Checks for viewer action toolbar routing."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.action_manager import ActionManager
from app.app_state import AppState
from PySide6.QtWidgets import QApplication, QToolBar
from widgets.viewers import BaseViewer
from widgets.viewers.viewer_actions import ViewerAction


class _ActionProvider:
    def __init__(self) -> None:
        self.called = False

    def actions_for(self, _viewer: object) -> tuple[ViewerAction, ...]:
        return (
            ViewerAction(
                action_id="viewer.test",
                label="Test Action",
                callback=self._call,
            ),
        )

    def _call(self) -> None:
        self.called = True


class _Viewer(BaseViewer):
    def __init__(self, provider: _ActionProvider) -> None:
        super().__init__(viewer_id="viewer-1", viewer_title="Viewer 1")
        self._provider = provider

    @property
    def action_providers(self) -> tuple[object, ...]:
        return (self._provider,)


class ActionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.application = QApplication.instance() or QApplication([])

    def test_active_viewer_actions_are_added_to_toolbar(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        provider = _ActionProvider()
        viewer = _Viewer(provider)

        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()

        action = manager.action("viewer.test")
        self.assertIsNotNone(action)
        self.assertEqual(action.text(), "Test Action")

        action.trigger()
        self.assertTrue(provider.called)
