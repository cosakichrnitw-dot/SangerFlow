"""Tk dialog for creating an immutable selection from a BLAST result."""

from __future__ import annotations

from typing import Callable, Optional
import tkinter as tk
from tkinter import ttk

from core.blast_filter import BlastResultFilter, BlastResultSelection, apply_blast_filter
from core.blast_result import BlastResultDataset


class BlastFilterDialogError(ValueError):
    """A validation error that leaves immutable BLAST values unchanged."""


SelectionCreatedCallback = Callable[[BlastResultSelection], None]


class BlastFilterDialogState:
    """GUI-independent conversion from user text fields to filter selection."""

    def __init__(self, blast_result: BlastResultDataset) -> None:
        if not isinstance(blast_result, BlastResultDataset):
            raise ValueError("blast_result must be a BlastResultDataset")
        if not blast_result.hits:
            raise ValueError("blast_result must contain at least one hit to filter")
        self.blast_result = blast_result

    def build_filter(
        self,
        *,
        scientific_name: str = "",
        organism: str = "",
        min_identity: str = "",
        min_coverage: str = "",
        max_evalue: str = "",
        top_hit_only: bool = True,
    ) -> BlastResultFilter:
        """Parse optional form values into the existing immutable filter."""

        try:
            return BlastResultFilter(
                scientific_name=_optional_text(scientific_name),
                organism=_optional_text(organism),
                min_identity=_optional_number(min_identity, "min_identity"),
                min_coverage=_optional_number(min_coverage, "min_coverage"),
                max_evalue=_optional_number(max_evalue, "max_evalue"),
                top_hit_only=top_hit_only,
            )
        except ValueError as error:
            raise BlastFilterDialogError(str(error)) from error

    def apply(
        self,
        *,
        scientific_name: str = "",
        organism: str = "",
        min_identity: str = "",
        min_coverage: str = "",
        max_evalue: str = "",
        top_hit_only: bool = True,
    ) -> BlastResultSelection:
        criteria = self.build_filter(
            scientific_name=scientific_name,
            organism=organism,
            min_identity=min_identity,
            min_coverage=min_coverage,
            max_evalue=max_evalue,
            top_hit_only=top_hit_only,
        )
        return apply_blast_filter(self.blast_result, criteria)


class BlastFilterDialog(tk.Toplevel):
    """Minimal form that creates and publishes a ``BlastResultSelection``."""

    def __init__(
        self,
        master: tk.Misc | None,
        blast_result: BlastResultDataset,
        *,
        on_selection_created: Optional[SelectionCreatedCallback] = None,
    ) -> None:
        if on_selection_created is not None and not callable(on_selection_created):
            raise ValueError("on_selection_created must be callable or None")
        super().__init__(master)
        self.state = BlastFilterDialogState(blast_result)
        self.on_selection_created = on_selection_created
        self._scientific_name_var = tk.StringVar(value="")
        self._organism_var = tk.StringVar(value="")
        self._min_identity_var = tk.StringVar(value="")
        self._min_coverage_var = tk.StringVar(value="")
        self._max_evalue_var = tk.StringVar(value="")
        self._top_hit_only_var = tk.BooleanVar(value=True)
        self._message_var = tk.StringVar(value="Leave a field blank to ignore that condition.")

        self.title("Filter BLAST Result")
        self.resizable(True, False)
        self.transient(master)
        self._build_layout()

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)
        fields = (
            ("Scientific name (exact):", self._scientific_name_var),
            ("Organism (contains):", self._organism_var),
            ("Minimum identity:", self._min_identity_var),
            ("Minimum coverage:", self._min_coverage_var),
            ("Maximum E-value:", self._max_evalue_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(content, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(content, textvariable=variable, width=32).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(
            content,
            text="Use top hit only",
            variable=self._top_hit_only_var,
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))

        footer = ttk.Frame(content)
        footer.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(footer, textvariable=self._message_var, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(footer, text="Apply", command=self.apply).pack(side="right", padx=(0, 6))

    def apply(self) -> BlastResultSelection | None:
        """Apply fields, publish the selection, and close only on success."""

        try:
            selection = self.state.apply(
                scientific_name=self._scientific_name_var.get(),
                organism=self._organism_var.get(),
                min_identity=self._min_identity_var.get(),
                min_coverage=self._min_coverage_var.get(),
                max_evalue=self._max_evalue_var.get(),
                top_hit_only=self._top_hit_only_var.get(),
            )
            if self.on_selection_created is not None:
                self.on_selection_created(selection)
        except (BlastFilterDialogError, ValueError) as error:
            self._message_var.set(str(error))
            return None
        self.destroy()
        return selection

    def cancel(self) -> None:
        """Close without creating a selection or changing the source result."""

        self.destroy()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        raise BlastFilterDialogError("text fields must be strings")
    stripped = value.strip()
    return stripped or None


def _optional_number(value: object, field_name: str) -> float | None:
    if not isinstance(value, str):
        raise BlastFilterDialogError(f"{field_name} must be a number or blank")
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError as error:
        raise BlastFilterDialogError(f"{field_name} must be a number or blank") from error
