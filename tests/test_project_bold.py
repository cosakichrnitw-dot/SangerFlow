"""Tests for adding immutable BOLD result payloads to a Project."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.analysis_result import AnalysisResultType
from core.bold_result import BoldHit, BoldResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.project_bold import add_bold_result_to_project


def make_input_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-trimmed", "COI trimmed", SourceType.AB1_TRIMMED, (("IK345", "ATGC"),)
    )


def make_bold_result() -> BoldResultDataset:
    return BoldResultDataset(
        result_id="coi-bold",
        name="COI BOLD",
        parent_dataset_id="coi-trimmed",
        marker="COI",
        database="BOLD",
        hits=(
            BoldHit(
                query_id="IK345",
                process_id="BOLD:AAA001",
                species_name="Rhynchobatus australiae",
                similarity=99.4,
                database="BOLD",
            ),
        ),
    )


class ProjectBoldTests(unittest.TestCase):
    def test_adds_bold_result_as_a_project_analysis_entry(self) -> None:
        source = make_input_dataset()
        bold_result = make_bold_result()
        project = Project.create("project", "Project").add_dataset(source)

        updated = add_bold_result_to_project(
            project,
            bold_result,
            display_name="COI BOLD identification",
            metadata={"run_label": "August validation"},
        )

        self.assertEqual(project.analysis_result_count, 0)
        self.assertEqual(updated.analysis_result_ids, ("coi-bold",))
        stored = updated.get_analysis_result("coi-bold")
        self.assertEqual(stored.result_type, AnalysisResultType.BOLD)
        self.assertEqual(stored.parent_dataset_id, "coi-trimmed")
        self.assertEqual(updated.analysis_lineage("coi-bold"), ("coi-trimmed", "coi-bold"))
        entry = updated.get_analysis_entry("coi-bold")
        self.assertEqual(entry.display_name, "COI BOLD identification")
        self.assertEqual(entry.metadata["added_by"], "BOLD Workflow")
        self.assertEqual(entry.metadata["run_label"], "August validation")

    def test_preserves_source_project_dataset_and_bold_result(self) -> None:
        source = make_input_dataset()
        bold_result = make_bold_result()
        project = Project.create("project", "Project").add_dataset(source)
        updated = add_bold_result_to_project(project, bold_result)

        self.assertEqual(project.analysis_result_ids, ())
        self.assertIs(updated.get_dataset("coi-trimmed"), source)
        self.assertEqual(bold_result.hit_count(), 1)
        self.assertEqual(bold_result.hits[0].process_id, "BOLD:AAA001")
        with self.assertRaises(FrozenInstanceError):
            bold_result.name = "changed"  # type: ignore[misc]

    def test_rejects_invalid_project_parent_payload_and_empty_result(self) -> None:
        bold_result = make_bold_result()
        with self.assertRaisesRegex(ValueError, "BoldResultDataset"):
            add_bold_result_to_project(Project.create("project", "Project"), object())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "parent_dataset_id does not exist"):
            add_bold_result_to_project(Project.create("project", "Project"), bold_result)
        with self.assertRaisesRegex(ValueError, "project must"):
            add_bold_result_to_project(object(), bold_result)  # type: ignore[arg-type]
        empty = BoldResultDataset("empty", "Empty", "coi-trimmed", "COI", "BOLD", ())
        project = Project.create("project", "Project").add_dataset(make_input_dataset())
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            add_bold_result_to_project(project, empty)


if __name__ == "__main__":
    unittest.main()
