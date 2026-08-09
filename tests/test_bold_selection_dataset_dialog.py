"""Tests for the input-only BOLD-selection dataset dialog."""

from __future__ import annotations

import os
import tkinter as tk
import unittest

from core.bold_filter import BoldResultSelection
from gui.bold_selection_dataset_dialog import (
    BoldSelectionDatasetDialog,
    BoldSelectionDatasetDialogError,
    BoldSelectionDatasetDialogState,
)


class BoldSelectionDatasetDialogStateTests(unittest.TestCase):
    def test_exposes_selected_count_and_validates_dataset_request(self) -> None:
        selection = BoldResultSelection("coi-bold", ("IK345", "IK346"))
        state = BoldSelectionDatasetDialogState(selection)

        self.assertEqual(state.selected_sequence_count, 2)
        self.assertEqual(
            state.validate_request(" selected-coi ", " Selected COI "),
            ("selected-coi", "Selected COI"),
        )
        with self.assertRaisesRegex(BoldSelectionDatasetDialogError, "Dataset ID"):
            state.validate_request("", "Selected")
        with self.assertRaisesRegex(BoldSelectionDatasetDialogError, "Dataset Name"):
            state.validate_request("selected", "")

    def test_rejects_empty_or_invalid_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            BoldSelectionDatasetDialogState(BoldResultSelection("coi-bold", ()))
        with self.assertRaisesRegex(ValueError, "BoldResultSelection"):
            BoldSelectionDatasetDialogState(object())  # type: ignore[arg-type]


class BoldSelectionDatasetDialogTests(unittest.TestCase):
    def test_create_callback_and_cancel_when_tk_is_available(self) -> None:
        if not os.environ.get("DISPLAY"):
            self.skipTest("Tk display unavailable")
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            selection = BoldResultSelection("coi-bold", ("IK345", "IK346"))
            received = []
            dialog = BoldSelectionDatasetDialog(root, selection, on_create_dataset=lambda *args: received.append(args))
            dialog._dataset_id_var.set("selected-coi")
            dialog._name_var.set("Selected COI")
            request = dialog.create()
            self.assertEqual(request, (selection, "selected-coi", "Selected COI"))
            self.assertEqual(received, [(selection, "selected-coi", "Selected COI")])

            cancelled = BoldSelectionDatasetDialog(root, selection, on_create_dataset=lambda *args: received.append(args))
            cancelled.cancel()
            self.assertEqual(len(received), 1)
        finally:
            root.destroy()
