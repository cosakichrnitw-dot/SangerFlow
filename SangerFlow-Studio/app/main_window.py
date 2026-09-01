"""PySide6 main window composition for the independent Studio prototype."""

from PySide6.QtCore import QEvent, QTimer, Slot, Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QMessageBox, QStyle

from app.app_state import AppState
from app.drop_import import (
    ExternalDropError,
    ExternalDropKind,
    classify_external_drop_paths,
)
from app.icon_registry import studio_icon
from app.selection import StudioSelection
from controllers.project_controller import ProjectController
from core.sequence_dataset import SequenceDataset
from views.project_view import ProjectView
from widgets.project_dialogs import NewProjectDialog
from widgets.tool_settings_dialog import ToolSettingsDialog


class MainWindow(QMainWindow):
    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._state = state
        self._controller = controller
        self.setWindowTitle("SangerFlow-Studio")
        self.resize(1400, 860)
        self._project_view = ProjectView(state, controller)
        self._project_view.project_explorer_visibility_changed.connect(
            self._sync_project_explorer_action
        )
        self._project_view.dock_manager.attach_main_window(self)
        self.setCentralWidget(self._project_view)
        self.setAcceptDrops(True)
        # Keep the overlay inside the centre tab workspace.  A direct child of
        # ProjectView would become a fourth QSplitter pane and alter layout.
        self._drop_target = self._project_view.widget(1)
        self._drop_overlay = QLabel("Drop files to import", self._drop_target)
        self._drop_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._drop_overlay.setStyleSheet(
            "background: rgba(44, 116, 180, 38); border: 2px dashed #2c74b4; "
            "border-radius: 8px; color: #174a73; font-size: 18px; font-weight: 600;"
        )
        self._drop_overlay.hide()
        self._drop_target.installEventFilter(self)
        # Context menus mirror transient toolbar actions.  Use the same
        # deferred boundary as ActionManager so a menu/action is never removed
        # while Cocoa is still dispatching its triggering toolbar event.
        self._context_refresh_timer = QTimer(self)
        self._context_refresh_timer.setSingleShot(True)
        self._context_refresh_timer.setInterval(0)
        self._context_refresh_timer.timeout.connect(self._apply_context_menu_refresh)
        # QToolBar owns a toggleViewAction whose checked state can be applied
        # by Qt after a tab/current-viewer transition.  Restore only after the
        # same queued turn used by ActionManager; doing it synchronously alone
        # is too early on macOS.
        self._toolbar_visibility_timer = QTimer(self)
        self._toolbar_visibility_timer.setSingleShot(True)
        self._toolbar_visibility_timer.setInterval(0)
        self._toolbar_visibility_timer.timeout.connect(self._ensure_workflow_toolbar)
        self._build_menu_bar()
        self._build_toolbar()
        # AppState can outlive child widgets during test and application
        # teardown.  Use QObject-bound slots, never receiver-less lambdas that
        # retain a deleted QMainWindow wrapper.
        state.project_changed.connect(self._on_project_changed)
        state.dirty_changed.connect(self._on_dirty_changed)
        state.bundle_path_changed.connect(self._on_bundle_path_changed)
        self._update_window_title()
        self.statusBar().showMessage("Ready")

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        self._file_menu = file_menu
        new_project_action = QAction(studio_icon("new"), "New Project...", self)
        new_project_action.triggered.connect(self._new_project)
        file_menu.addAction(new_project_action)
        open_bundle_action = QAction(studio_icon("open_project"), "Open Project...", self)
        open_bundle_action.triggered.connect(self._choose_project_bundle)
        file_menu.addAction(open_bundle_action)
        file_menu.addSeparator()
        open_ab1_folder_action = QAction(studio_icon("folder"), "Open AB1 Folder...", self)
        open_ab1_folder_action.triggered.connect(self._choose_ab1_folder)
        file_menu.addAction(open_ab1_folder_action)
        open_ab1_file_action = QAction(studio_icon("file"), "Open AB1 File...", self)
        open_ab1_file_action.triggered.connect(self._choose_ab1_file)
        file_menu.addAction(open_ab1_file_action)
        open_sequence_file_action = QAction(studio_icon("file"), "Open Sequence File...", self)
        open_sequence_file_action.triggered.connect(self._choose_sequence_file)
        file_menu.addAction(open_sequence_file_action)
        file_menu.addSeparator()
        self._save_project_action = QAction(studio_icon("save"), "Save Project", self)
        self._save_project_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_project_action.triggered.connect(self._save_project)
        file_menu.addAction(self._save_project_action)
        self._save_project_as_action = QAction(studio_icon("save"), "Save Project As...", self)
        self._save_project_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
        self._save_project_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(self._save_project_as_action)
        close_project_action = QAction(studio_icon("close"), "Close Project", self)
        close_project_action.triggered.connect(self._close_project)
        file_menu.addAction(close_project_action)
        file_menu.addSeparator()
        exit_action = QAction(studio_icon("close"), "Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        self._edit_menu = self.menuBar().addMenu("Edit")
        self._select_all_action = QAction("Select All", self)
        self._select_all_action.setShortcut(QKeySequence.StandardKey.SelectAll)
        self._select_all_action.triggered.connect(self._select_all_in_active_grid)
        self._view_menu = self.menuBar().addMenu("View")
        self._dataset_menu = self.menuBar().addMenu("Dataset")
        self._metadata_menu = self.menuBar().addMenu("Metadata")
        self._align_menu = self.menuBar().addMenu("Align")
        self._identify_menu = self.menuBar().addMenu("Identify")
        self._export_menu = self.menuBar().addMenu("Export")
        self._project_menu = self.menuBar().addMenu("Project")
        self._project_records_action = QAction(studio_icon("project_records"), "Project Records", self)
        self._project_records_action.setEnabled(self._state.current_project is not None)
        self._project_records_action.setToolTip("Browse and combine records across Project datasets")
        self._project_records_action.triggered.connect(self._open_project_records)
        self._project_menu.addAction(self._project_records_action)
        tools_menu = self.menuBar().addMenu("Tools")
        tool_settings_action = QAction(studio_icon("settings"), "Tool Settings…", self)
        tool_settings_action.triggered.connect(self._open_tool_settings)
        tools_menu.addAction(tool_settings_action)
        self._view_menu.addSeparator()
        self._explorer_visibility_action = QAction("Project Explorer", self, checkable=True)
        self._explorer_visibility_action.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft)
        )
        self._explorer_visibility_action.setToolTip("Show or hide Project Explorer")
        self._explorer_visibility_action.setShortcut(QKeySequence("Ctrl+Alt+P"))
        self._explorer_visibility_action.setChecked(True)
        self._explorer_visibility_action.toggled.connect(
            self._project_view.set_project_explorer_visible
        )
        self._project_view.set_project_explorer_visibility_action(
            self._explorer_visibility_action
        )
        self._view_menu.addAction(self._explorer_visibility_action)
        self._inspector_visibility_action = QAction("Inspector / Quality Panel", self, checkable=True)
        self._inspector_visibility_action.setChecked(True)
        self._inspector_visibility_action.toggled.connect(
            self._project_view.set_inspector_visible
        )
        self._view_menu.addAction(self._inspector_visibility_action)
        self._focus_mode_action = QAction("Focus Mode", self, checkable=True)
        self._focus_mode_action.toggled.connect(self._set_focus_mode)
        self._view_menu.addAction(self._focus_mode_action)
        self._help_menu = self.menuBar().addMenu("Help")

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        # This is a permanent MainWindow control surface, not a viewer-owned
        # toolbar.  Viewer transitions may only update its action bindings.
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self._workflow_toolbar = toolbar
        action_manager = self._project_view.action_manager
        action_manager.configure_workflow_toolbar(
            back=self._go_back,
            import_ab1_folder=self._choose_ab1_folder,
            import_ab1_file=self._choose_ab1_file,
            import_sequence_file=self._choose_sequence_file,
        )
        action_manager.attach_toolbar(toolbar)
        action_manager.sequence_dataset_dropped_on_align.connect(
            self._align_dropped_sequence_dataset
        )
        self._project_view.action_manager.actions_rebuilt.connect(
            self._schedule_context_menu_refresh
        )
        self._project_view.action_manager.actions_rebuilt.connect(
            self._schedule_workflow_toolbar_restore
        )
        self._state.active_viewer_changed.connect(self._on_active_viewer_changed)

    def _go_back(self) -> None:
        """Move to the preceding workspace tab without changing project state."""

        tabs = self._project_view.widget(1)
        index = getattr(tabs, "currentIndex", lambda: 0)()
        if index > 0:
            tabs.setCurrentIndex(index - 1)

    @Slot(str, str)
    def _align_dropped_sequence_dataset(self, project_id: str, dataset_id: str) -> None:
        """Select a dropped Dataset, then route it through the normal Align action."""

        project = self._state.current_project
        if project is None or getattr(project, "project_id", None) != project_id:
            self.statusBar().showMessage("The dropped Dataset is no longer in the active Project.", 5000)
            return
        try:
            entry = project.get_entry(dataset_id)
        except (KeyError, ValueError):
            self.statusBar().showMessage("The dropped Dataset is no longer available.", 5000)
            return
        dataset = getattr(entry, "dataset", None)
        is_current = getattr(project, "is_current_revision", lambda _id: False)
        if not isinstance(dataset, SequenceDataset) or not is_current(dataset_id):
            self.statusBar().showMessage("Only a current Sequence Dataset can be aligned.", 5000)
            return
        # This is exactly the normal Explorer selection/open route.  The
        # ActionManager then invokes the Dataset Viewer's existing Align
        # descriptor on its next safe deferred update.
        self._controller.select_item(StudioSelection.dataset(entry), open_viewer=True)
        self._project_view.action_manager.request_dataset_action(
            "dataset.align_sequences", dataset_id
        )

    @Slot(object)
    def _on_project_changed(self, _project: object) -> None:
        self._update_window_title()
        self._schedule_context_menu_refresh()

    @Slot(bool)
    def _on_dirty_changed(self, _dirty: bool) -> None:
        self._update_window_title()

    @Slot(object)
    def _on_bundle_path_changed(self, _path: object) -> None:
        self._update_window_title()

    @Slot(object)
    def _on_active_viewer_changed(self, _viewer: object) -> None:
        self._ensure_workflow_toolbar()
        self._schedule_workflow_toolbar_restore()
        self._schedule_context_menu_refresh()

    def _schedule_workflow_toolbar_restore(self) -> None:
        """Run after deferred viewer-action updates and native tab dispatch."""

        if not self._toolbar_visibility_timer.isActive():
            self._toolbar_visibility_timer.start()

    def _ensure_workflow_toolbar(self) -> None:
        """Restore the permanent strip if an old viewer path detached it.

        The toolbar must never become part of a tab/viewer lifecycle.  This is
        deliberately a MainWindow-only guard; it does not recreate actions or
        alter ActionManager's deferred generation protection.
        """

        toolbar = getattr(self, "_workflow_toolbar", None)
        if toolbar is None:
            return
        if self.toolBarArea(toolbar) == Qt.ToolBarArea.NoToolBarArea:
            self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        # Calling QWidget.show alone is insufficient if QMainWindow's
        # toggleViewAction remains unchecked; its later state propagation can
        # hide the toolbar again after this method returns.
        toggle_action = toolbar.toggleViewAction()
        if not toggle_action.isChecked():
            toggle_action.setChecked(True)
        if not toolbar.isVisible():
            toolbar.show()

    def workflow_toolbar_state(self) -> dict[str, object]:
        """Deterministic test/diagnostic snapshot without adding a Dev UI."""

        toolbar = getattr(self, "_workflow_toolbar", None)
        if toolbar is None:
            return {"exists": False}
        return {
            "exists": True,
            "visible": toolbar.isVisible(),
            "hidden": toolbar.isHidden(),
            "toggle_checked": toolbar.toggleViewAction().isChecked(),
            "area": int(self.toolBarArea(toolbar)),
            "parent_is_main_window": toolbar.parent() is self,
        }

    def _schedule_context_menu_refresh(self) -> None:
        """Refresh menu proxies only after the deferred toolbar update."""

        if not self._context_refresh_timer.isActive():
            self._context_refresh_timer.start()

    def _apply_context_menu_refresh(self) -> None:
        action_manager = self._project_view.action_manager
        if action_manager.toolbar_update_pending:
            # ActionManager owns the first queued turn.  Reschedule rather
            # than clearing menu/action presentation during a toolbar click.
            self._context_refresh_timer.start()
            return
        self._refresh_context_menus()

    def _refresh_context_menus(self) -> None:
        """Mirror existing active-viewer actions into compact macOS menus."""

        for menu in (
            self._edit_menu,
            self._dataset_menu,
            self._metadata_menu,
            self._align_menu,
            self._identify_menu,
            self._export_menu,
            self._project_menu,
        ):
            menu.clear()
        self._edit_menu.addAction(self._select_all_action)
        self._edit_menu.addSeparator()
        self._project_records_action.setEnabled(self._state.current_project is not None)
        self._project_menu.addAction(self._project_records_action)
        self._project_menu.addSeparator()
        actions = self._project_view.action_manager
        groups = {
            "Edit": self._edit_menu,
            "Dataset": self._dataset_menu,
            "Metadata": self._metadata_menu,
            "Align": self._align_menu,
            "Identify": self._identify_menu,
            "Export": self._export_menu,
            "Project": self._project_menu,
        }
        for group, menu in groups.items():
            for action in actions.actions_for_menu_group(group):
                proxy = QAction(action.icon(), action.text(), menu)
                proxy.setEnabled(action.isEnabled())
                proxy.triggered.connect(action.trigger)
                menu.addAction(proxy)

    def _select_all_in_active_grid(self) -> None:
        viewer = self._state.active_viewer
        grid = getattr(viewer, "_grid", None)
        select_rectangle = getattr(grid, "select_rectangle", None)
        rows = getattr(grid, "rows", ())
        columns = getattr(grid, "column_count", 0)
        if callable(select_rectangle) and rows and columns:
            select_rectangle(0, 0, len(rows) - 1, int(columns) - 1, mode="all")

    def _set_focus_mode(self, enabled: bool) -> None:
        if enabled:
            self._focus_previous_visibility = (
                self._explorer_visibility_action.isChecked(),
                self._inspector_visibility_action.isChecked(),
            )
            self._explorer_visibility_action.setChecked(False)
            self._inspector_visibility_action.setChecked(False)
            return
        explorer, inspector = getattr(self, "_focus_previous_visibility", (True, True))
        self._explorer_visibility_action.setChecked(explorer)
        self._inspector_visibility_action.setChecked(inspector)

    def _sync_project_explorer_action(self, visible: bool) -> None:
        if self._explorer_visibility_action.isChecked() != visible:
            self._explorer_visibility_action.setChecked(visible)

    def _choose_project_bundle(self) -> None:
        if not self._confirm_discard_or_save():
            return
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            "",
            "SangerFlow Bundle (*.sangerflow);;All Files (*)",
        )
        if not filepath:
            return
        self._open_project_bundle_path(filepath)

    def _open_project_bundle_path(self, filepath: str) -> None:
        """Open a selected bundle after either a dialog or an external drop."""

        try:
            loaded_bundle = self._controller.open_project_bundle(filepath)
        except Exception as error:
            QMessageBox.critical(self, "Could not open Project Bundle", str(error))
            return
        warnings = self._controller.last_warnings
        if warnings:
            QMessageBox.warning(
                self,
                "Project opened with warnings",
                "\n".join(warnings),
            )
        self.statusBar().showMessage(
            f"Opened project: {loaded_bundle.project.name}",
            5000,
        )

    def _open_project_records(self) -> None:
        try:
            self._controller.open_project_records_viewer()
        except Exception as error:
            QMessageBox.warning(self, "Project Records", str(error))

    def _open_tool_settings(self) -> None:
        ToolSettingsDialog(self).exec()

    def _choose_ab1_folder(self) -> None:
        folderpath = QFileDialog.getExistingDirectory(
            self,
            "Open AB1 Folder",
            "",
        )
        if not folderpath:
            return
        handling = self._choose_ab1_source_handling()
        if handling is None:
            return
        self._open_ab1_folder_path(folderpath, handling)

    def _open_ab1_folder_path(self, folderpath: str, handling: str) -> None:
        try:
            tab_name = self._controller.open_ab1_folder(
                folderpath,
                source_file_handling=handling,
            )
        except Exception as error:
            QMessageBox.critical(self, "Could not open AB1 folder", str(error))
            return
        if tab_name:
            self.statusBar().showMessage(f"Opened AB1 folder: {folderpath}", 5000)

    def _choose_ab1_file(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open AB1 File",
            "",
            "AB1 Files (*.ab1 *.abi);;All Files (*)",
        )
        if not filepath:
            return
        handling = self._choose_ab1_source_handling()
        if handling is None:
            return
        self._open_ab1_file_paths((filepath,), handling)

    def _open_ab1_file_paths(self, filepaths: tuple[str, ...], handling: str) -> None:
        try:
            if len(filepaths) == 1:
                tab_name = self._controller.open_ab1_file(
                    filepaths[0],
                    source_file_handling=handling,
                )
            else:
                tab_name = self._controller.open_ab1_files(
                    filepaths,
                    source_file_handling=handling,
                )
        except Exception as error:
            title = "Could not open AB1 files" if len(filepaths) > 1 else "Could not open AB1 file"
            QMessageBox.critical(self, title, str(error))
            return
        if tab_name:
            label = filepaths[0] if len(filepaths) == 1 else f"{len(filepaths)} AB1 files"
            noun = "file" if len(filepaths) == 1 else "files"
            self.statusBar().showMessage(f"Opened AB1 {noun}: {label}", 5000)

    def _choose_sequence_file(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Sequence File",
            "",
            "Sequence Files (*.fas *.fasta *.fa *.fna);;FASTA Files (*.fas *.fasta *.fa *.fna);;All Files (*)",
        )
        if not filepath:
            return
        self._open_sequence_file_path(filepath)

    def _open_sequence_file_path(self, filepath: str) -> None:
        try:
            tab_name = self._controller.open_sequence_file(filepath)
        except Exception as error:
            QMessageBox.critical(self, "Could not open sequence file", str(error))
            return
        if tab_name:
            self.statusBar().showMessage(f"Opened sequence file: {filepath}", 5000)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt override
        try:
            self._drop_request_from_event(event)
        except ExternalDropError as error:
            self._set_drop_feedback(False)
            self.statusBar().showMessage(str(error), 4000)
            event.ignore()
            return
        self._set_drop_feedback(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        try:
            self._drop_request_from_event(event)
        except ExternalDropError:
            self._set_drop_feedback(False)
            event.ignore()
            return
        self._set_drop_feedback(True)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._set_drop_feedback(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._set_drop_feedback(False)
        try:
            request = self._drop_request_from_event(event)
            self._route_external_drop(request)
        except ExternalDropError as error:
            QMessageBox.warning(self, "Unsupported Import", str(error))
            event.ignore()
            return
        event.acceptProposedAction()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        self._position_drop_overlay()

    def eventFilter(self, watched, event):  # noqa: N802 - Qt override
        if watched is self._drop_target and event.type() == QEvent.Type.Resize:
            self._position_drop_overlay()
        return super().eventFilter(watched, event)

    def _drop_request_from_event(self, event):
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            raise ExternalDropError("Drop local files or folders from Finder to import them.")
        urls = tuple(mime_data.urls())
        if not urls or any(not url.isLocalFile() for url in urls):
            raise ExternalDropError("Only local Finder files and folders can be imported.")
        return classify_external_drop_paths(tuple(url.toLocalFile() for url in urls))

    def _route_external_drop(self, request) -> None:
        """Route a classified drop through the same Controller APIs as File."""

        if request.kind is ExternalDropKind.PROJECT_BUNDLE:
            if self._confirm_discard_or_save():
                self._open_project_bundle_path(str(request.paths[0]))
            return
        if request.kind is ExternalDropKind.SEQUENCE_FILE:
            self._open_sequence_file_path(str(request.paths[0]))
            return
        handling = self._choose_ab1_source_handling()
        if handling is None:
            return
        if request.kind is ExternalDropKind.AB1_FOLDER:
            self._open_ab1_folder_path(str(request.paths[0]), handling)
            return
        if request.kind is ExternalDropKind.AB1_FILES:
            self._open_ab1_file_paths(tuple(str(path) for path in request.paths), handling)
            return
        raise ExternalDropError("Unsupported import request.")

    def _set_drop_feedback(self, visible: bool) -> None:
        self._position_drop_overlay()
        self._drop_overlay.setVisible(visible)
        if visible:
            self._drop_overlay.raise_()
            self.statusBar().showMessage("Drop files to import", 0)

    def _position_drop_overlay(self) -> None:
        if hasattr(self, "_drop_overlay"):
            self._drop_overlay.setGeometry(self._drop_target.rect().adjusted(12, 12, -12, -12))

    def _save_project(self) -> bool:
        if self._state.current_bundle_path is None:
            return self._save_project_as()
        try:
            filepath = self._controller.save_project_bundle(self._state.current_bundle_path)
        except Exception as error:
            QMessageBox.critical(self, "Could not save Project", str(error))
            return False
        self.statusBar().showMessage(f"Saved project: {filepath}", 5000)
        return True

    def _new_project(self) -> None:
        if not self._confirm_discard_or_save():
            return
        dialog = NewProjectDialog(self)
        if not dialog.exec():
            return
        try:
            project = self._controller.create_project(
                dialog.project_name,
                location=dialog.location,
                create_workspace=dialog.create_workspace,
            )
        except Exception as error:
            QMessageBox.critical(self, "Could not create Project", str(error))
            return
        self._controller.activate_tab("Project Summary")
        self.statusBar().showMessage(f"Created project: {project.name}", 5000)

    def _close_project(self) -> None:
        if not self._state.current_project:
            return
        close_transaction = self._prepare_project_close_transaction()
        if close_transaction is None:
            return
        if not self._commit_project_close_transaction(close_transaction):
            return
        self._controller.finalize_project_close()
        self.statusBar().showMessage("Project closed", 5000)

    def _save_project_as(self) -> bool:
        if self._state.current_project is None:
            QMessageBox.information(self, "No Project", "No Project is open.")
            return False
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Project Bundle",
            self._suggested_bundle_path(),
            "SangerFlow Bundle (*.sangerflow);;All Files (*)",
        )
        if not filepath:
            return False
        if not filepath.lower().endswith(".sangerflow"):
            filepath = f"{filepath}.sangerflow"
        try:
            saved_path = self._controller.save_project_bundle(filepath)
        except Exception as error:
            QMessageBox.critical(self, "Could not save Project", str(error))
            return False
        self.statusBar().showMessage(f"Saved project: {saved_path}", 5000)
        return True

    def _suggested_bundle_path(self) -> str:
        if self._state.current_bundle_path:
            return self._state.current_bundle_path
        project = self._state.current_project
        name = getattr(project, "project_id", None) or getattr(project, "name", "project")
        safe_name = "".join(
            character if str(character).isalnum() or character in {"-", "_"} else "_"
            for character in str(name)
        ).strip("_") or "project"
        return f"{safe_name}.sangerflow"

    def _choose_ab1_source_handling(self) -> str | None:
        """Ask whether raw AB1 files remain external or are copied to Raw_Data."""

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Source File Handling")
        dialog.setText("How should this Project handle the selected AB1 files?")
        reference = dialog.addButton("Reference original files", QMessageBox.ButtonRole.AcceptRole)
        copy = dialog.addButton("Copy into Project Workspace / Raw_Data", QMessageBox.ButtonRole.ActionRole)
        cancel = dialog.addButton(QMessageBox.StandardButton.Cancel)
        if self._controller.current_workspace() is None:
            copy.setEnabled(False)
            dialog.setInformativeText("Copy mode becomes available after saving or creating a Project Workspace.")
        dialog.exec()
        clicked = dialog.clickedButton()
        if clicked is reference:
            return "reference"
        if clicked is copy:
            return "copy"
        if clicked is cancel:
            return None
        return None

    def _project_close_decision(self, *, force_prompt: bool = False) -> str:
        """Return a Project-close intent without saving, closing, or discarding."""

        if not force_prompt and not self._state.is_dirty:
            return "clean"
        message = "The current Project has unsaved changes."
        if force_prompt and not self._state.is_dirty:
            message = (
                "Saving pending editor edits will create a new Project revision. "
                "Save the Project before closing?"
            )
        response = QMessageBox.warning(
            self,
            "Unsaved Project Changes",
            message,
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if response == QMessageBox.StandardButton.Save:
            return "save"
        if response == QMessageBox.StandardButton.Discard:
            return "discard"
        return "cancel"

    def _confirm_discard_or_save(self) -> bool:
        """Compatibility wrapper for navigation paths that do not close tabs."""

        decision = self._project_close_decision()
        if decision == "cancel":
            return False
        return decision != "save" or self._save_project()

    def _prepare_project_close_transaction(self) -> tuple[str, object] | None:
        """Collect every close intent before any editor or tab can mutate.

        A late Cancel therefore leaves all working copies and Project state
        exactly as they were at the start of Project Close/application quit.
        """

        project_decision = self._project_close_decision()
        if project_decision == "cancel":
            return None
        close_plan = self._controller.prepare_project_close()
        if close_plan is None:
            return None
        if (
            project_decision == "clean"
            and bool(getattr(close_plan, "requires_project_persistence", False))
        ):
            project_decision = self._project_close_decision(force_prompt=True)
            if project_decision == "cancel":
                return None
        return project_decision, close_plan

    def _commit_project_close_transaction(self, transaction: tuple[str, object]) -> bool:
        """Commit an already-approved close transaction in safe order."""

        project_decision, close_plan = transaction
        if not self._controller.commit_project_close_changes(close_plan):
            return False
        # Editor saves can create immutable revisions.  Persist them before
        # tabs are removed, so a failed bundle save leaves visible working
        # context rather than silently closing the Project.
        if project_decision == "save" and not self._save_project():
            return False
        return self._controller.finalize_project_close_tabs(close_plan)

    def _update_window_title(self) -> None:
        project = self._state.current_project
        if project is None:
            title = "SangerFlow-Studio"
        else:
            title = f"SangerFlow-Studio — {getattr(project, 'name', 'Project')}"
        if self._state.is_dirty:
            title += " *"
        self.setWindowTitle(title)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        close_transaction = self._prepare_project_close_transaction()
        if close_transaction is None:
            event.ignore()
            return
        if not self._commit_project_close_transaction(close_transaction):
            event.ignore()
            return
        self._controller.finalize_project_close()
        event.accept()
