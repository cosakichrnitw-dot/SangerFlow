"""PySide6 main window composition for the independent Studio prototype."""

import sys

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox

from app.app_state import AppState
from controllers.project_controller import ProjectController
from views.project_view import ProjectView


class MainWindow(QMainWindow):
    def __init__(self, state: AppState, controller: ProjectController) -> None:
        super().__init__()
        self._state = state
        self._controller = controller
        self.setWindowTitle("SangerFlow-Studio")
        self.resize(1400, 860)
        self._project_view = ProjectView(state, controller)
        self._project_view.dock_manager.attach_main_window(self)
        self.setCentralWidget(self._project_view)
        self._build_menu_bar()
        self._build_toolbar()
        self.statusBar().showMessage("Ready")

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        open_bundle_action = QAction("Open Project Bundle...", self)
        open_bundle_action.triggered.connect(self._choose_project_bundle)
        file_menu.addAction(open_bundle_action)
        open_ab1_folder_action = QAction("Open AB1 Folder...", self)
        open_ab1_folder_action.triggered.connect(self._choose_ab1_folder)
        file_menu.addAction(open_ab1_folder_action)
        self.menuBar().addMenu("Project")
        tools_menu = self.menuBar().addMenu("Tools")
        start_profile_action = QAction("Dev: Start Chromatogram Paint Profile", self)
        start_profile_action.triggered.connect(
            lambda _checked=False: self._start_chromatogram_paint_profile()
        )
        tools_menu.addAction(start_profile_action)
        stop_profile_action = QAction("Dev: Stop Chromatogram Paint Profile", self)
        stop_profile_action.triggered.connect(
            lambda _checked=False: self._stop_chromatogram_paint_profile()
        )
        tools_menu.addAction(stop_profile_action)
        self.menuBar().addMenu("Help")

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        welcome_action = QAction("Welcome", self)
        welcome_action.triggered.connect(lambda: self._controller.activate_tab("Welcome"))
        toolbar.addAction(welcome_action)
        self._project_view.action_manager.attach_toolbar(toolbar)

    def _choose_project_bundle(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project Bundle",
            "",
            "SangerFlow Bundle (*.sangerflow);;All Files (*)",
        )
        if not filepath:
            return
        try:
            loaded_bundle = self._controller.open_project_bundle(filepath)
        except Exception as error:
            QMessageBox.critical(self, "Could not open Project Bundle", str(error))
            return
        self.statusBar().showMessage(
            f"Opened project: {loaded_bundle.project.name}",
            5000,
        )

    def _choose_ab1_folder(self) -> None:
        folderpath = QFileDialog.getExistingDirectory(
            self,
            "Open AB1 Folder",
            "",
        )
        if not folderpath:
            return
        try:
            tab_name = self._controller.open_ab1_folder(folderpath)
        except Exception as error:
            QMessageBox.critical(self, "Could not open AB1 folder", str(error))
            return
        if tab_name:
            self.statusBar().showMessage(f"Opened AB1 folder: {folderpath}", 5000)

    def _start_chromatogram_paint_profile(self) -> None:
        viewer = self._state.active_viewer
        start = getattr(viewer, "start_paint_profile", None)
        if not callable(start):
            _emit_profile_menu_message(
                "[PROFILE] start requested, but active viewer is not a ChromatogramViewer."
            )
            self.statusBar().showMessage("Active viewer is not a ChromatogramViewer.", 5000)
            return
        start()

    def _stop_chromatogram_paint_profile(self) -> None:
        viewer = self._state.active_viewer
        stop = getattr(viewer, "stop_paint_profile", None)
        if not callable(stop):
            _emit_profile_menu_message(
                "[PROFILE] stop requested, but active viewer is not a ChromatogramViewer."
            )
            self.statusBar().showMessage("Active viewer is not a ChromatogramViewer.", 5000)
            return
        stop()


def _emit_profile_menu_message(text: str) -> None:
    print(text, flush=True)
    print(text, file=sys.stderr, flush=True)
