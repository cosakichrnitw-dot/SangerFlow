"""Tests for versioned JSON persistence of immutable Project descriptions."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_json import (
    PROJECT_SCHEMA_VERSION,
    ProjectPersistenceError,
    load_project,
    save_project,
)


def make_project() -> Project:
    imported = SequenceDataset(
        dataset_id="imported-coi",
        name="Imported COI",
        source_type=SourceType.IMPORTED_FASTA,
        records=(
            SequenceRecord(
                "IK345",
                "ATGC",
                description="IK345 COI",
                source_reference=object(),
                metadata={"country": "Indonesia"},
            ),
        ),
        metadata={"source_filepath": "coi.fasta", "nested": {"marker": "COI"}},
    )
    alignment = AlignmentDataset(
        alignment_id="aligned-coi",
        name="Aligned COI",
        parent_dataset_id="imported-coi",
        records=(
            AlignmentRecord(
                record_id="IK345",
                source_record_id="IK345",
                aligned_sequence="ATG-C",
                metadata={"country": "Indonesia"},
            ),
        ),
        metadata={"alignment_method": "MAFFT"},
    )
    project = Project.create("central-java", "Central Java", {"owner": "lab"})
    project = project.add_dataset(imported, metadata={"added_by": "FASTA import"})
    project = project.add_dataset(
        alignment,
        parent_dataset_id="imported-coi",
        derivation_type=DerivationType.ALIGNMENT_FROM_DATASET,
        metadata={"workflow": "MAFFT"},
    )
    return project.add_analysis_result(
        AnalysisResult(
            result_id="blast-001",
            name="COI identification",
            result_type=AnalysisResultType.BLAST,
            parent_dataset_id="aligned-coi",
            metadata={"repository_key": "blast-001.json"},
        ),
        metadata={"added_by": "BLAST Workflow"},
    )


class ProjectJsonPersistenceTests(unittest.TestCase):
    def test_save_then_load_preserves_project_datasets_and_lineage(self) -> None:
        project = make_project()
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "central-java.sangerflow.json"
            save_project(project, path)
            loaded = load_project(path)

            self.assertEqual(loaded.project_id, project.project_id)
            self.assertEqual(loaded.name, project.name)
            self.assertEqual(dict(loaded.metadata), dict(project.metadata))
            self.assertEqual(loaded.dataset_ids, ("imported-coi", "aligned-coi"))
            self.assertEqual(loaded.get_dataset("imported-coi").sequence_ids, ("IK345",))
            self.assertEqual(loaded.get_dataset("imported-coi").records[0].description, "IK345 COI")
            self.assertIsNone(loaded.get_dataset("imported-coi").records[0].source_reference)
            self.assertEqual(loaded.lineage("aligned-coi"), ("imported-coi", "aligned-coi"))
            self.assertEqual(
                loaded.get_entry("aligned-coi").derivation_type,
                DerivationType.ALIGNMENT_FROM_DATASET,
            )
            loaded_alignment = loaded.get_dataset("aligned-coi")
            self.assertIsInstance(loaded_alignment, AlignmentDataset)
            self.assertEqual(loaded_alignment.length, 5)
            self.assertEqual(loaded_alignment.records[0].aligned_sequence, "ATG-C")

    def test_analysis_result_reference_and_lineage_are_preserved_without_payload(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "project.json"
            save_project(make_project(), path)
            loaded = load_project(path)

            result = loaded.get_analysis_result("blast-001")
            self.assertEqual(result.result_type, AnalysisResultType.BLAST)
            self.assertEqual(result.parent_dataset_id, "aligned-coi")
            self.assertEqual(result.metadata["repository_key"], "blast-001.json")
            self.assertEqual(
                loaded.analysis_lineage("blast-001"),
                ("imported-coi", "aligned-coi", "blast-001"),
            )

    def test_metadata_is_restored_read_only_and_original_project_is_unchanged(self) -> None:
        project = make_project()
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "project.json"
            save_project(project, path)
            loaded = load_project(path)
            with self.assertRaises(TypeError):
                loaded.metadata["owner"] = "other"  # type: ignore[index]
            with self.assertRaises(TypeError):
                loaded.get_dataset("imported-coi").metadata["x"] = 1  # type: ignore[index]
            self.assertEqual(project.dataset_ids, ("imported-coi", "aligned-coi"))

    def test_rejects_invalid_json_and_unsupported_schema(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            invalid = directory / "invalid.json"
            invalid.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ProjectPersistenceError):
                load_project(invalid)

            unsupported = directory / "unsupported.json"
            unsupported.write_text(
                json.dumps({"schema_version": PROJECT_SCHEMA_VERSION + 1, "project": {}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ProjectPersistenceError, "schema_version"):
                load_project(unsupported)

    def test_rejects_non_json_metadata_and_missing_file(self) -> None:
        project = Project.create("project", "Project", {"opaque": object()})
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "project.json"
            with self.assertRaises(ProjectPersistenceError):
                save_project(project, path)
            with self.assertRaises(ProjectPersistenceError):
                load_project(Path(temporary_directory) / "missing.json")


if __name__ == "__main__":
    unittest.main()
