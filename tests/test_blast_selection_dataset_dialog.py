"""Tests for the input-only BLAST-selection dataset dialog."""

from __future__ import annotations

import os
import tkinter as tk
import unittest

import pytest

from core.blast_filter import BlastResultSelection
from gui.blast_selection_dataset_dialog import (
    BlastSelectionDatasetDialog,
    BlastSelectionDatasetDialogError,
    BlastSelectionDatasetDialogState,
)


class BlastSelectionDatasetDialogStateTests(unittest.TestCase):
    def test_exposes_selected_count_and_validates_dataset_request(self) -> None:
        selection = BlastResultSelection("coi-blast", ("IK345", "IK346"))
        state = BlastSelectionDatasetDialogState(selection)

        self.assertEqual(state.selected_sequence_count, 2)
        self.assertEqual(state.validate_request(" selected-coi ", " Selected COI "), ("selected-coi", "Selected COI"))
        with self.assertRaisesRegex(BlastSelectionDatasetDialogError, "Dataset ID"):
            state.validate_request("", "Selected")
        with self.assertRaisesRegex(BlastSelectionDatasetDialogError, "Dataset Name"):
            state.validate_request("selected", "")

    def test_rejects_empty_or_invalid_selection(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            BlastSelectionDatasetDialogState(BlastResultSelection("coi-blast", ()))
        with self.assertRaisesRegex(ValueError, "BlastResultSelection"):
            BlastSelectionDatasetDialogState(object())  # type: ignore[arg-type]


@pytest.mark.legacy_tk
@unittest.skipUnless(
    os.environ.get("SANGERFLOW_RUN_LEGACY_TK") == "1",
    "legacy Tkinter native tests require SANGERFLOW_RUN_LEGACY_TK=1",
)
class BlastSelectionDatasetDialogTests(unittest.TestCase):
    def test_create_callback_and_cancel_when_tk_is_available(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            selection = BlastResultSelection("coi-blast", ("IK345", "IK346"))
            received = []
            dialog = BlastSelectionDatasetDialog(root, selection, on_create_dataset=lambda *args: received.append(args))
            dialog._dataset_id_var.set("selected-coi")
            dialog._name_var.set("Selected COI")
            request = dialog.create()
            self.assertEqual(request, (selection, "selected-coi", "Selected COI"))
            self.assertEqual(received, [(selection, "selected-coi", "Selected COI")])

            cancelled = BlastSelectionDatasetDialog(root, selection, on_create_dataset=lambda *args: received.append(args))
            cancelled.cancel()
            self.assertEqual(len(received), 1)
        finally:
            root.destroy()
