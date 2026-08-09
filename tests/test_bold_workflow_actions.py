"""Tests for callback-only BOLD Project-result opening."""

from __future__ import annotations

import unittest

from core.bold_filter import BoldResultSelection
from core.bold_result import BoldHit, BoldResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from gui.bold_workflow_actions import BoldWorkflowActionError, open_project_bold_result
from workflow.project_bold import add_bold_result_to_project


def make_source() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-trimmed", "COI trimmed", SourceType.AB1_TRIMMED, (("IK345", "ATGC"),)
    )


def make_result() -> BoldResultDataset:
    return BoldResultDataset(
        "coi-bold", "COI BOLD", "coi-trimmed", "COI", "BOLD",
        (BoldHit("IK345", process_id="BOLD:AAA", similarity=99.5, database="BOLD"),),
    )


class BoldWorkflowActionTests(unittest.TestCase):
    def test_resolves_a_project_bold_result_and_invokes_viewer_callback(self) -> None:
        source = make_source()
        bold_result = make_result()
        project = add_bold_result_to_project(Project.create("project", "Project").add_dataset(source), bold_result)
        opened: list[BoldResultDataset] = []

        result = open_project_bold_result(
            project,
            "coi-bold",
            resolve_bold_result=lambda result_id: bold_result if result_id == "coi-bold" else None,  # type: ignore[return-value]
            on_open_bold_result=opened.append,
        )

        self.assertIs(result, bold_result)
        self.assertEqual(opened, [bold_result])
        self.assertEqual(project.analysis_result_ids, ("coi-bold",))

    def test_rejects_missing_or_mismatched_bold_payloads(self) -> None:
        source = make_source()
        project = Project.create("project", "Project").add_dataset(source)
        with self.assertRaisesRegex(BoldWorkflowActionError, "unknown"):
            open_project_bold_result(
                project, "missing", resolve_bold_result=lambda _: make_result(), on_open_bold_result=lambda _: None
            )
        bold_result = make_result()
        project = add_bold_result_to_project(project, bold_result)
        wrong = BoldResultDataset("other", "Other", "coi-trimmed", "COI", "BOLD", bold_result.hits)
        with self.assertRaisesRegex(BoldWorkflowActionError, "does not match"):
            open_project_bold_result(
                project, "coi-bold", resolve_bold_result=lambda _: wrong, on_open_bold_result=lambda _: None
            )

    def test_selection_dataset_action_updates_only_the_returned_project(self) -> None:
        from gui.bold_workflow_actions import create_project_dataset_from_bold_viewer_selection

        source = make_source()
        project = Project.create("project", "Project").add_dataset(source)
        changed: list[Project] = []
        updated = create_project_dataset_from_bold_viewer_selection(
            project,
            source,
            BoldResultSelection("coi-bold", ("IK345",)),
            dataset_id="selected",
            name="Selected",
            on_project_changed=changed.append,
        )

        self.assertEqual(project.dataset_ids, ("coi-trimmed",))
        self.assertEqual(updated.dataset_ids, ("coi-trimmed", "selected"))
        self.assertEqual(changed, [updated])
