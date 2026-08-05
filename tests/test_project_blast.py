"""Tests for adding immutable BLAST result payloads to a Project."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.analysis_result import AnalysisResultType
from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.project_blast import add_blast_result_to_project


def make_input_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-trimmed",
        "COI trimmed",
        SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"),),
    )


def make_blast_result() -> BlastResultDataset:
    return BlastResultDataset(
        result_id="coi-identification-blast",
        name="COI identification BLAST",
        hits=(
            BlastHit(
                query_id="IK345",
                hit_accession="AB123456",
                scientific_name="Rhynchobatus australiae",
                organism="Rhynchobatus australiae",
                identity=99.5,
                query_coverage=98.0,
                evalue=1e-50,
                alignment_length=658,
                database="nt",
            ),
        ),
        parent_dataset_id="coi-trimmed",
        analysis_mode=BlastAnalysisMode.IDENTIFICATION,
        marker="COI",
        database="nt",
    )


class ProjectBlastTests(unittest.TestCase):
    def test_adds_blast_result_as_a_project_analysis_entry(self) -> None:
        input_dataset = make_input_dataset()
        blast_result = make_blast_result()
        project = Project.create("project", "Project").add_dataset(input_dataset)

        updated = add_blast_result_to_project(
            project,
            blast_result,
            display_name="COI identification",
            metadata={"run_label": "August validation"},
        )

        self.assertEqual(project.analysis_result_count, 0)
        self.assertEqual(updated.analysis_result_count, 1)
        self.assertEqual(updated.analysis_result_ids, ("coi-identification-blast",))
        stored = updated.get_analysis_result("coi-identification-blast")
        self.assertEqual(stored.result_type, AnalysisResultType.BLAST)
        self.assertEqual(stored.parent_dataset_id, "coi-trimmed")
        self.assertEqual(
            updated.analysis_lineage("coi-identification-blast"),
            ("coi-trimmed", "coi-identification-blast"),
        )
        entry = updated.get_analysis_entry("coi-identification-blast")
        self.assertEqual(entry.display_name, "COI identification")
        self.assertEqual(entry.metadata["added_by"], "BLAST Workflow")
        self.assertEqual(entry.metadata["run_label"], "August validation")

    def test_preserves_original_project_and_blast_result(self) -> None:
        input_dataset = make_input_dataset()
        blast_result = make_blast_result()
        project = Project.create("project", "Project").add_dataset(input_dataset)
        updated = add_blast_result_to_project(project, blast_result)

        self.assertEqual(project.dataset_ids, ("coi-trimmed",))
        self.assertEqual(project.analysis_result_ids, ())
        self.assertIs(updated.get_dataset("coi-trimmed"), input_dataset)
        self.assertEqual(blast_result.hit_count(), 1)
        self.assertEqual(blast_result.parent_dataset_id, "coi-trimmed")
        with self.assertRaises(FrozenInstanceError):
            blast_result.name = "changed"  # type: ignore[misc]

    def test_rejects_non_blast_results_and_missing_parent_dataset(self) -> None:
        project = Project.create("project", "Project")
        with self.assertRaisesRegex(ValueError, "BlastResultDataset"):
            add_blast_result_to_project(project, object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "parent_dataset_id does not exist"):
            add_blast_result_to_project(project, make_blast_result())
        with self.assertRaisesRegex(ValueError, "project must be"):
            add_blast_result_to_project(object(), make_blast_result())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
