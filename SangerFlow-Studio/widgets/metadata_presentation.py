"""Bounded, read-only presentation helpers for immutable Studio metadata."""

from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout, QWidget


_MAX_SCALAR_PREVIEW = 180


def source_filepaths(metadata: object) -> tuple[str, ...]:
    """Return source file paths without changing the underlying metadata."""

    if not isinstance(metadata, Mapping):
        return ()
    value = metadata.get("source_filepaths")
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(str(path) for path in value)


def metadata_summary(metadata: object) -> str:
    """Return a layout-safe metadata summary.

    Long source paths and arbitrary collection reprs remain available in the
    model but are represented by a bounded summary in normal inspector/viewer
    layouts so they cannot dictate a workspace's preferred width.
    """

    if not metadata:
        return "-"
    if not isinstance(metadata, Mapping):
        return _bounded_scalar(metadata)
    values: list[str] = []
    for key, value in metadata.items():
        if key == "source_filepaths" and isinstance(value, (tuple, list)):
            values.append(f"{key}={len(value)} files")
        elif isinstance(value, Mapping):
            values.append(f"{key}={len(value)} fields")
        elif isinstance(value, (tuple, list, set, frozenset)):
            values.append(f"{key}={len(value)} values")
        else:
            values.append(f"{key}={_bounded_scalar(value)}")
    return "; ".join(values)


def show_source_filepaths_dialog(parent: QWidget, paths: tuple[str, ...]) -> QDialog:
    """Show every source path in a bounded, selectable, scrollable dialog."""

    dialog = QDialog(parent)
    dialog.setWindowTitle("Source files")
    dialog.setMinimumSize(440, 260)
    dialog.resize(720, 420)
    layout = QVBoxLayout(dialog)
    label = QLabel(f"{len(paths)} files")
    layout.addWidget(label)
    values = QPlainTextEdit(dialog)
    values.setReadOnly(True)
    values.setPlainText("\n".join(paths))
    values.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(values, 1)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
    buttons.rejected.connect(dialog.reject)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    dialog.exec()
    return dialog


def _bounded_scalar(value: object) -> str:
    text = str(value)
    if len(text) <= _MAX_SCALAR_PREVIEW:
        return text
    return f"{text[:_MAX_SCALAR_PREVIEW - 1]}…"
