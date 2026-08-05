"""Tests for adding BLAST-selection datasets to immutable Projects."""

from __future__ import annotations

import unittest

from core.blast_filter import BlastResultSelection
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.blast_selection_dataset import create_dataset_from_blast_selection
from workflow.blast_selection_project import (
    add_blast_selection_dataset_to_project,
    create_project_dataset_from_blast_selection,
)


def make_source() -> SequenceDataset:
    base = SequenceDataset.from_sequence_pairs(
        "coi-trimmed",
        "COI trimmed",
        SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )
    return SequenceDataset(
        base.dataset_id, base.name, base.source_type, base.records, metadata={"blast_result_id": "coi-blast"}
    )


class BlastSelectionProjectTests(unittest.TestCase):
    def test_adds_subset_dataset_with_project_lineage_and_preserves_inputs(self) -> None:
        source = make_source()
        selection = BlastResultSelection("coi-blast", ("IK346",))
        subset = create_dataset_from_blast_selection(
            source, selection, dataset_id="selected", name="Selected COI"
        )
        project = Project.create("project", "Project").add_dataset(source)
        updated = add_blast_selection_dataset_to_project(project, subset, metadata={"note": "reviewed"})

        self.assertEqual(project.dataset_ids, ("coi-trimmed",))
        self.assertEqual(updated.dataset_ids, ("coi-trimmed", "selected"))
        entry = updated.get_entry("selected")
        self.assertEqual(entry.parent_dataset_id, "coi-trimmed")
        self.assertEqual(entry.derivation_type, DerivationType.SUBSET_FROM_DATASET)
        self.assertEqual(entry.metadata["created_by"], "BLAST Selection")
        self.assertEqual(entry.metadata["derivation_detail"], "BLAST_SELECTION")
        self.assertEqual(entry.metadata["blast_result_id"], "coi-blast")
        self.assertEqual(entry.metadata["note"], "reviewed")
        self.assertEqual(updated.lineage("selected"), ("coi-trimmed", "selected"))
        self.assertEqual(source.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(subset.sequence_ids, ("IK346",))

    def test_convenience_workflow_creates_and_adds_subset(self) -> None:
        source = make_source()
        selection = BlastResultSelection("coi-blast", ("IK345",))
        project = Project.create("project", "Project").add_dataset(source)

        updated = create_project_dataset_from_blast_selection(
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
            add_blast_selection_dataset_to_project(project, source)

        selection = BlastResultSelection("coi-blast", ("IK345",))
        subset = create_dataset_from_blast_selection(
            source, selection, dataset_id="subset", name="Subset"
        )
        with self.assertRaisesRegex(ValueError, "does not exist"):
            add_blast_selection_dataset_to_project(project, subset)
