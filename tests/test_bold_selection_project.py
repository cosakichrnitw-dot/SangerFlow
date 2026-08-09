"""Tests for adding BOLD-selection datasets to immutable Projects."""

from __future__ import annotations

import unittest

from core.bold_filter import BoldResultSelection
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.bold_selection_dataset import create_dataset_from_bold_selection
from workflow.bold_selection_project import (
    add_bold_selection_dataset_to_project,
    create_project_dataset_from_bold_selection,
)


def make_source() -> SequenceDataset:
    base = SequenceDataset.from_sequence_pairs(
        "coi-trimmed",
        "COI trimmed",
        SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )
    return SequenceDataset(
        base.dataset_id, base.name, base.source_type, base.records, metadata={"bold_result_id": "coi-bold"}
    )


class BoldSelectionProjectTests(unittest.TestCase):
    def test_adds_subset_dataset_with_lineage_metadata_and_immutable_inputs(self) -> None:
        source = make_source()
        selection = BoldResultSelection("coi-bold", ("IK346",))
        subset = create_dataset_from_bold_selection(
            source, selection, dataset_id="selected", name="Selected COI"
        )
        project = Project.create("project", "Project").add_dataset(source)
        updated = add_bold_selection_dataset_to_project(project, subset, metadata={"note": "reviewed"})

        self.assertEqual(project.dataset_ids, ("coi-trimmed",))
        self.assertEqual(updated.dataset_ids, ("coi-trimmed", "selected"))
        entry = updated.get_entry("selected")
        self.assertEqual(entry.parent_dataset_id, "coi-trimmed")
        self.assertEqual(entry.derivation_type, DerivationType.SUBSET_FROM_DATASET)
        self.assertEqual(entry.metadata["created_by"], "BOLD Selection")
        self.assertEqual(entry.metadata["derivation_detail"], "BOLD_SELECTION")
        self.assertEqual(entry.metadata["bold_result_id"], "coi-bold")
        self.assertEqual(entry.metadata["note"], "reviewed")
        self.assertEqual(updated.lineage("selected"), ("coi-trimmed", "selected"))
        self.assertEqual(source.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(subset.sequence_ids, ("IK346",))

    def test_convenience_workflow_creates_and_adds_subset(self) -> None:
        source = make_source()
        selection = BoldResultSelection("coi-bold", ("IK345",))
        project = Project.create("project", "Project").add_dataset(source)

        updated = create_project_dataset_from_bold_selection(
            project,
            source,
            selection,
            dataset_id="r-australiae",
            name="R. australiae",
        )

        self.assertEqual(updated.dataset_ids, ("coi-trimmed", "r-australiae"))
        self.assertEqual(updated.get_dataset("r-australiae").sequence_ids, ("IK345",))

    def test_rejects_non_selection_dataset_and_missing_parent(self) -> None:
        source = make_source()
        project = Project.create("project", "Project")
        with self.assertRaisesRegex(ValueError, "derived_from"):
            add_bold_selection_dataset_to_project(project, source)

        selection = BoldResultSelection("coi-bold", ("IK345",))
        subset = create_dataset_from_bold_selection(
            source, selection, dataset_id="subset", name="Subset"
        )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            add_bold_selection_dataset_to_project(project, subset)
