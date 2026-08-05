"""Tk dialog and testable state for importing one FASTA into a Project."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional
import tkinter as tk
from tkinter import filedialog, ttk

from core.fasta_dataset import FastaOpenMode, read_fasta_dataset
from core.project import DerivationType, Project


class FastaImportError(ValueError):
    """A user-facing import problem that leaves the current Project unchanged."""


ProjectChangedCallback = Callable[[Project], None]


class FastaImportDialogState:
    """Mutable dialog state around an immutable Project value."""

    def __init__(self, project: Project) -> None:
        if not isinstance(project, Project):
            raise ValueError("project must be a Project")
        self.project = project
        self.filepath: str | None = None

    def set_filepath(self, filepath: str | Path) -> None:
        path = Path(filepath)
        self.filepath = str(path)

    def import_dataset(
        self,
        *,
        dataset_name: str,
        open_mode: FastaOpenMode | str,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> Project:
        """Read, add, and publish a new immutable Project only on success."""

        if not self.filepath:
            raise FastaImportError("select a FASTA file before importing")
        if not isinstance(dataset_name, str) or not dataset_name.strip():
            raise FastaImportError("Dataset Name is required")
        try:
            mode = open_mode if isinstance(open_mode, FastaOpenMode) else FastaOpenMode(open_mode)
        except ValueError as error:
            raise FastaImportError("Open Mode must be auto, unaligned, or alignment") from error

        try:
            dataset = read_fasta_dataset(self.filepath, name=dataset_name, open_as=mode)
            updated_project = self.project.add_dataset(
                dataset,
                derivation_type=DerivationType.IMPORTED,
            )
        except (FileNotFoundError, ValueError) as error:
            raise FastaImportError(str(error)) from error

        self.project = updated_project
        if on_project_changed is not None:
            on_project_changed(updated_project)
        return updated_project


class FastaImportDialog(tk.Toplevel):
    """Minimal modal-style dialog for importing one FASTA dataset."""

    def __init__(
        self,
        master: tk.Misc | None,
        project: Project,
        *,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> None:
        if on_project_changed is not None and not callable(on_project_changed):
            raise ValueError("on_project_changed must be callable or None")
        super().__init__(master)
        self.state = FastaImportDialogState(project)
        self.on_project_changed = on_project_changed
        self._filepath_var = tk.StringVar(value="")
        self._dataset_name_var = tk.StringVar(value="")
        self._open_mode_var = tk.StringVar(value=FastaOpenMode.AUTO.value)
        self._message_var = tk.StringVar(value="Choose a FASTA file to import.")

        self.title("Import FASTA Dataset")
        self.resizable(True, False)
        self.transient(master)
        self._build_layout()

    @property
    def project(self) -> Project:
        return self.state.project

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="File:").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Entry(content, textvariable=self._filepath_var, state="readonly", width=52).grid(
            row=0, column=1, sticky="ew", pady=(0, 8)
        )
        ttk.Button(content, text="Choose File…", command=self._choose_file).grid(
            row=0, column=2, sticky="e", padx=(8, 0), pady=(0, 8)
        )

        ttk.Label(content, text="Dataset Name:").grid(row=1, column=0, sticky="w", pady=(0, 10))
        ttk.Entry(content, textvariable=self._dataset_name_var).grid(
            row=1, column=1, columnspan=2, sticky="ew", pady=(0, 10)
        )

        mode_frame = ttk.LabelFrame(content, text="Open Mode", padding=8)
        mode_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        for index, (text, mode) in enumerate(
            (
                ("Auto", FastaOpenMode.AUTO),
                ("Unaligned", FastaOpenMode.UNALIGNED),
                ("Alignment", FastaOpenMode.ALIGNMENT),
            )
        ):
            ttk.Radiobutton(mode_frame, text=text, variable=self._open_mode_var, value=mode.value).grid(
                row=0, column=index, sticky="w", padx=(0, 18)
            )

        footer = ttk.Frame(content)
        footer.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Label(footer, textvariable=self._message_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Import", command=self._import).pack(side="right", padx=(0, 6))

    def _choose_file(self) -> None:
        filepath = filedialog.askopenfilename(
            parent=self,
            title="Choose FASTA file",
            filetypes=(
                ("FASTA files", "*.fas *.fasta *.fa *.fna"),
                ("All files", "*"),
            ),
        )
        if filepath:
            self.select_file(filepath)

    def select_file(self, filepath: str | Path) -> None:
        """Set the selected file and a user-editable default dataset name."""

        path = Path(filepath)
        self.state.set_filepath(path)
        self._filepath_var.set(str(path))
        self._dataset_name_var.set(path.stem or path.name)
        self._message_var.set("Choose an open mode, then import the FASTA dataset.")

    def _import(self) -> None:
        try:
            self.state.import_dataset(
                dataset_name=self._dataset_name_var.get(),
                open_mode=self._open_mode_var.get(),
                on_project_changed=self.on_project_changed,
            )
        except FastaImportError as error:
            self._message_var.set(str(error))
            return
        self.destroy()
