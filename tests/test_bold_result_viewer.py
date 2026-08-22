"""Tests for the read-only BOLD result ViewModel and Tk viewer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import os
import tkinter as tk
import unittest

import pytest

from core.bold_filter import BoldResultSelection
from core.bold_result import BoldHit, BoldResultDataset
from gui.bold_result_view_model import BoldResultSummaryRow, BoldResultViewModel
from gui.bold_result_viewer import BoldResultViewer


def make_result() -> BoldResultDataset:
    return BoldResultDataset(
        result_id="coi-bold",
        name="COI BOLD",
        parent_dataset_id="coi-trimmed",
        marker="COI",
        database="BOLD",
        hits=(
            BoldHit(
                query_id="IK345", process_id="BOLD:AAA001", species_name="Rhynchobatus australiae",
                genus="Rhynchobatus", family="Rhinidae", bin_uri="BOLD:AAA001",
                similarity=99.4, database="BOLD", country="Indonesia", institution="Museum A",
            ),
            BoldHit(
                query_id="IK345", process_id="BOLD:AAA002", species_name="Rhynchobatus palpebratus",
                genus="Rhynchobatus", similarity=97.3, database="BOLD",
            ),
            BoldHit(
                query_id="IK346", process_id="BOLD:BBB001", species_name="Rhynchobatus palpebratus",
                genus="Rhynchobatus", similarity=98.8, database="BOLD",
            ),
        ),
    )


class BoldResultViewModelTests(unittest.TestCase):
    def test_creates_summary_rows_for_multiple_queries_and_exposes_hits(self) -> None:
        result = make_result()
        view_model = BoldResultViewModel.from_result(result)

        rows = view_model.summary_rows()
        self.assertEqual(len(rows), 2)
        self.assertIsInstance(rows[0], BoldResultSummaryRow)
        self.assertEqual(rows[0].query_id, "IK345")
        self.assertEqual(rows[0].species_name, "Rhynchobatus australiae")
        self.assertEqual(rows[0].similarity, 99.4)
        self.assertEqual(rows[1].query_id, "IK346")
        self.assertEqual(
            tuple(hit.process_id for hit in view_model.get_hits("IK345")),
            ("BOLD:AAA001", "BOLD:AAA002"),
        )
        self.assertEqual(view_model.get_hits("missing"), ())

    def test_rejects_invalid_or_empty_results_without_mutating_source(self) -> None:
        result = make_result()
        empty = BoldResultDataset("empty", "Empty", "input", None, "BOLD", ())
        with self.assertRaisesRegex(ValueError, "BoldResultDataset"):
            BoldResultViewModel.from_result(object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            BoldResultViewModel.from_result(empty)
        self.assertEqual(result.hit_count(), 3)
        with self.assertRaises(FrozenInstanceError):
            result.name = "changed"  # type: ignore[misc]


@pytest.mark.legacy_tk
@unittest.skipUnless(
    os.environ.get("SANGERFLOW_RUN_LEGACY_TK") == "1",
    "legacy Tkinter native tests require SANGERFLOW_RUN_LEGACY_TK=1",
)
class BoldResultViewerTests(unittest.TestCase):
    def test_gui_creation_and_query_selection_when_tk_is_available(self) -> None:
        # In the headless macOS test runner, creating and tearing down a Tk
        # This explicit native tier can run on macOS Aqua as well as X11.
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            received = []
            created = []
            viewer = BoldResultViewer(
                root,
                make_result(),
                on_selection_created=received.append,
                on_create_dataset=lambda *args: created.append(args),
            )
            self.assertEqual(str(viewer.create_dataset_button.cget("state")), "disabled")
            self.assertEqual(len(viewer.summary_table.get_children()), 2)
            viewer.select_query("IK345")
            detail = viewer.detail.get("1.0", "end")
            self.assertIn("Process ID: BOLD:AAA001", detail)
            self.assertIn("BIN: BOLD:AAA001", detail)
            selection = BoldResultSelection("coi-bold", ("IK345",))
            viewer.submit_selection(selection)
            self.assertIs(viewer.current_selection, selection)
            self.assertEqual(received, [selection])
            viewer._accept_filter_selection(selection)
            self.assertIs(viewer.current_selection, selection)
            self.assertEqual(received, [selection, selection])
            self.assertEqual(str(viewer.create_dataset_button.cget("state")), "normal")
            viewer._open_filter_dialog()
            dialogs = [child for child in viewer.winfo_children() if child.winfo_class() == "Toplevel"]
            self.assertEqual(len(dialogs), 1)
            dialogs[0].destroy()
            viewer._open_selection_dataset_dialog()
            dialogs = [child for child in viewer.winfo_children() if child.winfo_class() == "Toplevel"]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            dialog._dataset_id_var.set("selected")  # type: ignore[attr-defined]
            dialog._name_var.set("Selected")  # type: ignore[attr-defined]
            dialog.create()  # type: ignore[attr-defined]
            self.assertEqual(created, [(selection, "selected", "Selected")])
            with self.assertRaises(KeyError):
                viewer.select_query("missing")
            viewer.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
