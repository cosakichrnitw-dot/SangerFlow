"""Executable entry point for the independent SangerFlow-Studio prototype."""

from __future__ import annotations

import argparse
import sys

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from app.main_window import MainWindow
from controllers.project_controller import ProjectController


def build_application() -> tuple[QApplication, MainWindow]:
    application = QApplication.instance() or QApplication(sys.argv)
    state = AppState()
    controller = ProjectController(state)
    return application, MainWindow(state, controller)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch SangerFlow-Studio")
    parser.add_argument("--smoke-test", action="store_true")
    arguments = parser.parse_args(argv)
    application, window = build_application()
    if arguments.smoke_test:
        window.show()
        application.processEvents()
        window.close()
        application.quit()
        return 0
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
