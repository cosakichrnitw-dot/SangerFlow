"""Minimal viewer action management for SangerFlow-Studio."""

from __future__ import annotations

from functools import partial

from PySide6.QtCore import QObject, QTimer, Signal, QSize, Qt
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import QMenu, QToolBar

from app.app_state import AppState
from app.gui_thread import assert_main_gui_thread
from app.icon_registry import action_icon, studio_icon


class ActionManager(QObject):
    """Expose active-viewer actions through a toolbar."""

    actions_rebuilt = Signal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._toolbar: QToolBar | None = None
        self._export_toolbar_action: QAction | None = None
        self._export_menu: QMenu | None = None
        self._group_toolbar_actions: list[QAction] = []
        self._group_menus: list[QMenu] = []
        self._actions: dict[str, QAction] = {}
        self._action_generation = 0
        self._requested_generation = 0
        self._requested_viewer: object | None = None
        self._toolbar_callbacks: dict[str, object] = {}
        self._fixed_actions: dict[str, QAction] = {}
        self._fixed_menus: dict[str, QMenu] = {}
        self._fixed_bindings: dict[str, tuple[object, object, int] | None] = {}
        # A toolbar button can still be handling a mouse/hover event when an
        # action opens a replacement Viewer.  Defer removal of its presentation
        # widget until that native event has returned to Qt/Cocoa.
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(0)
        self._rebuild_timer.timeout.connect(self._apply_requested_viewer)
        state.active_viewer_changed.connect(self.update_for_active_viewer)
        # Some workflow affordances depend on a selected cell/record (for
        # example, opening chromatogram evidence from Sequence Editor).  The
        # fixed toolbar remains stable; only its safe deferred binding updates.
        state.selection_changed.connect(self._refresh_for_selection_context)

    def _refresh_for_selection_context(self, _selection: object) -> None:
        self.update_for_active_viewer(self._state.active_viewer)

    def configure_workflow_toolbar(self, **callbacks: object) -> None:
        """Set global callbacks before the permanent workflow strip is built."""

        self._toolbar_callbacks = dict(callbacks)

    def attach_toolbar(self, toolbar: QToolBar) -> None:
        # The manager and its transient QAction/QMenu objects have exactly the
        # same lifetime as the toolbar that presents them.  A parentless
        # manager can otherwise outlive a test/window toolbar long enough for
        # Qt to destruct an action from two ownership paths.
        if self.parent() is None:
            self.setParent(toolbar)
        self._toolbar = toolbar
        self._install_fixed_workflow_actions()
        self.update_for_active_viewer(self._state.active_viewer)

    def _install_fixed_workflow_actions(self) -> None:
        """Install a stable Geneious-style workflow strip exactly once."""

        if self._fixed_actions or self._toolbar is None:
            return
        self._toolbar.setIconSize(QSize(28, 28))
        self._toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self._toolbar.setMinimumHeight(62)
        self._add_fixed_action("back", "Back", "back", self._toolbar_callbacks.get("back"))
        self._add_fixed_action("undo", "Undo", "undo", None, enabled=False)
        self._add_fixed_action("redo", "Redo", "redo", None, enabled=False)
        self._fixed_actions["undo"].triggered.connect(partial(self._invoke_fixed_binding, "undo"))
        self._fixed_actions["redo"].triggered.connect(partial(self._invoke_fixed_binding, "redo"))
        self._toolbar.addSeparator()
        self._add_fixed_menu("import", "Import", "import")
        self._add_fixed_menu("export", "Export", "export")
        self._toolbar.addSeparator()
        self._add_fixed_action("chromatogram", "Chromatogram", "chromatogram", None, enabled=False)
        self._add_fixed_action("sequence_editor", "Sequence Editor", "sequence_editor", None, enabled=False)
        self._fixed_actions["chromatogram"].triggered.connect(
            partial(self._invoke_fixed_binding, "chromatogram")
        )
        self._fixed_actions["sequence_editor"].triggered.connect(
            partial(self._invoke_fixed_binding, "sequence_editor")
        )
        self._add_fixed_menu("consensus", "Consensus", "consensus")
        self._add_fixed_menu("align", "Align", "align")
        self._add_fixed_menu("blast", "BLAST", "blast")
        for key in ("export", "consensus", "align", "blast"):
            self._fixed_actions[key].setEnabled(False)

    def _add_fixed_action(self, key: str, label: str, icon_name: str, callback: object, *, enabled: bool = True) -> None:
        assert self._toolbar is not None
        # Back/Undo/Redo are compact utilities, not workflow labels.  Their
        # object name and tooltip retain an accessible, testable identity.
        toolbar_label = "" if key in {"back", "undo", "redo"} else label
        action = QAction(studio_icon(icon_name), toolbar_label, self)
        action.setObjectName(f"workflowToolbar{key.title().replace('_', '')}")
        action.setToolTip(label)
        action.setEnabled(enabled)
        if callable(callback):
            action.triggered.connect(callback)
        self._fixed_actions[key] = action
        self._toolbar.addAction(action)

    def _add_fixed_menu(self, key: str, label: str, icon_name: str) -> None:
        assert self._toolbar is not None
        menu = QMenu(self._toolbar)
        action = QAction(studio_icon(icon_name), label, self)
        action.setToolTip(f"{label} workflow")
        action.triggered.connect(partial(self._show_action_menu, action, menu))
        self._fixed_actions[key] = action
        self._fixed_menus[key] = menu
        self._toolbar.addAction(action)

    def update_for_active_viewer(self, viewer: object | None = None) -> None:
        """Request a safe, coalesced toolbar update for ``viewer``.

        This intentionally does not mutate QToolBar from an active QAction's
        triggered call stack.  The latest requested Viewer wins when the owned
        timer runs on the next event-loop turn.
        """

        assert_main_gui_thread("ActionManager.update_for_active_viewer/QToolBar")
        if self._toolbar is None:
            return
        self._requested_generation += 1
        self._requested_viewer = viewer
        if not self._rebuild_timer.isActive():
            self._rebuild_timer.start()

    @property
    def toolbar_update_pending(self) -> bool:
        """Whether a requested active-viewer toolbar update is still deferred."""

        return self._rebuild_timer.isActive()

    def _apply_requested_viewer(self) -> None:
        """Commit exactly the newest requested Viewer action set."""

        assert_main_gui_thread("ActionManager._apply_requested_viewer/QToolBar")
        if self._toolbar is None:
            return
        requested_generation = self._requested_generation
        viewer = self._requested_viewer
        # An active-viewer signal emitted after this callback was queued must
        # never be overwritten by an older rebuild request.
        if viewer is not self._state.active_viewer:
            self.update_for_active_viewer(self._state.active_viewer)
            return
        self._action_generation += 1
        generation = self._action_generation
        self._clear_viewer_actions()
        if viewer is None:
            self._clear_fixed_viewer_bindings()
            if requested_generation == self._requested_generation:
                self.actions_rebuilt.emit()
            return
        for provider in getattr(viewer, "action_providers", ()):
            for descriptor in provider.actions_for(viewer):
                # ActionManager owns transient actions.  QToolBar/QMenu only
                # present them; this avoids shared ownership during tab
                # teardown and deferred QAction destruction.
                action = QAction(action_icon(descriptor.action_id), descriptor.label, self)
                action.setEnabled(descriptor.enabled)
                action.setToolTip(descriptor.tooltip or descriptor.label)
                self._apply_standard_shortcut(action, descriptor.action_id)
                action.setProperty("sangerflow_menu_group", descriptor.menu_group or self._default_menu_group(descriptor.action_id))
                action.setProperty("sangerflow_context_scope", descriptor.context_scope or "")
                # QAction destruction is deferred by Qt.  Never let a queued
                # click from an action belonging to a no-longer-active tab
                # invoke that viewer's callback.
                action.triggered.connect(
                    partial(self._invoke_viewer_action, viewer, descriptor.callback, generation)
                )
                self._actions[descriptor.action_id] = action
        # ViewerAction instances are intentionally not added to QToolBar.
        # The fixed workflow strip below is their only toolbar presentation;
        # all remaining actions continue to be available from application and
        # context menus through the same descriptors and callbacks.
        self._refresh_fixed_workflow_actions(viewer, generation)
        if requested_generation == self._requested_generation:
            self.actions_rebuilt.emit()

    def _invoke_viewer_action(
        self,
        viewer: object,
        callback: object,
        generation: int,
        _checked: bool = False,
    ) -> None:
        """Run an action only while its originating viewer remains active."""

        if self._action_generation != generation or self._state.active_viewer is not viewer:
            return
        if callable(callback):
            callback()

    def _refresh_fixed_workflow_actions(self, viewer: object, generation: int) -> None:
        """Bind permanent workflow controls to the active viewer's actions."""

        self._populate_fixed_menu("import", ("dataset.import_sample_metadata",), global_import=True)
        self._bind_fixed_action("undo", self._first_action_ending(".undo"), viewer, generation)
        self._bind_fixed_action("redo", self._first_action_ending(".redo"), viewer, generation)
        self._bind_fixed_action(
            "chromatogram",
            self._first_action(
                (
                    "dataset.open_chromatogram_viewer",
                    "alignment.review_chromatograms",
                    "sequence_editor.review_evidence",
                )
            ),
            viewer,
            generation,
        )
        self._bind_fixed_action(
            "sequence_editor",
            self._first_action((
                "dataset.edit_sequences",
                "dataset.open_alignment_viewer",
                "chromatogram.open_sequence_editor",
            )),
            viewer,
            generation,
        )
        self._populate_fixed_menu(
            "consensus",
            ("chromatogram.build_consensus", "fr_consensus.review_selected", "fr_consensus.review_all", "single_consensus.create_dataset", "multiple_consensus.create_dataset", "consensus_review.create_dataset"),
            viewer=viewer,
            generation=generation,
        )
        self._populate_fixed_menu(
            "align",
            ("chromatogram.align", "sequence_editor.align", "dataset.open_alignment_viewer", "alignment.review_chromatograms"),
            viewer=viewer,
            generation=generation,
        )
        self._populate_fixed_menu(
            "blast",
            ("dataset.run_blast", "alignment.run_blast", "dataset.import_blast_xml"),
            viewer=viewer,
            generation=generation,
        )
        export_actions = tuple(self.actions_for_menu_group("Export"))
        self._populate_fixed_menu("export", (), viewer=viewer, generation=generation, actions=export_actions)

    def _clear_fixed_viewer_bindings(self) -> None:
        for key in ("undo", "redo", "chromatogram", "sequence_editor"):
            self._fixed_bindings[key] = None
            self._fixed_actions[key].setEnabled(False)
        for key in ("export", "consensus", "align", "blast"):
            self._fixed_menus[key].clear()
            self._fixed_actions[key].setEnabled(False)
        self._populate_fixed_menu("import", (), global_import=True)

    def _first_action(self, action_ids: tuple[str, ...]) -> QAction | None:
        return next((self._actions[action_id] for action_id in action_ids if action_id in self._actions), None)

    def _first_action_ending(self, suffix: str) -> QAction | None:
        return next((action for action_id, action in self._actions.items() if action_id.endswith(suffix)), None)

    def _bind_fixed_action(self, key: str, action: QAction | None, viewer: object, generation: int) -> None:
        fixed = self._fixed_actions[key]
        if action is None:
            self._fixed_bindings[key] = None
            fixed.setEnabled(False)
            fixed.setToolTip(
                {
                    "undo": "Undo is unavailable: there is no edit to undo.",
                    "redo": "Redo is unavailable: there is no edit to redo.",
                    "chromatogram": "No source chromatogram evidence is associated with this context.",
                    "sequence_editor": "No editable sequence dataset is available in this context.",
                }.get(key, fixed.toolTip())
            )
            return
        fixed.setEnabled(action.isEnabled())
        fixed.setToolTip(action.toolTip() or action.text())
        self._fixed_bindings[key] = (viewer, action.trigger, generation)

    def _invoke_fixed_binding(self, key: str, _checked: bool = False) -> None:
        binding = self._fixed_bindings.get(key)
        if binding is not None:
            self._invoke_viewer_action(*binding)

    def _populate_fixed_menu(
        self,
        key: str,
        action_ids: tuple[str, ...],
        *,
        viewer: object | None = None,
        generation: int | None = None,
        actions: tuple[QAction, ...] = (),
        global_import: bool = False,
    ) -> None:
        menu = self._fixed_menus[key]
        menu.clear()
        selected = actions or tuple(self._actions[action_id] for action_id in action_ids if action_id in self._actions)
        if global_import:
            for label, icon_name, callback_key in (
                ("Import AB1 Folder…", "folder", "import_ab1_folder"),
                ("Import AB1 File…", "file", "import_ab1_file"),
                ("Import Sequence File…", "file", "import_sequence_file"),
            ):
                action = menu.addAction(studio_icon(icon_name), label)
                callback = self._toolbar_callbacks.get(callback_key)
                if callable(callback):
                    action.triggered.connect(callback)
                else:
                    action.setEnabled(False)
            if selected:
                menu.addSeparator()
        for source in selected:
            proxy = menu.addAction(source.icon(), source.text())
            proxy.setEnabled(source.isEnabled())
            if viewer is not None and generation is not None:
                proxy.triggered.connect(partial(self._invoke_viewer_action, viewer, source.trigger, generation))
            else:
                proxy.triggered.connect(source.trigger)
        # A dropdown with only unavailable operations must not look runnable.
        # This is especially important for Export and context-sensitive
        # scientific workflows: an enabled toolbar control must have at least
        # one genuine receiver in the current Studio context.
        self._fixed_actions[key].setEnabled(
            any(action.isEnabled() for action in menu.actions())
        )

    @staticmethod
    def _default_menu_group(action_id: str) -> str:
        """Classify legacy descriptors until each provider supplies a group."""

        if ".export" in action_id or "export_" in action_id:
            return "Export"
        if "blast" in action_id or action_id.startswith("identification."):
            return "Identify"
        if "metadata" in action_id:
            return "Metadata"
        if any(token in action_id for token in ("undo", "redo", "copy", "paste", "rename", "hide", "delete", "set_selection", "exclude", "include")):
            return "Edit"
        if action_id.startswith("alignment.") or action_id.endswith(".align"):
            return "Align"
        return "Dataset"

    @staticmethod
    def _apply_standard_shortcut(action: QAction, action_id: str) -> None:
        if action_id.endswith(".copy_selection"):
            action.setShortcut(QKeySequence.StandardKey.Copy)
        elif action_id.endswith(".undo"):
            action.setShortcut(QKeySequence.StandardKey.Undo)
        elif action_id.endswith(".redo"):
            action.setShortcut(QKeySequence.StandardKey.Redo)

    def _add_action_menu(
        self, label: str, actions: list[QAction], *, track_group: bool = True
    ) -> tuple[QAction, QMenu]:
        assert self._toolbar is not None
        menu = QMenu(self._toolbar)
        for action in actions:
            menu.addAction(action)
        trigger = QAction(label, self)
        trigger.triggered.connect(partial(self._show_action_menu, trigger, menu))
        if track_group:
            self._group_menus.append(menu)
            self._group_toolbar_actions.append(trigger)
        self._toolbar.addAction(trigger)
        return trigger, menu

    def _show_action_menu(self, trigger: QAction, menu: QMenu, _checked: bool = False) -> None:
        """Open a compact toolbar dropdown without QWidgetAction ownership."""

        toolbar = self._toolbar
        if toolbar is None:
            return
        location = toolbar.mapToGlobal(toolbar.actionGeometry(trigger).bottomLeft())
        menu.exec(location)

    def _clear_viewer_actions(self) -> None:
        """Remove transient viewer actions using a symmetric Qt lifecycle."""

        assert self._toolbar is not None

        # The export menu references actions held in _actions.  Clear it before
        # queuing those actions for destruction, then destroy the QWidgetAction
        # which owns its tool button/default widget.
        if self._export_menu is not None:
            self._export_menu.clear()
            self._export_menu.deleteLater()
            self._export_menu = None
        export_toolbar_action = self._export_toolbar_action
        self._export_toolbar_action = None
        if export_toolbar_action is not None:
            self._toolbar.removeAction(export_toolbar_action)
            export_toolbar_action.deleteLater()

        for menu in self._group_menus:
            menu.clear()
            menu.deleteLater()
        self._group_menus.clear()
        for toolbar_action in self._group_toolbar_actions:
            self._toolbar.removeAction(toolbar_action)
            toolbar_action.deleteLater()
        self._group_toolbar_actions.clear()

        actions = tuple(self._actions.values())
        self._actions.clear()
        for action in actions:
            self._toolbar.removeAction(action)
            action.deleteLater()

    def action(self, action_id: str) -> QAction | None:
        return self._actions.get(action_id)

    def action_ids(self) -> tuple[str, ...]:
        return tuple(self._actions)

    def actions_for_menu_group(self, group: str) -> tuple[QAction, ...]:
        """Return current-viewer actions for a top-level application menu."""

        return tuple(
            action
            for action in self._actions.values()
            if action.property("sangerflow_menu_group") == group
        )


def _toolbar_icon(name: str) -> QIcon:
    """Backward-compatible name retained for existing toolbar tests."""

    return studio_icon(name)
