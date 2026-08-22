"""Checks for viewer action toolbar routing."""

from __future__ import annotations

import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.action_manager import ActionManager, _toolbar_icon
from app.app_state import AppState
from app.icon_registry import action_icon
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

    def test_stale_viewer_action_cannot_run_after_active_viewer_changes(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        provider = _ActionProvider()
        viewer = _Viewer(provider)
        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()
        stale_action = manager.action("viewer.test")
        self.assertIsNotNone(stale_action)

        # Rebuilds are intentionally deferred until the triggering toolbar
        # event has returned to Qt.  Once committed, a visually stale QAction
        # must not call its old viewer callback.
        manager.update_for_active_viewer(viewer)
        self.application.processEvents()
        stale_action.trigger()

        self.assertFalse(provider.called)

    def test_rapid_active_viewer_changes_commit_only_the_final_action_set(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        first_provider = _ActionProvider()
        second_provider = _ActionProvider()
        first = _Viewer(first_provider)
        second = _Viewer(second_provider)
        second._viewer_id = "viewer-2"

        manager.attach_toolbar(toolbar)
        state.set_active_viewer(first)
        state.set_active_viewer(second)
        state.set_active_viewer(first)
        self.assertTrue(manager.toolbar_update_pending)
        self.application.processEvents()

        action = manager.action("viewer.test")
        self.assertIsNotNone(action)
        action.trigger()
        self.assertTrue(first_provider.called)
        self.assertFalse(second_provider.called)
        self.assertEqual(manager.action_ids(), ("viewer.test",))

    def test_viewer_actions_do_not_add_toolbar_buttons_and_menu_metadata_is_preserved(self) -> None:
        class Provider:
            def actions_for(self, _viewer: object) -> tuple[ViewerAction, ...]:
                return (
                    ViewerAction("primary", "Primary", lambda: None, toolbar=True, priority=10, menu_group="Dataset"),
                    ViewerAction("rename", "Rename", lambda: None, menu_group="Edit", context_scope="row"),
                    ViewerAction("export", "Export FASTA", lambda: None, toolbar_group="Export", menu_group="Export"),
                )

        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        viewer = _Viewer(Provider())
        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()

        self.assertNotIn("Primary", [action.text() for action in toolbar.actions()])
        self.assertIn("Export", [action.text() for action in toolbar.actions()])
        self.assertNotIn("Rename", [action.text() for action in toolbar.actions()])
        self.assertEqual(tuple(action.text() for action in manager.actions_for_menu_group("Edit")), ("Rename",))
        self.assertEqual(manager.action("rename").property("sangerflow_context_scope"), "row")
        self.assertEqual(
            [action.text() for action in manager._fixed_menus["export"].actions()],
            ["Export FASTA"],
        )

    def test_fixed_workflow_toolbar_order_and_missing_svg_fallback(self) -> None:
        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        manager.attach_toolbar(toolbar)

        labels = [action.text() for action in toolbar.actions() if action.text()]
        self.assertEqual(
            labels[:7],
            ["Import", "Export", "Chromatogram", "Sequence Editor", "Consensus", "Align", "BLAST"],
        )
        self.assertEqual(manager._fixed_actions["back"].text(), "")
        self.assertEqual(manager._fixed_actions["undo"].text(), "")
        self.assertEqual(manager._fixed_actions["redo"].text(), "")
        self.assertEqual(manager._fixed_actions["undo"].toolTip(), "Undo")
        self.assertFalse(manager._fixed_actions["undo"].isEnabled())
        self.assertFalse(manager._fixed_actions["redo"].isEnabled())
        self.assertTrue(
            Path(__file__).resolve().parents[1].joinpath("resources", "icons", "back.svg").is_file()
        )
        self.assertFalse(_toolbar_icon("back").isNull())
        with patch("app.icon_registry.application_resource_path", return_value=Path("/missing/icon.svg")):
            self.assertTrue(_toolbar_icon("missing").isNull())

    def test_semantic_viewer_actions_resolve_replaceable_icons(self) -> None:
        self.assertFalse(action_icon("dataset.run_blast").isNull())
        self.assertFalse(action_icon("dataset.import_sample_metadata").isNull())
        self.assertFalse(action_icon("alignment.delete_selected_rows").isNull())
        self.assertTrue(action_icon("viewer.unknown_action").isNull())

    def test_alignment_edit_actions_are_classified_under_edit_not_align(self) -> None:
        self.assertEqual(ActionManager._default_menu_group("alignment.set_selection_a"), "Edit")
        self.assertEqual(ActionManager._default_menu_group("alignment.exclude_columns"), "Edit")
        self.assertEqual(ActionManager._default_menu_group("alignment.review_chromatograms"), "Align")

    def test_fixed_chromatogram_button_routes_to_alignment_evidence_action(self) -> None:
        class EvidenceProvider:
            def __init__(self) -> None:
                self.called = False

            def actions_for(self, _viewer: object) -> tuple[ViewerAction, ...]:
                return (
                    ViewerAction(
                        "alignment.review_chromatograms",
                        "Review Alignment Chromatograms",
                        self._call,
                        menu_group="Align",
                    ),
                )

            def _call(self) -> None:
                self.called = True

        state = AppState()
        manager = ActionManager(state)
        toolbar = QToolBar()
        provider = EvidenceProvider()
        viewer = _Viewer(provider)
        manager.attach_toolbar(toolbar)
        state.set_active_viewer(viewer)
        self.application.processEvents()

        button = manager._fixed_actions["chromatogram"]
        self.assertTrue(button.isEnabled())
        button.trigger()
        self.assertTrue(provider.called)
