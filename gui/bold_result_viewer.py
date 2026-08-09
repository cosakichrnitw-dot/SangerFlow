"""Minimal read-only Tk viewer for immutable BOLD result datasets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from core.bold_filter import BoldResultSelection
from core.bold_result import BoldHit, BoldResultDataset
from gui.bold_filter_dialog import BoldFilterDialog
from gui.bold_selection_dataset_dialog import BoldSelectionDatasetDialog, CreateDatasetCallback
from gui.bold_result_view_model import BoldResultViewModel


SelectionCreatedCallback = Callable[[BoldResultSelection], None]


class BoldResultViewer(tk.Toplevel):
    """Display BOLD top hits by query and taxonomy/reference detail."""

    _COLUMNS = ("query", "species", "genus", "similarity", "bin")

    def __init__(
        self,
        master: tk.Misc | None,
        bold_result: BoldResultDataset,
        *,
        on_selection_created: SelectionCreatedCallback | None = None,
        on_create_dataset: CreateDatasetCallback | None = None,
    ) -> None:
        if on_selection_created is not None and not callable(on_selection_created):
            raise ValueError("on_selection_created must be callable or None")
        if on_create_dataset is not None and not callable(on_create_dataset):
            raise ValueError("on_create_dataset must be callable or None")
        super().__init__(master)
        self.view_model = BoldResultViewModel.from_result(bold_result)
        self.on_selection_created = on_selection_created
        self.on_create_dataset = on_create_dataset
        self.current_selection: BoldResultSelection | None = None
        self._query_item_ids: dict[str, str] = {}

        self.title(f"BOLD Results — {bold_result.name}")
        self.geometry("880x560")
        self.minsize(640, 420)
        self._build_layout()
        self._populate_summary()

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=10)
        content.pack(fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        content.rowconfigure(3, weight=1)

        result = self.view_model.bold_result
        summary_text = (
            f"Result: {result.name}    Marker: {result.marker or '-'}    "
            f"Database: {result.database}"
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
            "species": "Species",
            "genus": "Genus",
            "similarity": "Similarity",
            "bin": "BIN",
        }
        widths = {"query": 150, "species": 250, "genus": 150, "similarity": 100, "bin": 180}
        for column in self._COLUMNS:
            self.summary_table.heading(column, text=headings[column])
            self.summary_table.column(column, width=widths[column], anchor="w")
        scrollbar = ttk.Scrollbar(summary_frame, orient="vertical", command=self.summary_table.yview)
        self.summary_table.configure(yscrollcommand=scrollbar.set)
        self.summary_table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.summary_table.bind("<<TreeviewSelect>>", self._on_query_selected)

        ttk.Label(content, text="BOLD reference detail", font=("TkDefaultFont", 10, "bold")).grid(
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
                    row.species_name or "-",
                    row.genus or "-",
                    "-" if row.similarity is None else f"{row.similarity:.3f}",
                    row.bin_uri or "-",
                ),
            )
            self._query_item_ids[row.query_id] = item_id

    def select_query(self, query_id: str) -> None:
        """Select a displayed query and show its immutable BOLD hit details."""

        item_id = self._query_item_ids.get(query_id)
        if item_id is None:
            raise KeyError(query_id)
        self.summary_table.selection_set(item_id)
        self.summary_table.focus(item_id)
        self.summary_table.see(item_id)
        self._show_query_detail(query_id)

    def submit_selection(self, selection: BoldResultSelection) -> None:
        """Publish a viewer-originated BOLD selection through a callback."""

        if not isinstance(selection, BoldResultSelection):
            raise ValueError("selection must be a BoldResultSelection")
        if selection.source_result_id != self.view_model.bold_result.result_id:
            raise ValueError("selection source_result_id does not match this BOLD result")
        if self.on_selection_created is None:
            raise ValueError("no BOLD selection callback is configured")
        self.on_selection_created(selection)
        self._set_current_selection(selection)

    def _on_query_selected(self, _event: tk.Event[tk.Misc]) -> None:
        selection = self.summary_table.selection()
        if not selection:
            return
        query_id = str(self.summary_table.item(selection[0], "values")[0])
        self._show_query_detail(query_id)

    def _show_query_detail(self, query_id: str) -> None:
        self._set_detail_text(_format_hits(query_id, self.view_model.get_hits(query_id)))

    def _set_detail_text(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _open_filter_dialog(self) -> None:
        """Open filtering UI; dataset and Project actions stay outside this viewer."""

        BoldFilterDialog(
            self,
            self.view_model.bold_result,
            on_selection_created=self._accept_filter_selection,
        )

    def _accept_filter_selection(self, selection: BoldResultSelection) -> None:
        if selection.source_result_id != self.view_model.bold_result.result_id:
            raise ValueError("selection source_result_id does not match this BOLD result")
        if self.on_selection_created is not None:
            self.on_selection_created(selection)
        self._set_current_selection(selection)

    def _set_current_selection(self, selection: BoldResultSelection) -> None:
        self.current_selection = selection
        if self.on_create_dataset is not None:
            self.create_dataset_button.configure(state="normal")

    def _open_selection_dataset_dialog(self) -> None:
        if self.current_selection is None or self.on_create_dataset is None:
            return
        BoldSelectionDatasetDialog(
            self,
            self.current_selection,
            on_create_dataset=self.on_create_dataset,
        )


def _format_hits(query_id: str, hits: tuple[BoldHit, ...]) -> str:
    if not hits:
        return f"Query: {query_id}\n\nNo hits."
    sections = []
    for rank, hit in enumerate(hits, start=1):
        sections.append(
            "\n".join(
                (
                    f"Query: {query_id}",
                    f"Rank: {rank}",
                    f"Species: {hit.species_name or '-'}",
                    f"Genus: {hit.genus or '-'}",
                    f"Family: {hit.family or '-'}",
                    f"Order: {hit.order or '-'}",
                    f"Phylum: {hit.phylum or '-'}",
                    f"Similarity: {hit.similarity if hit.similarity is not None else '-'}",
                    f"BIN: {hit.bin_uri or '-'}",
                    f"Process ID: {hit.process_id or '-'}",
                    f"Record ID: {hit.record_id or '-'}",
                    f"Country: {hit.country or '-'}",
                    f"Institution: {hit.institution or '-'}",
                    f"Specimen ID: {hit.specimen_id or '-'}",
                    f"Collection date: {hit.collection_date or '-'}",
                    f"Database: {hit.database}",
                )
            )
        )
    return "\n\n".join(sections)
