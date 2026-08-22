"""Core provenance and Project JSON v2 regression coverage."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.lineage import (
    LineageRelation,
    LineageRelationType,
    LineageSourceKind,
    RecordProvenance,
    RecordRef,
)
from core.project import Project, ProjectDatasetEntry
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_json import PROJECT_SCHEMA_VERSION, ProjectPersistenceError, load_project, save_project


def _dataset(identifier: str, record_id: str = "C2", *, provenance: RecordProvenance | None = None) -> SequenceDataset:
    return SequenceDataset(
        dataset_id=identifier,
        name=identifier,
        source_type=SourceType.IMPORTED_FASTA,
        records=(SequenceRecord(record_id, "ATGC", provenance=provenance),),
    )


class LineageV2Tests(unittest.TestCase):
    def test_multiple_dataset_and_analysis_result_sources_are_immutable_and_validated(self) -> None:
        first = _dataset("first", "C2")
        second = _dataset("second", "C7")
        result = AnalysisResult("blast", "BLAST", AnalysisResultType.BLAST, "first")
        output = _dataset(
            "final",
            "C2",
            provenance=RecordProvenance((RecordRef("first", "C2"),)),
        )
        relations = (
            LineageRelation(LineageSourceKind.DATASET, "first", LineageRelationType.MERGED_FROM_DATASETS),
            LineageRelation(LineageSourceKind.DATASET, "second", LineageRelationType.MERGED_FROM_DATASETS),
            LineageRelation(LineageSourceKind.ANALYSIS_RESULT, "blast", LineageRelationType.SELECTED_FROM_BLAST),
        )
        project = Project.create("project", "Project").add_dataset(first).add_dataset(second).add_analysis_result(result)
        updated = project.add_dataset(output, lineage_relations=relations)

        entry = updated.get_entry("final")
        self.assertEqual(entry.parent_dataset_id, "first")
        self.assertEqual(entry.lineage_relations, relations)
        self.assertEqual(output.records[0].provenance.source_records, (RecordRef("first", "C2"),))
        self.assertEqual(project.dataset_ids, ("first", "second"))
        with self.assertRaises(TypeError):
            relations[0].metadata["note"] = "mutated"  # type: ignore[index]

    def test_invalid_relations_and_dependencies_are_rejected(self) -> None:
        source = _dataset("source")
        output = _dataset("output")
        project = Project.create("project", "Project").add_dataset(source)
        with self.assertRaisesRegex(ValueError, "does not exist"):
            project.add_dataset(
                output,
                lineage_relations=(
                    LineageRelation(LineageSourceKind.DATASET, "missing", LineageRelationType.SUBSET_FROM_DATASET),
                ),
            )
        with self.assertRaisesRegex(ValueError, "duplicate lineage"):
            ProjectDatasetEntry(
                output,
                "output",
                lineage_relations=(
                    LineageRelation(LineageSourceKind.DATASET, "source", LineageRelationType.SUBSET_FROM_DATASET),
                    LineageRelation(LineageSourceKind.DATASET, "source", LineageRelationType.SUBSET_FROM_DATASET),
                ),
            )
        with self.assertRaisesRegex(ValueError, "own lineage source"):
            ProjectDatasetEntry(
                output,
                "output",
                lineage_relations=(
                    LineageRelation(
                        LineageSourceKind.DATASET,
                        "output",
                        LineageRelationType.SUBSET_FROM_DATASET,
                    ),
                ),
            )
        with self.assertRaisesRegex(ValueError, "require an ANALYSIS_RESULT"):
            LineageRelation(
                LineageSourceKind.DATASET,
                "source",
                LineageRelationType.SELECTED_FROM_BLAST,
            )
        child = project.add_dataset(
            output,
            lineage_relations=(
                LineageRelation(LineageSourceKind.DATASET, "source", LineageRelationType.SUBSET_FROM_DATASET),
            ),
        )
        with self.assertRaisesRegex(ValueError, "children exist"):
            child.remove_dataset("source")

        result = AnalysisResult("blast", "BLAST", AnalysisResultType.BLAST, "source")
        project_with_result = project.add_analysis_result(result)
        selected = _dataset("selected")
        project_with_result = project_with_result.add_dataset(
            selected,
            lineage_relations=(
                LineageRelation(LineageSourceKind.ANALYSIS_RESULT, "blast", LineageRelationType.SELECTED_FROM_BLAST),
            ),
        )
        with self.assertRaisesRegex(ValueError, "derived datasets exist"):
            project_with_result.remove_analysis_result("blast")

        with self.assertRaisesRegex(ValueError, "does not exist"):
            project.add_dataset(
                _dataset("missing-result-output"),
                lineage_relations=(
                    LineageRelation(
                        LineageSourceKind.ANALYSIS_RESULT,
                        "missing-result",
                        LineageRelationType.SELECTED_FROM_BLAST,
                    ),
                ),
            )

    def test_dataset_cycle_is_rejected(self) -> None:
        first = _dataset("first")
        second = _dataset("second")
        with self.assertRaisesRegex(ValueError, "cycle"):
            Project(
                "project",
                "Project",
                dataset_entries=(
                    ProjectDatasetEntry(
                        first,
                        "first",
                        lineage_relations=(
                            LineageRelation(
                                LineageSourceKind.DATASET,
                                "second",
                                LineageRelationType.MERGED_FROM_DATASETS,
                            ),
                        ),
                    ),
                    ProjectDatasetEntry(
                        second,
                        "second",
                        lineage_relations=(
                            LineageRelation(
                                LineageSourceKind.DATASET,
                                "first",
                                LineageRelationType.MERGED_FROM_DATASETS,
                            ),
                        ),
                    ),
                ),
            )

    def test_record_provenance_supports_same_visible_id_from_distinct_datasets(self) -> None:
        provenance = RecordProvenance((RecordRef("run-one", "C2"), RecordRef("run-two", "C2")))
        record = SequenceRecord("C2_merged", "ATGC", provenance=provenance)
        self.assertEqual(record.provenance.source_records[0].dataset_id, "run-one")
        self.assertEqual(record.provenance.source_records[1].dataset_id, "run-two")
        self.assertEqual(SequenceRecord("raw", "ATGC").provenance, RecordProvenance())

    def test_v2_roundtrip_preserves_relations_and_record_provenance(self) -> None:
        first = _dataset("first", "C2")
        second = _dataset("second", "C7")
        result = AnalysisResult("blast", "BLAST", AnalysisResultType.BLAST, "first")
        final = SequenceDataset(
            dataset_id="final",
            name="Final",
            source_type=SourceType.IMPORTED_FASTA,
            records=(
                SequenceRecord("C2", "ATGC", provenance=RecordProvenance((RecordRef("first", "C2"),))),
                SequenceRecord("C7", "ATGT", provenance=RecordProvenance((RecordRef("second", "C7"),))),
            ),
        )
        project = (
            Project.create("project", "Project")
            .add_dataset(first)
            .add_dataset(second)
            .add_analysis_result(result)
            .add_dataset(
                final,
                lineage_relations=(
                    LineageRelation(LineageSourceKind.DATASET, "first", LineageRelationType.MERGED_FROM_DATASETS),
                    LineageRelation(LineageSourceKind.DATASET, "second", LineageRelationType.MERGED_FROM_DATASETS),
                    LineageRelation(LineageSourceKind.ANALYSIS_RESULT, "blast", LineageRelationType.SELECTED_FROM_BLAST),
                ),
            )
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(project, path)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], PROJECT_SCHEMA_VERSION)
            loaded = load_project(path)
        entry = loaded.get_entry("final")
        self.assertEqual(len(entry.lineage_relations), 3)
        self.assertEqual(loaded.get_dataset("final").get_record("C7").provenance.source_records, (RecordRef("second", "C7"),))

    def test_v1_load_migrates_legacy_parent_in_memory_without_touching_source(self) -> None:
        document = {
            "schema_version": 1,
            "project": {
                "project_id": "project",
                "name": "Project",
                "metadata": {},
                "analysis_results": [],
                "datasets": [
                    _v1_entry("source", None),
                    _v1_entry("child", "source"),
                ],
            },
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            original = json.dumps(document, indent=2)
            path.write_text(original, encoding="utf-8")
            loaded = load_project(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            child = loaded.get_entry("child")
            self.assertEqual(child.parent_dataset_id, "source")
            self.assertEqual(child.lineage_relations[0].source_id, "source")
            self.assertEqual(
                child.lineage_relations[0].relation_type,
                LineageRelationType.SUBSET_FROM_DATASET,
            )
            self.assertEqual(
                loaded.get_dataset("child").get_record("C2").provenance,
                RecordProvenance(),
            )
            save_project(loaded, path)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8"))["schema_version"],
                PROJECT_SCHEMA_VERSION,
            )

    def test_unknown_future_schema_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "future.json"
            path.write_text(json.dumps({"schema_version": 999, "project": {}}), encoding="utf-8")
            with self.assertRaises(ProjectPersistenceError):
                load_project(path)


def _v1_entry(dataset_id: str, parent_dataset_id: str | None) -> dict[str, object]:
    return {
        "dataset": {
            "dataset_model": "SequenceDataset",
            "dataset_id": dataset_id,
            "name": dataset_id,
            "source_type": "IMPORTED_FASTA",
            "metadata": {},
            "records": [
                {"sequence_id": "C2", "sequence": "ATGC", "description": None, "metadata": {}},
            ],
        },
        "display_name": dataset_id,
        "parent_dataset_id": parent_dataset_id,
        "derivation_type": "SUBSET_FROM_DATASET" if parent_dataset_id else None,
        "metadata": {},
    }
