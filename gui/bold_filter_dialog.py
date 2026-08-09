"""Tk dialog for creating an immutable selection from a BOLD result."""

from __future__ import annotations

from typing import Callable, Optional
import tkinter as tk
from tkinter import ttk

from core.bold_filter import BoldResultFilter, BoldResultSelection, apply_bold_filter
from core.bold_result import BoldResultDataset


class BoldFilterDialogError(ValueError):
    """A validation error that leaves immutable BOLD values unchanged."""


SelectionCreatedCallback = Callable[[BoldResultSelection], None]


class BoldFilterDialogState:
    """GUI-independent conversion from BOLD filter fields to a selection."""

    def __init__(self, bold_result: BoldResultDataset) -> None:
        if not isinstance(bold_result, BoldResultDataset):
            raise ValueError("bold_result must be a BoldResultDataset")
        if not bold_result.hits:
            raise ValueError("bold_result must contain at least one hit to filter")
        self.bold_result = bold_result

    def build_filter(
        self,
        *,
        species_name: str = "",
        genus: str = "",
        family: str = "",
        bin_uri: str = "",
        country: str = "",
        minimum_similarity: str = "",
        first_hit_only: bool = True,
    ) -> BoldResultFilter:
        """Parse optional form values into the immutable BOLD filter."""

        try:
            return BoldResultFilter(
                species_name=_optional_text(species_name),
                genus=_optional_text(genus),
                family=_optional_text(family),
                bin_uri=_optional_text(bin_uri),
                country=_optional_text(country),
                min_similarity=_optional_number(minimum_similarity, "minimum_similarity"),
                top_hit_only=first_hit_only,
            )
        except ValueError as error:
            raise BoldFilterDialogError(str(error)) from error

    def apply(self, **kwargs: object) -> BoldResultSelection:
        return apply_bold_filter(self.bold_result, self.build_filter(**kwargs))


class BoldFilterDialog(tk.Toplevel):
    """Minimal form that creates and publishes a ``BoldResultSelection``."""

    def __init__(
        self,
        master: tk.Misc | None,
        bold_result: BoldResultDataset,
        *,
        on_selection_created: Optional[SelectionCreatedCallback] = None,
    ) -> None:
        if on_selection_created is not None and not callable(on_selection_created):
            raise ValueError("on_selection_created must be callable or None")
        super().__init__(master)
        self.state = BoldFilterDialogState(bold_result)
        self.on_selection_created = on_selection_created
        self._species_name_var = tk.StringVar(value="")
        self._genus_var = tk.StringVar(value="")
        self._family_var = tk.StringVar(value="")
        self._bin_uri_var = tk.StringVar(value="")
        self._country_var = tk.StringVar(value="")
        self._minimum_similarity_var = tk.StringVar(value="")
        self._first_hit_only_var = tk.BooleanVar(value=True)
        self._message_var = tk.StringVar(value="Leave a field blank to ignore that condition.")

        self.title("Filter BOLD Result")
        self.resizable(True, False)
        self.transient(master)
        self._build_layout()

    def _build_layout(self) -> None:
        content = ttk.Frame(self, padding=12)
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, weight=1)
        fields = (
            ("Species name (exact):", self._species_name_var),
            ("Genus (exact):", self._genus_var),
            ("Family (exact):", self._family_var),
            ("BIN URI (exact):", self._bin_uri_var),
            ("Country (contains):", self._country_var),
            ("Minimum similarity:", self._minimum_similarity_var),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(content, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            ttk.Entry(content, textvariable=variable, width=32).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Checkbutton(
            content,
            text="Use first hit only",
            variable=self._first_hit_only_var,
        ).grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(8, 0))

        footer = ttk.Frame(content)
        footer.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(footer, textvariable=self._message_var, anchor="w").pack(side="left", fill="x", expand=True)
        ttk.Button(footer, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(footer, text="Apply", command=self.apply).pack(side="right", padx=(0, 6))

    def apply(self) -> BoldResultSelection | None:
        """Apply fields, publish a selection, and close only on success."""

        try:
            selection = self.state.apply(
                species_name=self._species_name_var.get(),
                genus=self._genus_var.get(),
                family=self._family_var.get(),
                bin_uri=self._bin_uri_var.get(),
                country=self._country_var.get(),
                minimum_similarity=self._minimum_similarity_var.get(),
                first_hit_only=self._first_hit_only_var.get(),
            )
            if self.on_selection_created is not None:
                self.on_selection_created(selection)
        except (BoldFilterDialogError, ValueError) as error:
            self._message_var.set(str(error))
            return None
        self.destroy()
        return selection

    def cancel(self) -> None:
        """Close without creating a selection or changing the source result."""

        self.destroy()


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        raise BoldFilterDialogError("text fields must be strings")
    stripped = value.strip()
    return stripped or None


def _optional_number(value: object, field_name: str) -> float | None:
    if not isinstance(value, str):
        raise BoldFilterDialogError(f"{field_name} must be a number or blank")
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError as error:
        raise BoldFilterDialogError(f"{field_name} must be a number or blank") from error
