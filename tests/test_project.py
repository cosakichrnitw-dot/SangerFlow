"""Tests for immutable in-memory project dataset management."""

from __future__ import annotations

import unittest

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import DerivationType, Project, ProjectAnalysisEntry, ProjectDatasetEntry
from core.sequence_dataset import SequenceDataset, SourceType


class ProjectTests(unittest.TestCase):
    def dataset(self, dataset_id: str, name: str | None = None) -> SequenceDataset:
        return SequenceDataset.from_sequence_pairs(
            dataset_id,
            name or dataset_id.title(),
            SourceType.IMPORTED_FASTA,
            [(f"{dataset_id}-record", "ATGC")],
        )

    def analysis_result(
        self,
        result_id: str = "blast-result",
        parent_dataset_id: str = "trimmed",
        result_type: AnalysisResultType = AnalysisResultType.BLAST,
    ) -> AnalysisResult:
        return AnalysisResult(
            result_id=result_id,
            name=result_id.replace("-", " ").title(),
            result_type=result_type,
            parent_dataset_id=parent_dataset_id,
            metadata={"producer": "test"},
        )

    def alignment_dataset(self, alignment_id: str, parent_dataset_id: str) -> AlignmentDataset:
        return AlignmentDataset(
            alignment_id=alignment_id,
            name=alignment_id.title(),
            parent_dataset_id=parent_dataset_id,
            records=(
                AlignmentRecord(
                    record_id=f"{parent_dataset_id}-record",
                    source_record_id=f"{parent_dataset_id}-record",
                    aligned_sequence="ATG-C",
                ),
            ),
        )

    def test_create_allows_an_empty_project_and_freezes_metadata(self) -> None:
        source_metadata = {"region": "Central Java"}
        project = Project.create("wedgefish", "Central Java Wedgefish", source_metadata)
        source_metadata["region"] = "changed"

        self.assertEqual(project.dataset_count, 0)
        self.assertEqual(project.dataset_ids, ())
        self.assertEqual(project.metadata["region"], "Central Java")
        with self.assertRaises(TypeError):
            project.metadata["region"] = "changed"  # type: ignore[index]

    def test_add_dataset_preserves_order_and_original_project(self) -> None:
        imported = self.dataset("imported")
        trimmed = self.dataset("trimmed")
        project = Project.create("project", "Project")
        after_import = project.add_dataset(imported)
        after_trim = after_import.add_dataset(
            trimmed,
            parent_dataset_id="imported",
            derivation_type=DerivationType.TRIMMED_FROM_READS,
        )

        self.assertEqual(project.dataset_ids, ())
        self.assertEqual(after_import.dataset_ids, ("imported",))
        self.assertEqual(after_trim.dataset_ids, ("imported", "trimmed"))
        self.assertEqual(after_trim.get_entry("imported").display_name, imported.name)

    def test_duplicate_id_getters_and_has_dataset(self) -> None:
        imported = self.dataset("imported")
        project = Project.create("project", "Project").add_dataset(imported)

        self.assertTrue(project.has_dataset("imported"))
        self.assertFalse(project.has_dataset("missing"))
        self.assertIs(project.get_dataset("imported"), imported)
        self.assertIs(project.get_entry("imported").dataset, imported)
        with self.assertRaises(KeyError):
            project.get_dataset("missing")
        with self.assertRaisesRegex(ValueError, "already exists"):
            project.add_dataset(imported)

    def test_add_alignment_dataset_as_project_dataset(self) -> None:
        imported = self.dataset("imported")
        alignment = self.alignment_dataset("alignment", "imported")
        project = (
            Project.create("project", "Project")
            .add_dataset(imported)
            .add_dataset(
                alignment,
                parent_dataset_id="imported",
                derivation_type=DerivationType.ALIGNMENT_FROM_DATASET,
            )
        )

        self.assertEqual(project.dataset_ids, ("imported", "alignment"))
        self.assertIs(project.get_dataset("alignment"), alignment)
        self.assertEqual(project.lineage("alignment"), ("imported", "alignment"))
        with self.assertRaisesRegex(ValueError, "already exists"):
            project.add_dataset(alignment)

    def test_rename_returns_new_project_without_changing_dataset(self) -> None:
        imported = self.dataset("imported", "Original dataset name")
        project = Project.create("project", "Project").add_dataset(imported)
        renamed = project.rename_dataset("imported", "Display name for review")

        self.assertEqual(project.get_entry("imported").display_name, "Original dataset name")
        self.assertEqual(renamed.get_entry("imported").display_name, "Display name for review")
        self.assertEqual(imported.name, "Original dataset name")
        self.assertEqual(imported.records[0].sequence, "ATGC")

    def test_remove_leaf_rejects_missing_and_rejects_parent_with_children(self) -> None:
        imported = self.dataset("imported")
        aligned = self.dataset("aligned")
        project = (
            Project.create("project", "Project")
            .add_dataset(imported)
            .add_dataset(
                aligned,
                parent_dataset_id="imported",
                derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
            )
        )

        with self.assertRaises(KeyError):
            project.remove_dataset("missing")
        with self.assertRaisesRegex(ValueError, "children exist"):
            project.remove_dataset("imported")
        removed = project.remove_dataset("aligned")
        self.assertEqual(removed.dataset_ids, ("imported",))
        self.assertEqual(project.dataset_ids, ("imported", "aligned"))

    def test_parent_child_and_lineage_follow_dataset_derivation(self) -> None:
        raw = self.dataset("raw")
        trimmed = self.dataset("trimmed")
        alignment = self.dataset("alignment")
        project = (
            Project.create("project", "Project")
            .add_dataset(raw, derivation_type=DerivationType.IMPORTED)
            .add_dataset(
                trimmed,
                parent_dataset_id="raw",
                derivation_type=DerivationType.TRIMMED_FROM_READS,
            )
            .add_dataset(
                alignment,
                parent_dataset_id="trimmed",
                derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
            )
        )

        self.assertEqual(project.child_dataset_ids("raw"), ("trimmed",))
        self.assertEqual(project.child_dataset_ids("trimmed"), ("alignment",))
        self.assertEqual(project.lineage("alignment"), ("raw", "trimmed", "alignment"))

    def test_add_rejects_missing_parent_and_self_parent(self) -> None:
        project = Project.create("project", "Project")
        child = self.dataset("child")

        with self.assertRaisesRegex(ValueError, "does not exist"):
            project.add_dataset(child, parent_dataset_id="missing")
        with self.assertRaisesRegex(ValueError, "own parent"):
            project.add_dataset(child, parent_dataset_id="child")

    def test_entry_metadata_is_read_only_and_direct_cycles_are_rejected(self) -> None:
        raw = self.dataset("raw")
        child = self.dataset("child")
        entry_metadata = {"operation": "import"}
        entry = ProjectDatasetEntry(raw, "Raw reads", metadata=entry_metadata)
        entry_metadata["operation"] = "changed"

        self.assertEqual(entry.metadata["operation"], "import")
        with self.assertRaises(TypeError):
            entry.metadata["operation"] = "changed"  # type: ignore[index]

        raw_entry = ProjectDatasetEntry(raw, "Raw", parent_dataset_id="child")
        child_entry = ProjectDatasetEntry(child, "Child", parent_dataset_id="raw")
        with self.assertRaisesRegex(ValueError, "cycle"):
            Project("project", "Project", (raw_entry, child_entry))

    def test_analysis_results_coexist_with_datasets_and_preserve_originals(self) -> None:
        raw = self.dataset("raw")
        trimmed = self.dataset("trimmed")
        blast_result = self.analysis_result(parent_dataset_id="trimmed")
        project = (
            Project.create("project", "Project")
            .add_dataset(raw)
            .add_dataset(
                trimmed,
                parent_dataset_id="raw",
                derivation_type=DerivationType.TRIMMED_FROM_READS,
            )
        )
        updated = project.add_analysis_result(blast_result, display_name="COI identification")

        self.assertEqual(project.analysis_result_ids, ())
        self.assertEqual(updated.dataset_ids, ("raw", "trimmed"))
        self.assertEqual(updated.analysis_result_count, 1)
        self.assertEqual(updated.analysis_result_ids, ("blast-result",))
        self.assertTrue(updated.has_analysis_result("blast-result"))
        self.assertFalse(updated.has_analysis_result("missing"))
        self.assertIs(updated.get_analysis_result("blast-result"), blast_result)
        self.assertEqual(
            updated.get_analysis_entry("blast-result").display_name,
            "COI identification",
        )
        self.assertEqual(updated.analysis_lineage("blast-result"), ("raw", "trimmed", "blast-result"))
        self.assertEqual(trimmed.records[0].sequence, "ATGC")
        self.assertEqual(blast_result.metadata["producer"], "test")

    def test_analysis_result_entry_metadata_is_read_only_and_results_can_be_removed(self) -> None:
        trimmed = self.dataset("trimmed")
        result = self.analysis_result(parent_dataset_id="trimmed")
        entry_metadata = {"review_status": "pending"}
        project = (
            Project.create("project", "Project")
            .add_dataset(trimmed)
            .add_analysis_result(result, metadata=entry_metadata)
        )
        entry_metadata["review_status"] = "changed"

        entry = project.get_analysis_entry("blast-result")
        self.assertIsInstance(entry, ProjectAnalysisEntry)
        self.assertEqual(entry.result_type, AnalysisResultType.BLAST)
        self.assertEqual(entry.parent_dataset_id, "trimmed")
        self.assertEqual(entry.metadata["review_status"], "pending")
        with self.assertRaises(TypeError):
            entry.metadata["review_status"] = "changed"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "analysis results exist"):
            project.remove_dataset("trimmed")

        removed = project.remove_analysis_result("blast-result")
        self.assertEqual(project.analysis_result_ids, ("blast-result",))
        self.assertEqual(removed.analysis_result_ids, ())
        self.assertEqual(removed.dataset_ids, ("trimmed",))
        with self.assertRaises(KeyError):
            project.get_analysis_result("missing")
        with self.assertRaises(KeyError):
            project.remove_analysis_result("missing")

    def test_analysis_result_addition_rejects_duplicate_and_missing_parent(self) -> None:
        trimmed = self.dataset("trimmed")
        result = self.analysis_result(parent_dataset_id="trimmed")
        project = Project.create("project", "Project").add_dataset(trimmed)
        updated = project.add_analysis_result(result)

        with self.assertRaisesRegex(ValueError, "already exists"):
            updated.add_analysis_result(result)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            Project.create("project", "Project").add_analysis_result(result)


if __name__ == "__main__":
    unittest.main()
