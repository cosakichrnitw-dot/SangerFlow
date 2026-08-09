"""Input-only Tk dialog for a dataset requested from a BOLD selection."""

from __future__ import annotations

from typing import Callable, Optional
import tkinter as tk
from tkinter import ttk

from core.bold_filter import BoldResultSelection


class BoldSelectionDatasetDialogError(ValueError):
    """A user-facing validation error with no dataset or Project mutation."""


CreateDatasetCallback = Callable[[BoldResultSelection, str, str], None]


class BoldSelectionDatasetDialogState:
    """GUI-independent validation for the BOLD dataset-request form."""

    def __init__(self, selection: BoldResultSelection) -> None:
        if not isinstance(selection, BoldResultSelection):
            raise ValueError("selection must be a BoldResultSelection")
        if not selection.selected_query_ids:
            raise ValueError("selection must contain at least one query_id")
        self.selection = selection

    @property
    def selected_sequence_count(self) -> int:
        return len(self.selection.selected_query_ids)

    def validate_request(self, dataset_id: str, name: str) -> tuple[str, str]:
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise BoldSelectionDatasetDialogError("Dataset ID is required")
        if not isinstance(name, str) or not name.strip():
            raise BoldSelectionDatasetDialogError("Dataset Name is required")
        return dataset_id.strip(), name.strip()


class BoldSelectionDatasetDialog(tk.Toplevel):
    """Collect a name and ID, then delegate BOLD subset creation to a callback."""

    def __init__(
        self,
        master: tk.Misc | None,
        selection: BoldResultSelection,
        *,
        on_create_dataset: Optional[CreateDatasetCallback] = None,
    ) -> None:
        if on_create_dataset is not None and not callable(on_create_dataset):
            raise ValueError("on_create_dataset must be callable or None")
        super().__init__(master)
        self.state = BoldSelectionDatasetDialogState(selection)
        self.on_create_dataset = on_create_dataset
        self._dataset_id_var = tk.StringVar(value="")
        self._name_var = tk.StringVar(value="")
        self._message_var = tk.StringVar(value="Enter an ID and name for the selected sequences.")

        self.title("Create Dataset from BOLD Selection")
        self.resizable(True, False)
        self.transient(master)
        self._build_layout()

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)

        ttk.Label(content, text="Selected sequences:").grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(content, text=str(self.state.selected_sequence_count)).grid(
            row=0, column=1, sticky="w", pady=(0, 8)
        )
        ttk.Label(content, text="Dataset ID:").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(content, textvariable=self._dataset_id_var, width=34).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Label(content, text="Dataset Name:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(content, textvariable=self._name_var, width=34).grid(row=2, column=1, sticky="ew", pady=3)

        footer = ttk.Frame(content)
        footer.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(footer, textvariable=self._message_var, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(footer, text="Create", command=self.create).pack(side="right", padx=(0, 6))

    def create(self) -> tuple[BoldResultSelection, str, str] | None:
        """Publish a validated create request without performing workflow work."""

        try:
            dataset_id, name = self.state.validate_request(
                self._dataset_id_var.get(), self._name_var.get()
            )
            if self.on_create_dataset is None:
                raise BoldSelectionDatasetDialogError("no dataset-create callback is configured")
            self.on_create_dataset(self.state.selection, dataset_id, name)
        except (BoldSelectionDatasetDialogError, ValueError) as error:
            self._message_var.set(str(error))
            return None
        request = (self.state.selection, dataset_id, name)
        self.destroy()
        return request

    def cancel(self) -> None:
        """Close without publishing a request."""

        self.destroy()
