"""Runtime guard for QWidget mutations in the Studio GUI thread."""

from __future__ import annotations

import logging

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication


_LOGGER = logging.getLogger(__name__)


def assert_main_gui_thread(operation: str) -> None:
    """Fail fast when a QWidget-facing operation is called off the GUI thread.

    There is no QApplication during a few non-GUI unit tests, in which case the
    assertion is intentionally a no-op.  Once an application exists, every
    protected GUI entry point must execute on its owning QApplication thread.
    """

    application = QApplication.instance()
    if application is None:
        return
    current_thread = QThread.currentThread()
    main_thread = application.thread()
    if current_thread != main_thread:
        _LOGGER.critical(
            "GUI thread violation at %s: current=%r main=%r",
            operation,
            current_thread,
            main_thread,
        )
        raise AssertionError(
            f"{operation} must run on the QApplication main thread; "
            f"current={current_thread!r}, main={main_thread!r}"
        )
    _LOGGER.debug("GUI thread verified at %s", operation)
