"""Minimal GUI for inspecting and selecting immutable project datasets.

This manager only routes existing ``SequenceDataset`` values.  It does not
import files, run analyses, or persist the project.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Optional
import tkinter as tk
from tkinter import ttk

from core.project import Project
from core.analysis_result import AnalysisResultType
from core.sequence_dataset import SequenceDataset, SourceType
from core.dataset_open_router import DatasetOpenRouteError, DatasetOpenRouter
from gui.blast_workflow_actions import (
    BlastWorkflowActionError,
    BlastResultResolver,
    OpenBlastResultCallback,
    open_project_blast_result,
)
from gui.bold_workflow_actions import (
    BoldWorkflowActionError,
    BoldResultResolver,
    OpenBoldResultCallback,
    open_project_bold_result,
)
from gui.fasta_import_dialog import FastaImportDialog


class DatasetSelectionError(ValueError):
    """Raised when a dataset-manager action cannot be safely routed."""


@dataclass(frozen=True)
class DatasetTableRow:
    """Display-only projection of one immutable ``ProjectDatasetEntry``."""

    selected: bool
    dataset_name: str
    dataset_id: str
    source_type: str
    sequence_count: int
    length_range: str
    has_gaps: str
    parent_dataset_id: str
    derivation_type: str


@dataclass(frozen=True)
class AnalysisResultTableRow:
    """Display-only projection of one immutable project analysis entry."""

    display_name: str
    result_id: str
    result_type: str
    parent_dataset_id: str


OpenDatasetCallback = Callable[[SequenceDataset], None]
OpenDatasetsCallback = Callable[[tuple[SequenceDataset, ...]], None]
ProjectChangedCallback = Callable[[Project], None]
AlignDatasetCallback = Callable[[SequenceDataset, Project], Project]
RunBlastCallback = Callable[[SequenceDataset, Project], Project]


class ProjectDatasetManagerState:
    """Mutable GUI selection state around an immutable :class:`Project`."""

    def __init__(self, project: Project) -> None:
        if not isinstance(project, Project):
            raise ValueError("project must be a Project")
        self.project = project
        self._selected_dataset_ids: set[str] = set()

    def table_rows(self) -> tuple[DatasetTableRow, ...]:
        return tuple(
            DatasetTableRow(
                selected=_dataset_id(entry.dataset) in self._selected_dataset_ids,
                dataset_name=entry.display_name,
                dataset_id=_dataset_id(entry.dataset),
                source_type=_dataset_type(entry.dataset),
                sequence_count=entry.dataset.sequence_count,
                length_range=_length_range(entry.dataset),
                has_gaps="Yes" if _has_gaps(entry.dataset) else "No",
                parent_dataset_id=entry.parent_dataset_id or "-",
                derivation_type=(entry.derivation_type.value if entry.derivation_type else "-"),
            )
            for entry in self.project.dataset_entries
        )

    def analysis_result_rows(self) -> tuple[AnalysisResultTableRow, ...]:
        return tuple(
            AnalysisResultTableRow(
                display_name=entry.display_name,
                result_id=entry.result_id,
                result_type=entry.result_type.value,
                parent_dataset_id=entry.parent_dataset_id,
            )
            for entry in self.project.analysis_results
        )

    def set_selected(self, dataset_id: str, selected: bool) -> None:
        if not self.project.has_dataset(dataset_id):
            raise DatasetSelectionError(f"unknown dataset_id: {dataset_id}")
        if selected:
            self._selected_dataset_ids.add(dataset_id)
        else:
            self._selected_dataset_ids.discard(dataset_id)

    def select_all(self) -> None:
        self._selected_dataset_ids = set(self.project.dataset_ids)

    def deselect_all(self) -> None:
        self._selected_dataset_ids.clear()

    def selected_datasets(self) -> tuple[SequenceDataset, ...]:
        """Return selected values in the project order, never click order."""

        return tuple(
            entry.dataset
            for entry in self.project.dataset_entries
            if _dataset_id(entry.dataset) in self._selected_dataset_ids
        )

    def open_selected(
        self,
        *,
        on_open_dataset: Optional[OpenDatasetCallback] = None,
        on_open_datasets: Optional[OpenDatasetsCallback] = None,
        dataset_open_router: Optional[DatasetOpenRouter] = None,
    ) -> tuple[SequenceDataset, ...]:
        selected = self.selected_datasets()
        if not selected:
            raise DatasetSelectionError("select at least one dataset before opening")
        if dataset_open_router is not None:
            if not isinstance(dataset_open_router, DatasetOpenRouter):
                raise DatasetSelectionError("dataset_open_router must be a DatasetOpenRouter or None")
            for dataset in selected:
                dataset_open_router.open(dataset)
        elif len(selected) == 1 and on_open_dataset is not None:
            on_open_dataset(selected[0])
        elif on_open_datasets is not None:
            on_open_datasets(selected)
        elif on_open_dataset is not None:
            for dataset in selected:
                on_open_dataset(dataset)
        else:
            raise DatasetSelectionError("no dataset-open callback is configured")
        return selected

    def remove_selected(
        self,
        *,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> Project:
        """Remove selected leaf datasets while keeping the original Project intact.

        Selected datasets are visited in reverse project order so a selected
        child is removed before its selected parent.  A parent with an
        unselected child still fails through ``Project.remove_dataset``.
        """

        selected_ids = tuple(row.dataset_id for row in self.table_rows() if row.selected)
        if not selected_ids:
            raise DatasetSelectionError("select at least one dataset before removing")

        updated = self.project
        for dataset_id in reversed(selected_ids):
            updated = updated.remove_dataset(dataset_id)
        self.project = updated
        self._selected_dataset_ids.intersection_update(updated.dataset_ids)
        if on_project_changed is not None:
            on_project_changed(updated)
        return updated

    def align_selected(
        self,
        on_align_dataset: Optional[AlignDatasetCallback],
        *,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> Project:
        """Delegate one unaligned selected dataset to an application callback.

        The state layer owns neither MAFFT nor a viewer.  It only validates the
        minimal workflow boundary and replaces its Project after the callback
        returns a new immutable Project successfully.
        """

        if on_align_dataset is None or not callable(on_align_dataset):
            raise DatasetSelectionError("no MAFFT alignment callback is configured")
        selected = self.selected_datasets()
        if len(selected) != 1:
            raise DatasetSelectionError("MAFFT alignment requires exactly one selected dataset")
        dataset = selected[0]
        if not isinstance(dataset, SequenceDataset):
            raise DatasetSelectionError("only unaligned SequenceDataset values can be aligned here")
        if dataset.source_type is SourceType.IMPORTED_ALIGNMENT:
            raise DatasetSelectionError("an existing alignment dataset cannot be aligned again here")
        if dataset.has_gaps:
            raise DatasetSelectionError("MAFFT alignment requires a gap-free dataset")

        updated_project = on_align_dataset(dataset, self.project)
        if not isinstance(updated_project, Project):
            raise DatasetSelectionError("MAFFT alignment callback must return a Project")
        self.project = updated_project
        if on_project_changed is not None:
            on_project_changed(updated_project)
        return updated_project

    def run_blast_selected(
        self,
        on_run_blast: Optional[RunBlastCallback],
        *,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> Project:
        """Delegate exactly one selected dataset to an application BLAST callback."""

        if on_run_blast is None or not callable(on_run_blast):
            raise DatasetSelectionError("no BLAST workflow callback is configured")
        selected = self.selected_datasets()
        if len(selected) != 1:
            raise DatasetSelectionError("BLAST requires exactly one selected dataset")
        updated_project = on_run_blast(selected[0], self.project)
        if not isinstance(updated_project, Project):
            raise DatasetSelectionError("BLAST workflow callback must return a Project")
        self.project = updated_project
        if on_project_changed is not None:
            on_project_changed(updated_project)
        return updated_project


class ProjectDatasetManagerWindow(tk.Toplevel):
    """Tkinter table for selecting datasets from a supplied in-memory Project."""

    _COLUMNS = (
        "selected",
        "dataset_name",
        "dataset_id",
        "source_type",
        "sequence_count",
        "length_range",
        "has_gaps",
        "parent_dataset",
        "derivation_type",
    )
    _HEADINGS = (
        "Selected",
        "Dataset Name",
        "Dataset ID",
        "Source Type",
        "Sequence Count",
        "Length Range",
        "Has Gaps",
        "Parent Dataset",
        "Derivation Type",
    )

    def __init__(
        self,
        master: tk.Misc | None,
        project: Project,
        *,
        on_open_dataset: Optional[OpenDatasetCallback] = None,
        on_open_datasets: Optional[OpenDatasetsCallback] = None,
        dataset_open_router: Optional[DatasetOpenRouter] = None,
        on_align_dataset: Optional[AlignDatasetCallback] = None,
        on_run_blast: Optional[RunBlastCallback] = None,
        resolve_blast_result: Optional[BlastResultResolver] = None,
        on_open_blast_result: Optional[OpenBlastResultCallback] = None,
        resolve_bold_result: Optional[BoldResultResolver] = None,
        on_open_bold_result: Optional[OpenBoldResultCallback] = None,
        on_project_changed: Optional[ProjectChangedCallback] = None,
    ) -> None:
        if on_open_dataset is not None and not callable(on_open_dataset):
            raise ValueError("on_open_dataset must be callable or None")
        if on_open_datasets is not None and not callable(on_open_datasets):
            raise ValueError("on_open_datasets must be callable or None")
        if dataset_open_router is not None and not isinstance(dataset_open_router, DatasetOpenRouter):
            raise ValueError("dataset_open_router must be a DatasetOpenRouter or None")
        if on_align_dataset is not None and not callable(on_align_dataset):
            raise ValueError("on_align_dataset must be callable or None")
        if on_run_blast is not None and not callable(on_run_blast):
            raise ValueError("on_run_blast must be callable or None")
        if resolve_blast_result is not None and not callable(resolve_blast_result):
            raise ValueError("resolve_blast_result must be callable or None")
        if on_open_blast_result is not None and not callable(on_open_blast_result):
            raise ValueError("on_open_blast_result must be callable or None")
        if resolve_bold_result is not None and not callable(resolve_bold_result):
            raise ValueError("resolve_bold_result must be callable or None")
        if on_open_bold_result is not None and not callable(on_open_bold_result):
            raise ValueError("on_open_bold_result must be callable or None")
        if on_project_changed is not None and not callable(on_project_changed):
            raise ValueError("on_project_changed must be callable or None")

        super().__init__(master)
        self.state = ProjectDatasetManagerState(project)
        self.on_open_dataset = on_open_dataset
        self.on_open_datasets = on_open_datasets
        self.dataset_open_router = dataset_open_router
        self.on_align_dataset = on_align_dataset
        self.on_run_blast = on_run_blast
        self.resolve_blast_result = resolve_blast_result
        self.on_open_blast_result = on_open_blast_result
        self.resolve_bold_result = resolve_bold_result
        self.on_open_bold_result = on_open_bold_result
        self.on_project_changed = on_project_changed
        self._message_var = tk.StringVar(value="Select one or more datasets.")
        self._item_dataset_ids: dict[str, str] = {}
        self._item_analysis_result_ids: dict[str, str] = {}

        self.title("Project Dataset Manager")
        self.geometry("1160x560")
        self.minsize(900, 360)
        self._build_layout()
        self.refresh_table()

    @property
    def project(self) -> Project:
        """The manager's current immutable project value."""

        return self.state.project

    def _build_layout(self) -> None:
        project_frame = ttk.Frame(self, padding=(10, 10, 10, 6))
        project_frame.pack(fill="x")
        ttk.Label(project_frame, text="Project:", font=("TkDefaultFont", 10, "bold")).grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        ttk.Label(project_frame, text=self.state.project.name).grid(row=0, column=1, sticky="w")
        ttk.Label(project_frame, text="Project ID:", font=("TkDefaultFont", 10, "bold")).grid(
            row=1, column=0, sticky="w", padx=(0, 6)
        )
        ttk.Label(project_frame, text=self.state.project.project_id).grid(row=1, column=1, sticky="w")
        table_frame = ttk.Frame(self, padding=(10, 0, 10, 8))
        table_frame.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table_frame, columns=self._COLUMNS, show="headings", selectmode="none")
        for column, heading in zip(self._COLUMNS, self._HEADINGS):
            self.table.heading(column, text=heading)
            self.table.column(column, anchor="w", stretch=True, width=125)
        self.table.column("selected", width=75, stretch=False, anchor="center")
        self.table.column("sequence_count", width=105, stretch=False, anchor="e")
        self.table.column("length_range", width=100, stretch=False, anchor="e")
        self.table.column("has_gaps", width=85, stretch=False, anchor="center")
        y_scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.table.yview)
        x_scrollbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=y_scrollbar.set, xscrollcommand=x_scrollbar.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        y_scrollbar.grid(row=0, column=1, sticky="ns")
        x_scrollbar.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.table.bind("<Button-1>", self._toggle_selection_from_click, add=True)

        analysis_frame = ttk.LabelFrame(self, text="Analysis Results", padding=(8, 6))
        analysis_frame.pack(fill="x", padx=10, pady=(0, 8))
        analysis_frame.columnconfigure(0, weight=1)
        self.analysis_table = ttk.Treeview(
            analysis_frame,
            columns=("name", "result_type", "parent_dataset_id"),
            show="headings",
            selectmode="browse",
            height=4,
        )
        for column, heading, width in (
            ("name", "Name", 280),
            ("result_type", "Result Type", 150),
            ("parent_dataset_id", "Parent Dataset ID", 220),
        ):
            self.analysis_table.heading(column, text=heading)
            self.analysis_table.column(column, anchor="w", width=width, stretch=True)
        self.analysis_table.grid(row=0, column=0, sticky="ew")
        self._open_result_button = ttk.Button(
            analysis_frame,
            text="Open Result",
            command=self._open_analysis_result,
        )
        self._open_result_button.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        footer = ttk.Frame(self, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Button(footer, text="Select All", command=self._select_all).pack(side="left")
        ttk.Button(footer, text="Deselect All", command=self._deselect_all).pack(side="left", padx=(6, 0))
        ttk.Button(footer, text="Import FASTA", command=self._open_fasta_import).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(
            footer,
            text="Align with MAFFT",
            command=self._align_selected,
            state="normal" if self.on_align_dataset else "disabled",
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            footer,
            text="Run BLAST",
            command=self._run_blast_selected,
            state="normal" if self.on_run_blast else "disabled",
        ).pack(side="left", padx=(6, 0))
        ttk.Label(footer, textvariable=self._message_var, anchor="w").pack(
            side="left", fill="x", expand=True, padx=12
        )
        open_state = "normal" if (
            self.dataset_open_router or self.on_open_dataset or self.on_open_datasets
        ) else "disabled"
        ttk.Button(footer, text="Open Dataset", command=self._open_selected, state=open_state).pack(
            side="right"
        )
        ttk.Button(footer, text="Remove from Project", command=self._remove_selected).pack(
            side="right", padx=(0, 6)
        )
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right", padx=(0, 6))

    def refresh_table(self) -> None:
        for item_id in self.table.get_children():
            self.table.delete(item_id)
        self._item_dataset_ids.clear()
        for index, row in enumerate(self.state.table_rows()):
            item_id = self.table.insert(
                "",
                "end",
                iid=f"dataset-{index}",
                values=(
                    "☑" if row.selected else "☐",
                    row.dataset_name,
                    row.dataset_id,
                    row.source_type,
                    row.sequence_count,
                    row.length_range,
                    row.has_gaps,
                    row.parent_dataset_id,
                    row.derivation_type,
                ),
            )
            self._item_dataset_ids[item_id] = row.dataset_id
        self._refresh_analysis_results()

    def _refresh_analysis_results(self) -> None:
        for item_id in self.analysis_table.get_children():
            self.analysis_table.delete(item_id)
        self._item_analysis_result_ids.clear()
        for index, row in enumerate(self.state.analysis_result_rows()):
            item_id = self.analysis_table.insert(
                "",
                "end",
                iid=f"analysis-result-{index}",
                values=(row.display_name, row.result_type, row.parent_dataset_id),
            )
            self._item_analysis_result_ids[item_id] = row.result_id
        can_open_blast = bool(self.resolve_blast_result and self.on_open_blast_result)
        can_open_bold = bool(self.resolve_bold_result and self.on_open_bold_result)
        self._open_result_button.configure(state="normal" if can_open_blast or can_open_bold else "disabled")

    def _toggle_selection_from_click(self, event: tk.Event) -> None:
        item_id = self.table.identify_row(event.y)
        column = self.table.identify_column(event.x)
        if not item_id or column != "#1":
            return
        dataset_id = self._item_dataset_ids[item_id]
        currently_selected = dataset_id in {dataset.dataset_id for dataset in self.state.selected_datasets()}
        self.state.set_selected(dataset_id, not currently_selected)
        self.refresh_table()

    def _select_all(self) -> None:
        self.state.select_all()
        self.refresh_table()

    def _deselect_all(self) -> None:
        self.state.deselect_all()
        self.refresh_table()

    def _open_selected(self) -> None:
        try:
            selected = self.state.open_selected(
                on_open_dataset=self.on_open_dataset,
                on_open_datasets=self.on_open_datasets,
                dataset_open_router=self.dataset_open_router,
            )
        except (DatasetSelectionError, DatasetOpenRouteError) as error:
            self._message_var.set(str(error))
        else:
            self._message_var.set(f"Sent {len(selected)} selected dataset(s) to the configured callback.")

    def _remove_selected(self) -> None:
        try:
            self.state.remove_selected(on_project_changed=self.on_project_changed)
        except (DatasetSelectionError, ValueError, KeyError) as error:
            self._message_var.set(str(error))
            return

        self.refresh_table()
        self._message_var.set("Selected dataset(s) removed from this in-memory project.")

    def _open_fasta_import(self) -> None:
        FastaImportDialog(
            self,
            self.project,
            on_project_changed=self._on_fasta_imported,
        )

    def _on_fasta_imported(self, updated_project: Project) -> None:
        self.state.project = updated_project
        self.refresh_table()
        self._message_var.set("FASTA dataset imported into this in-memory project.")
        if self.on_project_changed is not None:
            self.on_project_changed(updated_project)

    def _align_selected(self) -> None:
        try:
            self.state.align_selected(
                self.on_align_dataset,
                on_project_changed=self.on_project_changed,
            )
        except (DatasetSelectionError, RuntimeError, ValueError) as error:
            self._message_var.set(str(error))
            return
        self.refresh_table()
        self._message_var.set("MAFFT alignment dataset added to this in-memory project.")

    def _run_blast_selected(self) -> None:
        try:
            self.state.run_blast_selected(
                self.on_run_blast,
                on_project_changed=self.on_project_changed,
            )
        except (DatasetSelectionError, RuntimeError, ValueError) as error:
            self._message_var.set(str(error))
            return
        self.refresh_table()
        self._message_var.set("BLAST result added to this in-memory project.")

    def _open_analysis_result(self) -> None:
        try:
            selection = self.analysis_table.selection()
            if not selection:
                raise BlastWorkflowActionError("select an analysis result before opening")
            result_id = self._item_analysis_result_ids[selection[0]]
            result = self.project.get_analysis_result(result_id)
            if result.result_type is AnalysisResultType.BLAST:
                open_project_blast_result(
                    self.project,
                    result_id,
                    resolve_blast_result=self.resolve_blast_result,  # type: ignore[arg-type]
                    on_open_blast_result=self.on_open_blast_result,  # type: ignore[arg-type]
                )
            elif result.result_type is AnalysisResultType.BOLD:
                open_project_bold_result(
                    self.project,
                    result_id,
                    resolve_bold_result=self.resolve_bold_result,  # type: ignore[arg-type]
                    on_open_bold_result=self.on_open_bold_result,  # type: ignore[arg-type]
                )
            else:
                raise BlastWorkflowActionError(f"unsupported analysis result type: {result.result_type.value}")
        except (BlastWorkflowActionError, BoldWorkflowActionError) as error:
            self._message_var.set(str(error))


def _dataset_id(dataset: object) -> str:
    return str(getattr(dataset, "dataset_id", None) or getattr(dataset, "alignment_id", "-"))


def _dataset_type(dataset: object) -> str:
    source_type = getattr(dataset, "source_type", None)
    if source_type is not None:
        return getattr(source_type, "value", str(source_type))
    if hasattr(dataset, "alignment_id"):
        return "AlignmentDataset"
    return type(dataset).__name__


def _length_range(dataset: object) -> str:
    if hasattr(dataset, "minimum_length") and hasattr(dataset, "maximum_length"):
        return f"{dataset.minimum_length}\N{EN DASH}{dataset.maximum_length}"
    if hasattr(dataset, "length"):
        return f"{dataset.length}\N{EN DASH}{dataset.length}"
    return "-"


def _has_gaps(dataset: object) -> bool:
    if hasattr(dataset, "has_gaps"):
        return bool(dataset.has_gaps)
    return any("-" in getattr(record, "aligned_sequence", "") for record in getattr(dataset, "records", ()))
