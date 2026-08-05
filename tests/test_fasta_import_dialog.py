"""Tests for FASTA import dialog state without requiring a native Tk display."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.fasta_dataset import FastaOpenMode
from core.project import Project
from core.sequence_dataset import SourceType
from gui.fasta_import_dialog import FastaImportDialogState, FastaImportError


class FastaImportDialogStateTests(unittest.TestCase):
    def write_fasta(self, directory: str, filename: str, content: str) -> Path:
        path = Path(directory) / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_auto_import_adds_dataset_and_notifies_callback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "samples.fasta", ">A\natgc\n>B\nATGTA\n")
            state = FastaImportDialogState(Project.create("project", "Project"))
            state.set_filepath(path)
            received_projects: list[Project] = []
            updated = state.import_dataset(
                dataset_name="Imported samples",
                open_mode=FastaOpenMode.AUTO,
                on_project_changed=received_projects.append,
            )

        self.assertEqual(updated.dataset_ids, ("samples",))
        self.assertEqual(updated.get_dataset("samples").name, "Imported samples")
        self.assertEqual(updated.get_dataset("samples").source_type, SourceType.IMPORTED_FASTA)
        self.assertEqual(received_projects, [updated])

    def test_alignment_mode_imports_alignment_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "aligned.fasta", ">A\nATG-C\n>B\nATGTC\n")
            state = FastaImportDialogState(Project.create("project", "Project"))
            state.set_filepath(path)
            updated = state.import_dataset(dataset_name="Existing alignment", open_mode="alignment")

        dataset = updated.get_dataset("aligned")
        self.assertEqual(dataset.source_type, SourceType.IMPORTED_ALIGNMENT)
        self.assertTrue(dataset.has_gaps)
        self.assertEqual(dataset.sequence_count, 2)

    def test_missing_file_selection_and_invalid_fasta_leave_project_unchanged(self) -> None:
        project = Project.create("project", "Project")
        state = FastaImportDialogState(project)
        with self.assertRaisesRegex(FastaImportError, "select a FASTA"):
            state.import_dataset(dataset_name="Name", open_mode="auto")
        state.set_filepath("missing.fasta")
        with self.assertRaisesRegex(FastaImportError, "does not exist"):
            state.import_dataset(dataset_name="Name", open_mode="auto")
        self.assertIs(state.project, project)

        with tempfile.TemporaryDirectory() as directory:
            invalid = self.write_fasta(directory, "invalid.fasta", ">A\nATUZ\n")
            state.set_filepath(invalid)
            with self.assertRaisesRegex(FastaImportError, "invalid DNA/IUPAC"):
                state.import_dataset(dataset_name="Invalid", open_mode="auto")
            empty = self.write_fasta(directory, "empty.fasta", "")
            state.set_filepath(empty)
            with self.assertRaisesRegex(FastaImportError, "no records"):
                state.import_dataset(dataset_name="Empty", open_mode="auto")
        self.assertIs(state.project, project)

    def test_duplicate_record_and_duplicate_dataset_id_leave_project_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate_records = self.write_fasta(directory, "duplicate.fasta", ">A\nATGC\n>A\nATGT\n")
            source = self.write_fasta(directory, "source.fasta", ">A\nATGC\n")
            state = FastaImportDialogState(Project.create("project", "Project"))
            state.set_filepath(duplicate_records)
            with self.assertRaisesRegex(FastaImportError, "duplicate"):
                state.import_dataset(dataset_name="Duplicate records", open_mode="auto")
            self.assertEqual(state.project.dataset_count, 0)

            state.set_filepath(source)
            first = state.import_dataset(dataset_name="Source", open_mode="auto")
            state.set_filepath(source)
            with self.assertRaisesRegex(FastaImportError, "already exists"):
                state.import_dataset(dataset_name="Source again", open_mode="auto")
        self.assertEqual(state.project, first)

    def test_cancel_has_no_state_operation_and_dataset_name_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "samples.fasta", ">A\nATGC\n")
            project = Project.create("project", "Project")
            state = FastaImportDialogState(project)
            state.set_filepath(path)
            with self.assertRaisesRegex(FastaImportError, "Dataset Name"):
                state.import_dataset(dataset_name="", open_mode="auto")
        self.assertIs(state.project, project)


if __name__ == "__main__":
    unittest.main()
