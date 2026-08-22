"""Small Studio dialogs for external identification services."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QGroupBox,
    QVBoxLayout,
)

from app.gui_thread import assert_main_gui_thread
from app.icon_registry import studio_icon
from workflow.ncbi_blast_service import NcbiBlastProgress, NcbiBlastSettings


class BlastSettingsDialog(QDialog):
    """Choose safe online BLAST settings or the assisted Website workflow."""

    _PROGRAMS = ("blastn",)
    _DATABASES = ("nt", "refseq_rna", "refseq_representative_genomes", "Custom…")

    def __init__(
        self,
        *,
        query_count: int,
        included_query_count: int | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("BLAST")
        self._all_query_count = int(query_count)
        self._included_query_count = int(included_query_count or query_count)
        layout = QVBoxLayout(self)
        self._summary = QLabel()
        layout.addWidget(self._summary)

        mode_form = QFormLayout()
        self._mode = QComboBox()
        self._mode.addItem("NCBI Online", "online")
        self._mode.addItem("NCBI via Website", "website")
        mode_form.addRow("Mode", self._mode)
        if self._included_query_count != self._all_query_count:
            self._query_scope = QComboBox()
            self._query_scope.addItem(
                f"Included records ({self._included_query_count})", "included",
            )
            self._query_scope.addItem(f"All records ({self._all_query_count})", "all")
            self._query_scope.currentIndexChanged.connect(self._update_summary)
            mode_form.addRow("Queries", self._query_scope)
        else:
            self._query_scope = None
            mode_form.addRow("Queries", QLabel(f"All records ({self._all_query_count})"))
        layout.addLayout(mode_form)

        self._online_group = QGroupBox("NCBI Online settings")
        online_layout = QVBoxLayout(self._online_group)
        form = QFormLayout()
        self._program = QComboBox()
        for program in self._PROGRAMS:
            self._program.addItem(program)
        self._database = QComboBox()
        for database in self._DATABASES:
            self._database.addItem(database)
        self._custom_database = QLineEdit()
        self._custom_database.setPlaceholderText("Documented NCBI database name")
        self._custom_database.setEnabled(False)
        self._database.currentIndexChanged.connect(self._update_custom_database)
        self._max_hits = QSpinBox()
        self._max_hits.setRange(1, 100)
        self._max_hits.setValue(10)
        self._email = QLineEdit("")
        self._email.setPlaceholderText("optional, recommended by NCBI")
        form.addRow("Program", self._program)
        form.addRow("Database", self._database)
        form.addRow("Custom database", self._custom_database)
        form.addRow("Max target sequences", self._max_hits)
        form.addRow("NCBI contact email", self._email)
        online_layout.addLayout(form)
        advanced = QGroupBox("Advanced")
        advanced_form = QFormLayout(advanced)
        self._expect = QLineEdit("")
        self._expect.setPlaceholderText("NCBI default when blank")
        advanced_form.addRow("E-value", self._expect)
        online_layout.addWidget(advanced)
        layout.addWidget(self._online_group)

        self._website_note = QLabel(
            "SangerFlow will prepare exact-ID multi-FASTA. Paste or upload it on the official "
            "NCBI BLAST website, download BLAST XML, then import it here."
        )
        self._website_note.setWordWrap(True)
        self._website_note.setVisible(False)
        layout.addWidget(self._website_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        self._accept_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self._accept_button.setText("Run BLAST")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._mode.currentIndexChanged.connect(self._update_mode)
        self._update_summary()
        self._update_mode()

    @property
    def launch_mode(self) -> str:
        return str(self._mode.currentData())

    @property
    def query_scope(self) -> str:
        return "all" if self._query_scope is None else str(self._query_scope.currentData())

    @property
    def final_query_count(self) -> int:
        return self._all_query_count if self.query_scope == "all" else self._included_query_count

    def _update_summary(self, *_args: object) -> None:
        self._summary.setText(f"Final query count: {self.final_query_count}")

    def _update_mode(self, *_args: object) -> None:
        online = self.launch_mode == "online"
        self._online_group.setVisible(online)
        self._website_note.setVisible(not online)
        self._accept_button.setText("Run BLAST" if online else "Continue")

    def _update_custom_database(self, *_args: object) -> None:
        custom = self._database.currentText() == "Custom…"
        self._custom_database.setEnabled(custom)
        if custom:
            self._custom_database.setFocus()

    def settings(self) -> NcbiBlastSettings:
        if self.launch_mode != "online":
            raise ValueError("NCBI Online settings were requested for Website mode")
        expect_text = self._expect.text().strip()
        email_text = self._email.text().strip()
        database = self._custom_database.text().strip() if self._database.currentText() == "Custom…" else self._database.currentText()
        return NcbiBlastSettings(
            program=self._program.currentText(),
            database=database,
            max_target_sequences=int(self._max_hits.value()),
            expect=float(expect_text) if expect_text else None,
            email=email_text or None,
        )


def website_blast_fasta(dataset: object) -> str:
    """Return the exact-ID multi-FASTA used by the official Website workflow."""

    records = tuple(getattr(dataset, "records", ()))
    if not records:
        raise ValueError("Select at least one record before preparing BLAST Website FASTA.")
    lines: list[str] = []
    for record in records:
        record_id = getattr(record, "sequence_id", "")
        sequence = getattr(record, "sequence", "")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("BLAST Website FASTA requires non-empty record IDs.")
        if not isinstance(sequence, str) or not sequence:
            raise ValueError(f"BLAST Website FASTA record {record_id!r} has no sequence.")
        lines.extend((f">{record_id}", sequence))
    return "\n".join(lines) + "\n"


class BlastWebsiteDialog(QDialog):
    """Studio-assisted, deliberately manual NCBI Web BLAST round trip."""

    official_blast_url = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"

    def __init__(self, query_dataset: object, *, on_import_xml, parent=None) -> None:
        super().__init__(parent)
        self._query_dataset = query_dataset
        self._on_import_xml = on_import_xml
        self._fasta = website_blast_fasta(query_dataset)
        self.setWindowTitle("NCBI BLAST via Website")
        layout = QVBoxLayout(self)
        instructions = QLabel(
            "1. Copy or save the exact-ID FASTA below.\n"
            "2. Paste/upload it on the official NCBI BLAST website and run BLAST.\n"
            "3. Download BLAST XML, then import it here."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        self._fasta_preview = QPlainTextEdit(self._fasta)
        self._fasta_preview.setReadOnly(True)
        self._fasta_preview.setMinimumHeight(160)
        layout.addWidget(self._fasta_preview)
        actions = QHBoxLayout()
        self._copy_button = QPushButton("Copy FASTA to Clipboard")
        self._copy_button.setIcon(studio_icon("copy"))
        self._save_button = QPushButton("Save FASTA…")
        self._save_button.setIcon(studio_icon("save"))
        self._open_button = QPushButton("Open Official NCBI BLAST Website")
        self._open_button.setIcon(studio_icon("blast"))
        self._import_button = QPushButton("Import Downloaded XML…")
        self._import_button.setIcon(studio_icon("import"))
        self._copy_button.clicked.connect(self.copy_fasta_to_clipboard)
        self._save_button.clicked.connect(self.save_fasta)
        self._open_button.clicked.connect(self.open_official_website)
        self._import_button.clicked.connect(self.import_downloaded_xml)
        for button in (self._copy_button, self._save_button, self._open_button, self._import_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    @property
    def fasta_text(self) -> str:
        return self._fasta

    def copy_fasta_to_clipboard(self) -> str:
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(self._fasta)
        return self._fasta

    def save_fasta(self) -> str | None:
        from PySide6.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save BLAST Website FASTA", "blast_queries.fasta", "FASTA files (*.fasta *.fa *.fas);;All files (*)",
        )
        if not filepath:
            return None
        path = filepath if filepath.lower().endswith((".fasta", ".fa", ".fas")) else f"{filepath}.fasta"
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self._fasta)
        return path

    def open_official_website(self) -> bool:
        return QDesktopServices.openUrl(QUrl(self.official_blast_url))

    def import_downloaded_xml(self) -> object | None:
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Import Downloaded NCBI BLAST XML", "", "NCBI BLAST XML (*.xml);;All files (*)",
        )
        if not filepath:
            return None
        try:
            return self._on_import_xml(filepath)
        except ValueError as error:
            QMessageBox.warning(self, "Import NCBI BLAST XML", str(error))
            return None


@dataclass(frozen=True)
class BlastMetadataSettings:
    minimum_identity: float = 98.0
    minimum_coverage: float = 90.0
    mark_uncertain: bool = True
    fields: frozenset[str] = frozenset({
        "blast_best_hit",
        "blast_scientific_name",
        "blast_accession",
        "blast_identity",
        "blast_query_coverage",
        "blast_evalue",
    })


class BlastMetadataDialog(QDialog):
    """Confirm evidence thresholds before creating a BLAST metadata revision."""

    def __init__(self, *, dataset_name: str, query_count: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Apply BLAST Results to Metadata")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            f"Dataset: {dataset_name}\nQueries with BLAST evidence: {query_count}\n"
            "BLAST-derived fields never overwrite Species."
        ))
        form = QFormLayout()
        self._minimum_identity = QDoubleSpinBox()
        self._minimum_identity.setRange(0.0, 100.0)
        self._minimum_identity.setDecimals(1)
        self._minimum_identity.setValue(98.0)
        self._minimum_coverage = QDoubleSpinBox()
        self._minimum_coverage.setRange(0.0, 100.0)
        self._minimum_coverage.setDecimals(1)
        self._minimum_coverage.setValue(90.0)
        self._mark_uncertain = QCheckBox("Mark below-threshold hits as uncertain")
        self._mark_uncertain.setChecked(True)
        form.addRow("Minimum identity (%)", self._minimum_identity)
        form.addRow("Minimum query coverage (%)", self._minimum_coverage)
        form.addRow("Below threshold", self._mark_uncertain)
        layout.addLayout(form)
        layout.addWidget(QLabel("Fields to add to the new metadata revision"))
        self._field_boxes: dict[str, QCheckBox] = {}
        for key, label in (
            ("blast_best_hit", "Best hit"),
            ("blast_scientific_name", "Scientific name"),
            ("blast_accession", "Accession"),
            ("blast_identity", "Percent identity"),
            ("blast_query_coverage", "Query coverage"),
            ("blast_evalue", "E-value"),
        ):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            self._field_boxes[key] = checkbox
            layout.addWidget(checkbox)
        layout.addWidget(QLabel(
            "Preview: the top hit for each query is copied only to BLAST-namespaced fields; "
            "existing Species metadata is preserved."
        ))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Apply to New Revision")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def settings(self) -> BlastMetadataSettings:
        fields = frozenset(key for key, checkbox in self._field_boxes.items() if checkbox.isChecked())
        if not fields:
            raise ValueError("Select at least one BLAST metadata field.")
        return BlastMetadataSettings(
            minimum_identity=float(self._minimum_identity.value()),
            minimum_coverage=float(self._minimum_coverage.value()),
            mark_uncertain=self._mark_uncertain.isChecked(),
            fields=fields,
        )


class IdentificationProgressDialog(QDialog):
    """Non-modal progress dialog for long-running BLAST requests."""

    def __init__(self, *, title: str = "BLAST", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._cancelled = False
        layout = QVBoxLayout(self)
        self._state_label = QLabel("Preparing...")
        self._query_label = QLabel("Query: —")
        self._counts_label = QLabel("Completed: 0 / 0")
        self._detail_label = QLabel("")
        self._detail_label.setWordWrap(True)
        self._bar = QProgressBar()
        self._bar.setRange(0, 1)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self._state_label)
        layout.addWidget(self._query_label)
        layout.addWidget(self._counts_label)
        layout.addWidget(self._bar)
        layout.addWidget(self._detail_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_button)
        layout.addLayout(buttons)

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        assert_main_gui_thread("IdentificationProgressDialog.cancel")
        self._cancelled = True
        self._state_label.setText("Cancelling...")
        self._cancel_button.setEnabled(False)

    def update_progress(self, progress: NcbiBlastProgress) -> None:
        assert_main_gui_thread("IdentificationProgressDialog.update_progress")
        # NCBI exposes lifecycle states, not a percentage while a RID is
        # queued/running.  Use Qt's indeterminate mode until a query actually
        # completes; never display a misleading stuck 0% bar.
        total = progress.total or 0
        if progress.completed <= 0 and str(progress.state).casefold() not in {
            "complete", "success", "no_hit", "failed", "cancelled"
        }:
            self._bar.setRange(0, 0)
        else:
            self._bar.setRange(0, max(1, total))
            self._bar.setValue(min(progress.completed, max(1, total)))
        self._state_label.setText(progress.state)
        self._query_label.setText(f"Query: {progress.query_id or '—'}")
        self._counts_label.setText(
            f"Completed: {progress.completed} / {total}    "
            f"Successful: {progress.successful}    No hit: {progress.no_hit}    Failed: {progress.failed}"
        )
        details = []
        if progress.rid:
            details.append(f"RID: {progress.rid}")
        if progress.message:
            details.append(progress.message)
        self._detail_label.setText("\n".join(details))
