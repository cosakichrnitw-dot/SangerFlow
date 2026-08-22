"""Small, dynamic PopART export dialog for a SequenceDataset."""

from __future__ import annotations

from collections import Counter

from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QRadioButton, QTextEdit, QVBoxLayout,
)

from core.sequence_dataset import SequenceDataset
from export.popart_export import PopArtExportError, build_popart_rows, metadata_trait_fields


class PopArtExportDialog(QDialog):
    """Collect only PopART options that the exporter can represent safely."""

    def __init__(self, dataset: SequenceDataset, parent=None) -> None:
        super().__init__(parent)
        self._dataset = dataset
        self.setWindowTitle("Export for PopART")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Dataset: {dataset.name}\nRecords: {dataset.sequence_count}"))
        form = QFormLayout()
        self._trait_field = QComboBox()
        fields = metadata_trait_fields(dataset)
        self._trait_field.addItems(fields)
        form.addRow("Trait field", self._trait_field)
        layout.addLayout(form)
        self._appearance = QRadioButton("Dataset appearance order")
        self._alphabetical = QRadioButton("Alphabetical")
        self._custom = QRadioButton("Custom (comma-separated)")
        self._custom_order = QLineEdit()
        self._custom_order.setPlaceholderText("e.g. East, Central, West")
        self._appearance.setChecked(True)
        order_group = QButtonGroup(self)
        order_group.addButton(self._appearance)
        order_group.addButton(self._alphabetical)
        order_group.addButton(self._custom)
        layout.addWidget(self._appearance)
        layout.addWidget(self._alphabetical)
        layout.addWidget(self._custom)
        layout.addWidget(self._custom_order)
        self._include_missing = QRadioButton("Include missing values as unknown")
        self._exclude_missing = QRadioButton("Exclude records with missing values")
        self._include_missing.setChecked(True)
        missing_group = QButtonGroup(self)
        missing_group.addButton(self._include_missing)
        missing_group.addButton(self._exclude_missing)
        layout.addWidget(self._include_missing)
        layout.addWidget(self._exclude_missing)
        layout.addWidget(QLabel("Preview — category / count"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMaximumHeight(130)
        layout.addWidget(self._preview)
        self._trait_field.currentTextChanged.connect(self._refresh_preview)
        self._appearance.toggled.connect(self._refresh_preview)
        self._custom.toggled.connect(self._refresh_preview)
        self._custom_order.textChanged.connect(self._refresh_preview)
        self._include_missing.toggled.connect(self._refresh_preview)
        self._refresh_preview()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Export")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def export_options(self) -> tuple[str, tuple[str, ...] | None, str]:
        field = self._trait_field.currentText()
        if not field:
            raise PopArtExportError("this Dataset has no metadata fields to use as a trait")
        rows, categories, _ = build_popart_rows(
            self._dataset, trait_field=field,
            missing_values="include" if self._include_missing.isChecked() else "exclude",
        )
        del rows
        custom = tuple(value.strip() for value in self._custom_order.text().split(",") if value.strip())
        order = custom if self._custom.isChecked() else (tuple(sorted(categories)) if self._alphabetical.isChecked() else None)
        return field, order, (
            "include" if self._include_missing.isChecked() else "exclude"
        )

    def _refresh_preview(self, *_ignored) -> None:
        try:
            field, order, missing = self.export_options()
            rows, categories, _ = build_popart_rows(
                self._dataset, trait_field=field, category_order=order, missing_values=missing,
            )
            counts = Counter(
                next((category for category, value in zip(categories, values) if value == "1"), "Unknown")
                for _, _, values in rows
            )
            self._preview.setPlainText("\n".join(f"{key}: {counts[key]}" for key in (*categories, "Unknown") if counts[key]))
        except PopArtExportError as error:
            self._preview.setPlainText(str(error))
