"""Minimal read-only Tk viewer for immutable BLAST result datasets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from core.blast_filter import BlastResultSelection
from core.blast_result import BlastHit, BlastResultDataset
from gui.blast_filter_dialog import BlastFilterDialog
from gui.blast_selection_dataset_dialog import BlastSelectionDatasetDialog, CreateDatasetCallback
from gui.blast_result_view_model import BlastResultViewModel


SelectionCreatedCallback = Callable[[BlastResultSelection], None]


class BlastResultViewer(tk.Toplevel):
    """Display top hits by query and detailed immutable hit evidence."""

    _COLUMNS = ("query", "top_hit", "identity", "coverage", "evalue")

    def __init__(
        self,
        master: tk.Misc | None,
        blast_result: BlastResultDataset,
        *,
        on_selection_created: SelectionCreatedCallback | None = None,
        on_create_dataset: CreateDatasetCallback | None = None,
    ) -> None:
        if on_selection_created is not None and not callable(on_selection_created):
            raise ValueError("on_selection_created must be callable or None")
        if on_create_dataset is not None and not callable(on_create_dataset):
            raise ValueError("on_create_dataset must be callable or None")
        super().__init__(master)
        self.view_model = BlastResultViewModel.from_result(blast_result)
        self.on_selection_created = on_selection_created
        self.on_create_dataset = on_create_dataset
        self.current_selection: BlastResultSelection | None = None
        self._query_item_ids: dict[str, str] = {}
        self._detail_var = tk.StringVar(value="Select a query to inspect its BLAST hits.")

        self.title(f"BLAST Results — {blast_result.name}")
        self.geometry("820x560")
        self.minsize(640, 420)
        self._build_layout()
        self._populate_summary()

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        content.rowconfigure(3, weight=1)

        result = self.view_model.blast_result
        summary_text = (
            f"Result: {result.name}    Mode: {result.analysis_mode.value}    "
            f"Marker: {result.marker or '-'}    Database: {result.database or '-'}"
        )
        ttk.Label(content, text=summary_text, anchor="w").grid(
            row=0, column=0, sticky="ew", pady=(0, 8)
        )
        self.filter_button = ttk.Button(content, text="Filter…", command=self._open_filter_dialog)
        self.filter_button.grid(row=0, column=1, sticky="e", padx=(8, 0), pady=(0, 8))
        self.create_dataset_button = ttk.Button(
            content,
            text="Create Dataset…",
            command=self._open_selection_dataset_dialog,
            state="disabled",
        )
        self.create_dataset_button.grid(row=0, column=2, sticky="e", padx=(6, 0), pady=(0, 8))

        summary_frame = ttk.Frame(content)
        summary_frame.grid(row=1, column=0, sticky="nsew")
        summary_frame.columnconfigure(0, weight=1)
        summary_frame.rowconfigure(0, weight=1)
        self.summary_table = ttk.Treeview(
            summary_frame,
            columns=self._COLUMNS,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "query": "Query",
            "top_hit": "Top Hit",
            "identity": "Identity",
            "coverage": "Coverage",
            "evalue": "E-value",
        }
        widths = {"query": 150, "top_hit": 260, "identity": 90, "coverage": 90, "evalue": 110}
        for column in self._COLUMNS:
            self.summary_table.heading(column, text=headings[column])
            self.summary_table.column(column, width=widths[column], anchor="w")
        scrollbar = ttk.Scrollbar(summary_frame, orient="vertical", command=self.summary_table.yview)
        self.summary_table.configure(yscrollcommand=scrollbar.set)
        self.summary_table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.summary_table.bind("<<TreeviewSelect>>", self._on_query_selected)

        ttk.Label(content, text="Hit detail", font=("TkDefaultFont", 10, "bold")).grid(
            row=2, column=0, sticky="w", pady=(10, 4)
        )
        self.detail = tk.Text(content, height=12, wrap="word", state="disabled")
        self.detail.grid(row=3, column=0, sticky="nsew")

    def _populate_summary(self) -> None:
        for row in self.view_model.summary_rows():
            item_id = self.summary_table.insert(
                "",
                "end",
                values=(
                    row.query_id,
                    row.top_scientific_name,
                    f"{row.identity:.3f}",
                    f"{row.coverage:.3f}",
                    f"{row.evalue:g}",
                ),
            )
            self._query_item_ids[row.query_id] = item_id

    def select_query(self, query_id: str) -> None:
        """Select a displayed query and show its immutable hit details."""

        item_id = self._query_item_ids.get(query_id)
        if item_id is None:
            raise KeyError(query_id)
        self.summary_table.selection_set(item_id)
        self.summary_table.focus(item_id)
        self.summary_table.see(item_id)
        self._show_query_detail(query_id)

    def submit_selection(self, selection: BlastResultSelection) -> None:
        """Publish a viewer-originated selection to an application callback.

        This minimum integration point deliberately does not create datasets
        or modify Projects.  A future filter UI can produce the selection and
        delegate ``Selection → Dataset → Project`` to the configured
        application-layer callback.
        """

        if not isinstance(selection, BlastResultSelection):
            raise ValueError("selection must be a BlastResultSelection")
        if selection.source_result_id != self.view_model.blast_result.result_id:
            raise ValueError("selection source_result_id does not match this BLAST result")
        if self.on_selection_created is None:
            raise ValueError("no BLAST selection callback is configured")
        self.on_selection_created(selection)
        self._set_current_selection(selection)

    def _on_query_selected(self, _event: tk.Event[tk.Misc]) -> None:
        selection = self.summary_table.selection()
        if not selection:
            return
        query_id = str(self.summary_table.item(selection[0], "values")[0])
        self._show_query_detail(query_id)

    def _show_query_detail(self, query_id: str) -> None:
        hits = self.view_model.get_hits(query_id)
        self._set_detail_text(_format_hits(query_id, hits))

    def _set_detail_text(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _open_filter_dialog(self) -> None:
        """Open the filter form; selection publication stays callback-based."""

        BlastFilterDialog(
            self,
            self.view_model.blast_result,
            on_selection_created=self._accept_filter_selection,
        )

    def _accept_filter_selection(self, selection: BlastResultSelection) -> None:
        """Accept a dialog-produced selection and publish it when configured."""

        if selection.source_result_id != self.view_model.blast_result.result_id:
            raise ValueError("selection source_result_id does not match this BLAST result")
        if self.on_selection_created is not None:
            self.on_selection_created(selection)
        self._set_current_selection(selection)

    def _set_current_selection(self, selection: BlastResultSelection) -> None:
        self.current_selection = selection
        if self.on_create_dataset is not None:
            self.create_dataset_button.configure(state="normal")

    def _open_selection_dataset_dialog(self) -> None:
        if self.current_selection is None or self.on_create_dataset is None:
            return
        BlastSelectionDatasetDialog(
            self,
            self.current_selection,
            on_create_dataset=self.on_create_dataset,
        )


def _format_hits(query_id: str, hits: tuple[BlastHit, ...]) -> str:
    if not hits:
        return f"Query: {query_id}\n\nNo hits."
    sections = []
    for rank, hit in enumerate(hits, start=1):
        sections.append(
            "\n".join(
                (
                    f"Query: {query_id}",
                    f"Rank: {rank}",
                    f"Accession: {hit.hit_accession}",
                    f"Scientific name: {hit.scientific_name}",
                    f"Organism: {hit.organism}",
                    f"Identity: {hit.identity}",
                    f"Coverage: {hit.query_coverage}",
                    f"E-value: {hit.evalue}",
                    f"Database: {hit.database}",
                )
            )
        )
    return "\n\n".join(sections)
