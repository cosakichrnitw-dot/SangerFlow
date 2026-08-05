"""Tests for Main Viewer trimmed-read dataset creation without creating Tk UI."""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from core.sequence_dataset import SourceType
from core.project import DerivationType, Project
from gui.main_window import MainWindow


def make_read(filename: str, trimmed_sequence: str):
    return SimpleNamespace(filename=filename, trimmed_sequence=trimmed_sequence)


class MainWindowSequenceDatasetTests(unittest.TestCase):
    def test_creates_trimmed_dataset_from_current_viewer_read_order(self) -> None:
        window = object.__new__(MainWindow)
        first = make_read("IK345_F.ab1", "atgc")
        second = make_read("IK346_R.ab1", "ATG-")
        window.selected_reads = [first, second]

        dataset = window.create_sequence_dataset("trimmed-demo", "Trimmed Demo")

        self.assertEqual(dataset.source_type, SourceType.AB1_TRIMMED)
        self.assertEqual(dataset.sequence_count, 2)
        self.assertEqual(dataset.sequence_ids, ("IK345_F", "IK346_R"))
        self.assertEqual(tuple(record.sequence for record in dataset.records), ("ATGC", "ATG-"))
        self.assertEqual(dataset.metadata["source"], "Main Viewer")
        self.assertEqual(dataset.metadata["read_count"], 2)
        self.assertEqual(dataset.metadata["creation_context"], "current Main Viewer trimmed reads")

    def test_explicit_reads_preserve_input_and_do_not_change_viewer_state(self) -> None:
        window = object.__new__(MainWindow)
        selected = [make_read("selected.ab1", "AAAA")]
        source_reads = [make_read("source-one.ab1", "ATGC"), make_read("source-two.ab1", "ATGT")]
        window.selected_reads = selected
        before = tuple((read.filename, read.trimmed_sequence) for read in source_reads)

        dataset = window.create_sequence_dataset(
            "explicit", "Explicit", reads=source_reads, creation_context="manual test input"
        )

        self.assertEqual(dataset.sequence_ids, ("source-one", "source-two"))
        self.assertEqual(tuple((read.filename, read.trimmed_sequence) for read in source_reads), before)
        self.assertIs(window.selected_reads, selected)
        self.assertEqual(dataset.metadata["creation_context"], "manual test input")

    def test_empty_trimmed_sequence_and_missing_viewer_reads_are_rejected(self) -> None:
        window = object.__new__(MainWindow)
        with self.assertRaisesRegex(ValueError, "No reads are loaded"):
            window.create_sequence_dataset("missing", "Missing")
        with self.assertRaisesRegex(ValueError, "trimmed_sequence is empty"):
            window.create_sequence_dataset(
                "empty", "Empty", reads=[make_read("empty.ab1", "")]
            )

    def test_duplicate_ids_from_existing_read_names_are_rejected(self) -> None:
        window = object.__new__(MainWindow)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            window.create_sequence_dataset(
                "duplicate",
                "Duplicate",
                reads=[make_read("same.ab1", "ATGC"), make_read("same.ab1", "ATGT")],
            )

    def test_adds_new_trimmed_dataset_to_external_project_and_notifies_callback(self) -> None:
        window = object.__new__(MainWindow)
        source_reads = [make_read("IK345_F.ab1", "ATGC"), make_read("IK346_F.ab1", "ATGT")]
        project = Project.create("project", "Project")
        received_projects: list[Project] = []

        updated = window.add_trimmed_sequence_dataset_to_project(
            project,
            "trimmed-main-viewer",
            "Main Viewer trimmed reads",
            reads=source_reads,
            on_project_changed=received_projects.append,
        )

        self.assertEqual(project.dataset_ids, ())
        self.assertEqual(updated.dataset_ids, ("trimmed-main-viewer",))
        dataset = updated.get_dataset("trimmed-main-viewer")
        self.assertEqual(dataset.sequence_ids, ("IK345_F", "IK346_F"))
        self.assertEqual(dataset.source_type, SourceType.AB1_TRIMMED)
        self.assertEqual(
            updated.get_entry("trimmed-main-viewer").derivation_type,
            DerivationType.TRIMMED_FROM_READS,
        )
        self.assertEqual(received_projects, [updated])
        self.assertEqual(tuple(read.trimmed_sequence for read in source_reads), ("ATGC", "ATGT"))

    def test_project_addition_rejects_duplicate_dataset_without_mutating_project(self) -> None:
        window = object.__new__(MainWindow)
        existing = window.create_sequence_dataset(
            "trimmed", "Existing", reads=[make_read("existing.ab1", "ATGC")]
        )
        project = Project.create("project", "Project").add_dataset(existing)

        with self.assertRaisesRegex(ValueError, "already exists"):
            window.add_trimmed_sequence_dataset_to_project(
                project,
                "trimmed",
                "Duplicate",
                reads=[make_read("new.ab1", "ATGT")],
            )
        self.assertEqual(project.dataset_ids, ("trimmed",))
        self.assertEqual(project.get_dataset("trimmed").sequence_ids, ("existing",))


if __name__ == "__main__":
    unittest.main()
