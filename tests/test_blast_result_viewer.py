"""Tests for the read-only BLAST result ViewModel and Tk viewer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import os
import tkinter as tk
import unittest

import pytest

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.blast_filter import BlastResultSelection
from gui.blast_result_view_model import BlastResultSummaryRow, BlastResultViewModel
from gui.blast_result_viewer import BlastResultViewer


def make_result() -> BlastResultDataset:
    def hit(query_id: str, accession: str, identity: float) -> BlastHit:
        return BlastHit(
            query_id=query_id,
            hit_accession=accession,
            scientific_name="Rhynchobatus australiae",
            organism="Rhynchobatus australiae",
            identity=identity,
            query_coverage=98.0,
            evalue=1e-50,
            alignment_length=658,
            database="nt",
        )

    return BlastResultDataset(
        "coi-blast",
        "COI BLAST",
        (hit("IK345", "AB-first", 99.5), hit("IK345", "AB-second", 98.0), hit("IK346", "CD-first", 97.5)),
        "coi-trimmed",
        analysis_mode=BlastAnalysisMode.IDENTIFICATION,
        marker="COI",
        database="nt",
    )


class BlastResultViewModelTests(unittest.TestCase):
    def test_creates_summary_rows_for_multiple_queries_and_exposes_hits(self) -> None:
        result = make_result()
        view_model = BlastResultViewModel.from_result(result)

        rows = view_model.summary_rows()
        self.assertEqual(len(rows), 2)
        self.assertIsInstance(rows[0], BlastResultSummaryRow)
        self.assertEqual(rows[0].query_id, "IK345")
        self.assertEqual(rows[0].top_accession, "AB-first")
        self.assertEqual(rows[0].top_scientific_name, "Rhynchobatus australiae")
        self.assertEqual(rows[1].query_id, "IK346")
        self.assertEqual(tuple(hit.hit_accession for hit in view_model.get_hits("IK345")), ("AB-first", "AB-second"))
        self.assertEqual(view_model.get_hits("missing"), ())

    def test_rejects_invalid_or_empty_results_without_mutating_source(self) -> None:
        result = make_result()
        empty = BlastResultDataset("empty", "Empty", (), "input")
        with self.assertRaisesRegex(ValueError, "BlastResultDataset"):
            BlastResultViewModel.from_result(object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            BlastResultViewModel.from_result(empty)
        self.assertEqual(result.hit_count(), 3)
        with self.assertRaises(FrozenInstanceError):
            result.name = "changed"  # type: ignore[misc]


@pytest.mark.legacy_tk
@unittest.skipUnless(
    os.environ.get("SANGERFLOW_RUN_LEGACY_TK") == "1",
    "legacy Tkinter native tests require SANGERFLOW_RUN_LEGACY_TK=1",
)
class BlastResultViewerTests(unittest.TestCase):
    def test_gui_creation_and_query_selection_when_tk_is_available(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            received_selections: list[BlastResultSelection] = []
            viewer = BlastResultViewer(
                root,
                make_result(),
                on_selection_created=received_selections.append,
            )
            self.assertEqual(len(viewer.summary_table.get_children()), 2)
            viewer.select_query("IK345")
            self.assertIn("Accession: AB-first", viewer.detail.get("1.0", "end"))
            selection = BlastResultSelection("coi-blast", ("IK345",))
            viewer.submit_selection(selection)
            self.assertEqual(received_selections, [selection])
            with self.assertRaises(KeyError):
                viewer.select_query("missing")
            with self.assertRaisesRegex(ValueError, "does not match"):
                viewer.submit_selection(BlastResultSelection("other-result", ("IK345",)))
            viewer.destroy()
        finally:
            root.destroy()

    def test_viewer_connects_filter_selection_to_dataset_dialog_when_tk_is_available(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk display unavailable: {error}")
        root.withdraw()
        try:
            received = []
            viewer = BlastResultViewer(
                root,
                make_result(),
                on_create_dataset=lambda *args: received.append(args),
            )
            selection = BlastResultSelection("coi-blast", ("IK345",))
            viewer._accept_filter_selection(selection)
            self.assertIs(viewer.current_selection, selection)
            self.assertEqual(str(viewer.create_dataset_button.cget("state")), "normal")
            viewer._open_selection_dataset_dialog()
            dialogs = [child for child in viewer.winfo_children() if child.winfo_class() == "Toplevel"]
            self.assertEqual(len(dialogs), 1)
            dialog = dialogs[0]
            dialog._dataset_id_var.set("selected")  # type: ignore[attr-defined]
            dialog._name_var.set("Selected")  # type: ignore[attr-defined]
            dialog.create()  # type: ignore[attr-defined]
            self.assertEqual(received, [(selection, "selected", "Selected")])
            viewer.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
