"""Single-purpose input dialog for non-destructive record batch renaming."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class BatchRenameDialog(QDialog):
    """Collect a rename transform and expose only a validated mapping.

    This dialog never accesses a Dataset, Project, or controller.  The caller
    owns immutable revision creation after the dialog has been accepted.
    """

    def __init__(
        self,
        record_ids: tuple[str, ...] | list[str],
        parent: QWidget | None = None,
        *,
        existing_record_ids: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Rename Records")
        self._record_ids = tuple(record_ids)
        self._unselected_record_ids = set(existing_record_ids or ()) - set(self._record_ids)
        self._button_group = QButtonGroup(self)
        self.prefix_suffix_mode = QRadioButton("Prefix / Suffix")
        self.find_replace_mode = QRadioButton("Find / Replace")
        self.advanced_mode = QRadioButton("Advanced")
        self.prefix_suffix_mode.setChecked(True)
        for button in (self.prefix_suffix_mode, self.find_replace_mode, self.advanced_mode):
            self._button_group.addButton(button)
            button.toggled.connect(self._update_preview)
        self.prefix_edit = QLineEdit()
        self.suffix_edit = QLineEdit()
        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        for edit in (self.prefix_edit, self.suffix_edit, self.find_edit, self.replace_edit):
            edit.textChanged.connect(self._update_preview)
        form = QFormLayout()
        form.addRow("Prefix:", self.prefix_edit)
        form.addRow("Suffix:", self.suffix_edit)
        form.addRow("Find:", self.find_edit)
        form.addRow("Replace:", self.replace_edit)

        self._preview = QTableWidget(len(self._record_ids), 2)
        self._preview.setHorizontalHeaderLabels(("Current ID", "New ID"))
        self._preview.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._preview.verticalHeader().setVisible(False)
        self._preview.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._summary = QLabel()
        self._validation = QLabel()
        self._validation.setWordWrap(True)
        self._buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply)
        self._apply_button = self._buttons.button(QDialogButtonBox.StandardButton.Apply)
        self._buttons.rejected.connect(self.reject)
        # Apply has Qt's ApplyRole rather than AcceptRole, so it does not emit
        # QDialogButtonBox.accepted.  Bind the actual button to the modal
        # completion path used by DatasetViewer.dialog.exec().
        self._apply_button.clicked.connect(self.accept)
        self._accepted_once = False
        modes = QHBoxLayout()
        modes.addWidget(self.prefix_suffix_mode)
        modes.addWidget(self.find_replace_mode)
        modes.addWidget(self.advanced_mode)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Mode:"))
        layout.addLayout(modes)
        layout.addLayout(form)
        layout.addWidget(self._preview)
        layout.addWidget(self._summary)
        layout.addWidget(self._validation)
        layout.addWidget(self._buttons)
        self._update_preview()

    @property
    def rename_by_id(self) -> dict[str, str]:
        return {old: self._new_identifier(old) for old in self._record_ids}

    @property
    def is_valid_transform(self) -> bool:
        return not self._validation_errors()[0]

    def _new_identifier(self, record_id: str) -> str:
        if self.find_replace_mode.isChecked():
            find = self.find_edit.text()
            # Blank Find historically means no replacement rather than a
            # surprising insertion between every character.
            renamed = record_id.replace(find, self.replace_edit.text()) if find else record_id
            return renamed
        if self.advanced_mode.isChecked():
            find = self.find_edit.text()
            renamed = record_id.replace(find, self.replace_edit.text()) if find else record_id
            return f"{self.prefix_edit.text()}{renamed}{self.suffix_edit.text()}"
        return f"{self.prefix_edit.text()}{record_id}{self.suffix_edit.text()}"

    def _validation_errors(self) -> tuple[tuple[str, ...], int]:
        mapping = self.rename_by_id
        errors: list[str] = []
        empty = sorted(old for old, new in mapping.items() if not new.strip())
        if empty:
            errors.append("Resulting record IDs cannot be empty.")
        duplicates = sorted({new for new in mapping.values() if list(mapping.values()).count(new) > 1})
        if duplicates:
            errors.append("Duplicate resulting IDs: " + ", ".join(duplicates))
        collisions = sorted({new for new in mapping.values() if new in self._unselected_record_ids})
        if collisions:
            errors.append("Resulting IDs already used by unselected records: " + ", ".join(collisions))
        changed = sum(old != new for old, new in mapping.items())
        if not changed:
            errors.append("The transform does not change any selected record ID.")
        return tuple(errors), changed

    def _update_preview(self) -> None:
        mapping = self.rename_by_id
        for row, old in enumerate(self._record_ids):
            for column, value in enumerate((old, mapping[old])):
                item = self._preview.item(row, column)
                if item is None:
                    item = QTableWidgetItem()
                    self._preview.setItem(row, column, item)
                item.setText(value)
        errors, changed = self._validation_errors()
        self._summary.setText(f"{changed} of {len(self._record_ids)} records will be renamed")
        self._validation.setText("; ".join(errors) if errors else "0 conflicts")
        self._validation.setStyleSheet("color: #b00020;" if errors else "color: #276738;")
        self._apply_button.setEnabled(not errors)

    def accept(self) -> None:  # noqa: D401 - Qt override
        errors, _changed = self._validation_errors()
        if errors:
            # This also covers programmatic calls after a transform became
            # invalid; the reason must be visible rather than a silent return.
            self._validation.setText("; ".join(errors))
            self._validation.setStyleSheet("color: #b00020;")
            self._apply_button.setEnabled(False)
            return
        if self._accepted_once:
            return
        self._accepted_once = True
        self._apply_button.setEnabled(False)
        super().accept()
