"""Tests for the standalone Project Dataset Manager demonstration launcher."""

from __future__ import annotations

from io import StringIO
import unittest

from core.project import DerivationType
from core.sequence_dataset import SourceType
from tools.launch_project_dataset_manager import (
    build_demo_project,
    report_open_dataset,
    report_open_datasets,
    report_project_changed,
    show_project_dataset_manager,
)


class ProjectDatasetManagerLauncherTests(unittest.TestCase):
    def test_demo_project_has_expected_datasets_and_derivation(self) -> None:
        project = build_demo_project()

        self.assertEqual(project.project_id, "sangerflow_demo")
        self.assertEqual(project.name, "SangerFlow Demo Project")
        self.assertEqual(
            project.dataset_ids,
            ("imported_fasta_demo", "alignment_demo", "reviewed_consensus_demo"),
        )
        self.assertEqual(project.get_dataset("imported_fasta_demo").sequence_count, 3)
        self.assertFalse(project.get_dataset("imported_fasta_demo").is_equal_length)
        self.assertEqual(project.get_dataset("alignment_demo").source_type, SourceType.IMPORTED_ALIGNMENT)
        self.assertTrue(project.get_dataset("alignment_demo").has_gaps)
        self.assertEqual(project.get_entry("alignment_demo").parent_dataset_id, "imported_fasta_demo")
        self.assertEqual(
            project.get_entry("alignment_demo").derivation_type,
            DerivationType.ALIGNED_WITH_MAFFT,
        )
        self.assertEqual(
            project.get_dataset("reviewed_consensus_demo").source_type,
            SourceType.REVIEWED_CONSENSUS,
        )

    def test_terminal_callbacks_report_selected_datasets_and_project_updates(self) -> None:
        project = build_demo_project()
        stream = StringIO()

        report_open_dataset(project.get_dataset("alignment_demo"), stream=stream)
        report_open_datasets(
            (
                project.get_dataset("imported_fasta_demo"),
                project.get_dataset("reviewed_consensus_demo"),
            ),
            stream=stream,
        )
        report_project_changed(project.remove_dataset("reviewed_consensus_demo"), stream=stream)

        self.assertEqual(
            stream.getvalue(),
            "Opened dataset:\n"
            "  alignment_demo\n"
            "  sequences: 3\n"
            "Opened datasets:\n"
            "  imported_fasta_demo (sequences: 3)\n"
            "  reviewed_consensus_demo (sequences: 2)\n"
            "Project changed:\n"
            "  datasets: 2\n",
        )

    def test_show_uses_hidden_root_manager_callbacks_and_mainloop(self) -> None:
        calls: list[object] = []

        class FakeRoot:
            def withdraw(self) -> None:
                calls.append("withdraw")

            def destroy(self) -> None:
                calls.append("destroy")

            def mainloop(self) -> None:
                calls.append("mainloop")

        class FakeWindow:
            def __init__(self, root, project, **callbacks) -> None:
                self.root = root
                self.project = project
                self.callbacks = callbacks
                calls.append(("window", project.dataset_count, sorted(callbacks)))

            def protocol(self, name, callback) -> None:
                self.name = name
                self.callback = callback
                calls.append(("protocol", name))

        show_project_dataset_manager(
            build_demo_project(),
            root_factory=FakeRoot,
            window_factory=FakeWindow,
        )

        self.assertEqual(
            calls,
            [
                "withdraw",
                (
                    "window",
                    3,
                    ["on_open_dataset", "on_open_datasets", "on_project_changed"],
                ),
                ("protocol", "WM_DELETE_WINDOW"),
                "mainloop",
            ],
        )


if __name__ == "__main__":
    unittest.main()
