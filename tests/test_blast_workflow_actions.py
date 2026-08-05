"""Tests for callback-only BLAST GUI/application connections."""

from __future__ import annotations

import unittest

from core.blast_filter import BlastResultSelection
from core.blast_result import BlastHit, BlastResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from gui.blast_workflow_actions import (
    BlastWorkflowActionError,
    create_project_dataset_from_blast_viewer_selection,
    open_project_blast_result,
)
from workflow.project_blast import add_blast_result_to_project


def make_source() -> SequenceDataset:
    base = SequenceDataset.from_sequence_pairs(
        "coi-trimmed", "COI trimmed", SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )
    return SequenceDataset(base.dataset_id, base.name, base.source_type, base.records, {"blast_result_id": "coi-blast"})


def make_blast_result() -> BlastResultDataset:
    return BlastResultDataset(
        "coi-blast", "COI BLAST",
        (BlastHit("IK345", "AB123", "Rhynchobatus australiae", "Rhynchobatus australiae", 99.5, 98.0, 1e-50, 658, "nt"),),
        "coi-trimmed",
    )


class BlastWorkflowActionTests(unittest.TestCase):
    def test_opens_project_blast_result_through_resolver_and_viewer_callback(self) -> None:
        source = make_source()
        blast_result = make_blast_result()
        project = add_blast_result_to_project(
            Project.create("project", "Project").add_dataset(source), blast_result
        )
        opened: list[BlastResultDataset] = []

        result = open_project_blast_result(
            project,
            "coi-blast",
            resolve_blast_result=lambda result_id: blast_result if result_id == "coi-blast" else None,  # type: ignore[return-value]
            on_open_blast_result=opened.append,
        )

        self.assertIs(result, blast_result)
        self.assertEqual(opened, [blast_result])
        self.assertEqual(project.analysis_result_ids, ("coi-blast",))

    def test_open_rejects_missing_non_blast_or_mismatched_payloads(self) -> None:
        source = make_source()
        project = Project.create("project", "Project").add_dataset(source)
        with self.assertRaisesRegex(BlastWorkflowActionError, "unknown"):
            open_project_blast_result(
                project, "missing", resolve_blast_result=lambda _: make_blast_result(), on_open_blast_result=lambda _: None
            )
        blast_result = make_blast_result()
        project = add_blast_result_to_project(project, blast_result)
        wrong = BlastResultDataset("other", "Other", blast_result.hits, "coi-trimmed")
        with self.assertRaisesRegex(BlastWorkflowActionError, "does not match"):
            open_project_blast_result(
                project, "coi-blast", resolve_blast_result=lambda _: wrong, on_open_blast_result=lambda _: None
            )

    def test_selection_dataset_entry_calls_project_changed_callback(self) -> None:
        source = make_source()
        project = Project.create("project", "Project").add_dataset(source)
        changed: list[Project] = []
        updated = create_project_dataset_from_blast_viewer_selection(
            project,
            source,
            BlastResultSelection("coi-blast", ("IK346",)),
            dataset_id="selected",
            name="Selected",
            on_project_changed=changed.append,
        )

        self.assertEqual(updated.dataset_ids, ("coi-trimmed", "selected"))
        self.assertEqual(changed, [updated])
        self.assertEqual(project.dataset_ids, ("coi-trimmed",))
