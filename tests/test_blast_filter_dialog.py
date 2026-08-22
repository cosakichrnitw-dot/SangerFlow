"""Tests for the BLAST filter dialog state and minimal Tk form."""

from __future__ import annotations

import os
import tkinter as tk
import unittest

import pytest

from core.blast_result import BlastHit, BlastResultDataset
from gui.blast_filter_dialog import BlastFilterDialog, BlastFilterDialogError, BlastFilterDialogState


def make_result() -> BlastResultDataset:
    return BlastResultDataset(
        "coi-blast", "COI BLAST",
        (
            BlastHit("IK345", "AB1", "Rhynchobatus australiae", "Rhynchobatus australiae", 99.5, 98.0, 1e-50, 658, "nt"),
            BlastHit("IK346", "AB2", "Dasyatis kuhlii", "Blue-spotted stingray", 95.0, 90.0, 1e-10, 658, "nt"),
        ),
        "coi-trimmed",
    )


class BlastFilterDialogStateTests(unittest.TestCase):
    def test_builds_filter_and_selection_from_form_values(self) -> None:
        state = BlastFilterDialogState(make_result())
        criteria = state.build_filter(scientific_name="Rhynchobatus australiae", min_identity="99")
        selection = state.apply(scientific_name="Rhynchobatus australiae", min_identity="99")

        self.assertEqual(criteria.scientific_name, "Rhynchobatus australiae")
        self.assertEqual(criteria.min_identity, 99.0)
        self.assertTrue(criteria.top_hit_only)
        self.assertEqual(selection.source_result_id, "coi-blast")
        self.assertEqual(selection.selected_query_ids, ("IK345",))

    def test_rejects_invalid_numeric_input_and_empty_results(self) -> None:
        state = BlastFilterDialogState(make_result())
        with self.assertRaisesRegex(BlastFilterDialogError, "min_coverage"):
            state.build_filter(min_coverage="not-a-number")
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            BlastFilterDialogState(BlastResultDataset("empty", "Empty", (), "input"))


@pytest.mark.legacy_tk
@unittest.skipUnless(
    os.environ.get("SANGERFLOW_RUN_LEGACY_TK") == "1",
    "legacy Tkinter native tests require SANGERFLOW_RUN_LEGACY_TK=1",
)
class BlastFilterDialogTests(unittest.TestCase):
    def test_apply_callback_and_cancel_when_tk_is_available(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            received = []
            dialog = BlastFilterDialog(root, make_result(), on_selection_created=received.append)
            dialog._scientific_name_var.set("Rhynchobatus australiae")
            selection = dialog.apply()
            self.assertEqual(selection.selected_query_ids, ("IK345",))
            self.assertEqual(received, [selection])

            cancelled = BlastFilterDialog(root, make_result(), on_selection_created=received.append)
            cancelled.cancel()
            self.assertEqual(received, [selection])
        finally:
            root.destroy()
