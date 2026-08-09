"""Tests for the BOLD filter dialog state and minimal Tk form."""

from __future__ import annotations

import os
import tkinter as tk
import unittest

from core.bold_result import BoldHit, BoldResultDataset
from gui.bold_filter_dialog import BoldFilterDialog, BoldFilterDialogError, BoldFilterDialogState


def make_result() -> BoldResultDataset:
    return BoldResultDataset(
        "coi-bold", "COI BOLD", "coi-trimmed", "COI", "BOLD",
        (
            BoldHit("IK345", species_name="Rhynchobatus australiae", genus="Rhynchobatus", bin_uri="BOLD:AAA", similarity=99.5, database="BOLD"),
            BoldHit("IK346", species_name="Dasyatis kuhlii", genus="Dasyatis", bin_uri="BOLD:BBB", similarity=95.0, database="BOLD"),
        ),
    )


class BoldFilterDialogStateTests(unittest.TestCase):
    def test_builds_filter_and_selection_from_species_bin_and_similarity_fields(self) -> None:
        state = BoldFilterDialogState(make_result())
        species = state.apply(species_name="Rhynchobatus australiae")
        by_bin = state.apply(bin_uri="BOLD:BBB")
        by_similarity = state.apply(minimum_similarity="99")

        self.assertEqual(species.selected_query_ids, ("IK345",))
        self.assertEqual(by_bin.selected_query_ids, ("IK346",))
        self.assertEqual(by_similarity.selected_query_ids, ("IK345",))
        self.assertEqual(state.build_filter(genus="Rhynchobatus").genus, "Rhynchobatus")

    def test_rejects_invalid_numeric_input_and_empty_results(self) -> None:
        state = BoldFilterDialogState(make_result())
        with self.assertRaisesRegex(BoldFilterDialogError, "minimum_similarity"):
            state.build_filter(minimum_similarity="not-a-number")
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            BoldFilterDialogState(BoldResultDataset("empty", "Empty", "input", None, "BOLD", ()))


class BoldFilterDialogTests(unittest.TestCase):
    def test_apply_callback_and_cancel_when_tk_is_available(self) -> None:
        if not os.environ.get("DISPLAY"):
            self.skipTest("Tk display unavailable")
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            received = []
            dialog = BoldFilterDialog(root, make_result(), on_selection_created=received.append)
            dialog._species_name_var.set("Rhynchobatus australiae")
            selection = dialog.apply()
            self.assertEqual(selection.selected_query_ids, ("IK345",))
            self.assertEqual(received, [selection])

            cancelled = BoldFilterDialog(root, make_result(), on_selection_created=received.append)
            cancelled.cancel()
            self.assertEqual(received, [selection])
        finally:
            root.destroy()
