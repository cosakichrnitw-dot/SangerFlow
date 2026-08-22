"""Regression tests for Project logical Dataset revision state."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.lineage import (
    LineageRelation,
    LineageRelationType,
    LineageSourceKind,
    RecordProvenance,
    RecordRef,
)
from core.project import (
    Project,
    ProjectDatasetEntry,
    RevisionOperation,
    RevisionState,
)
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_json import PROJECT_SCHEMA_VERSION, ProjectPersistenceError, load_project, save_project


def _dataset(dataset_id: str, *, record_id: str | None = None) -> SequenceDataset:
    return SequenceDataset(
        dataset_id=dataset_id,
        name=dataset_id,
        source_type=SourceType.IMPORTED_FASTA,
        records=(
            SequenceRecord(
                sequence_id=record_id or dataset_id,
                sequence="ATGC",
                provenance=RecordProvenance((RecordRef("source", "C1"),))
                if dataset_id != "source"
                else RecordProvenance(),
            ),
        ),
    )


class DatasetRevisionTests(unittest.TestCase):
    def test_add_dataset_creates_new_logical_dataset_current_r1(self) -> None:
        project = Project.create("project", "Project").add_dataset(_dataset("source"))
        entry = project.get_entry("source")
        self.assertEqual(entry.logical_id, "source")
        self.assertEqual(entry.revision_number, 1)
        self.assertIs(entry.revision_state, RevisionState.CURRENT)
        self.assertIs(entry.revision_operation, RevisionOperation.IMPORTED)
        self.assertIsNone(entry.supersedes_dataset_id)

    def test_add_revision_supersedes_only_in_new_project(self) -> None:
        before = Project.create("project", "Project").add_dataset(_dataset("source"))
        after = before.add_dataset_revision(
            "source",
            _dataset("source_r2", record_id="C1_CO1"),
            operation=RevisionOperation.BATCH_RENAME,
        )
        self.assertIs(before.get_entry("source").revision_state, RevisionState.CURRENT)
        self.assertIs(after.get_entry("source").revision_state, RevisionState.SUPERSEDED)
        revision = after.get_entry("source_r2")
        self.assertEqual(revision.logical_id, "source")
        self.assertEqual(revision.revision_number, 2)
        self.assertEqual(revision.supersedes_dataset_id, "source")
        self.assertIs(revision.revision_state, RevisionState.CURRENT)

    def test_multiple_revisions_queries_and_archive_restore(self) -> None:
        project = Project.create("project", "Project").add_dataset(_dataset("source"))
        project = project.add_dataset_revision(
            "source", _dataset("source_r2"), operation=RevisionOperation.METADATA_MERGE
        )
        project = project.add_dataset_revision(
            "source_r2", _dataset("source_r3"), operation=RevisionOperation.SEQUENCE_EDIT
        )
        history = project.dataset_revision_history("source")
        self.assertEqual(tuple(entry.revision_number for entry in history), (1, 2, 3))
        self.assertEqual(
            tuple(entry.revision_state for entry in history),
            (RevisionState.SUPERSEDED, RevisionState.SUPERSEDED, RevisionState.CURRENT),
        )
        archived = project.archive_logical_dataset("source")
        self.assertEqual(archived.current_dataset_entries(), ())
        self.assertEqual(archived.archived_dataset_entries()[0].dataset.dataset_id, "source_r3")
        restored = archived.restore_logical_dataset("source")
        self.assertTrue(restored.is_current_revision("source_r3"))

    def test_separate_logical_datasets_can_both_be_current(self) -> None:
        project = Project.create("project", "Project").add_dataset(_dataset("first")).add_dataset(_dataset("second"))
        self.assertEqual(project.logical_dataset_ids, ("first", "second"))
        self.assertEqual({entry.logical_id for entry in project.current_dataset_entries()}, {"first", "second"})

    def test_alignment_revisions_use_same_api(self) -> None:
        parent = _dataset("source")
        alignment = AlignmentDataset(
            alignment_id="alignment", name="Alignment", parent_dataset_id="source",
            records=(AlignmentRecord("C1", "source", "ATGC"),),
        )
        edited = AlignmentDataset(
            alignment_id="alignment_r2", name="Alignment edited", parent_dataset_id="source",
            records=(AlignmentRecord("C1", "source", "AT-C"),),
        )
        project = Project.create("project", "Project").add_dataset(parent).add_dataset(alignment, parent_dataset_id="source")
        project = project.add_dataset_revision("alignment", edited, operation=RevisionOperation.ALIGNMENT_EDIT)
        self.assertEqual(project.current_dataset_entry("alignment").dataset.alignment_id, "alignment_r2")

    def test_analysis_and_record_provenance_keep_immutable_revision_ids(self) -> None:
        source = SequenceDataset.from_sequence_pairs("source", "Source", SourceType.IMPORTED_FASTA, (("C1", "ATGC"),))
        project = Project.create("project", "Project").add_dataset(source)
        project = project.add_dataset_revision(
            "source",
            _dataset("source_r2", record_id="C1_CO1"),
            operation=RevisionOperation.RECORD_RENAME,
        )
        result = AnalysisResult("blast", "BLAST", AnalysisResultType.BLAST, "source")
        project = project.add_analysis_result(result)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(project, path)
            loaded = load_project(path)
        self.assertEqual(loaded.get_analysis_result("blast").parent_dataset_id, "source")
        self.assertEqual(
            loaded.get_dataset("source_r2").records[0].provenance.source_records,
            (RecordRef("source", "C1"),),
        )

    def test_revision_validation_rejects_invalid_current_and_supersedes_family(self) -> None:
        first = _dataset("first")
        second = _dataset("second")
        with self.assertRaisesRegex(ValueError, "more than one current"):
            Project(
                "project", "Project",
                dataset_entries=(
                    ProjectDatasetEntry(first, "First", logical_id="logical"),
                    ProjectDatasetEntry(second, "Second", logical_id="logical", revision_number=2),
                ),
            )

    def test_revision_cycle_and_dependent_superseded_delete_are_rejected(self) -> None:
        first = _dataset("first")
        second = _dataset("second")
        with self.assertRaises(ValueError):
            Project(
                "project", "Project",
                dataset_entries=(
                    ProjectDatasetEntry(
                        first, "First", logical_id="logical", revision_state=RevisionState.SUPERSEDED,
                        supersedes_dataset_id="second",
                    ),
                    ProjectDatasetEntry(
                        second, "Second", logical_id="logical", revision_number=2,
                        supersedes_dataset_id="first",
                    ),
                ),
            )

        source = SequenceDataset.from_sequence_pairs("source", "Source", SourceType.IMPORTED_FASTA, (("C1", "ATGC"),))
        derived = _dataset("derived")
        project = Project.create("project", "Project").add_dataset(source)
        project = project.add_dataset_revision("source", _dataset("source_r2"), operation=RevisionOperation.OTHER)
        project = project.add_dataset(
            derived,
            lineage_relations=(
                LineageRelation(
                    LineageSourceKind.DATASET,
                    "source",
                    LineageRelationType.SUBSET_FROM_DATASET,
                ),
            ),
        )
        with self.assertRaisesRegex(ValueError, "children exist"):
            project.remove_dataset("source")
        with self.assertRaisesRegex(ValueError, "same logical_id"):
            Project(
                "project", "Project",
                dataset_entries=(
                    ProjectDatasetEntry(first, "First", logical_id="first"),
                    ProjectDatasetEntry(
                        second, "Second", logical_id="second", revision_number=2,
                        supersedes_dataset_id="first",
                    ),
                ),
            )

    def test_v2_migrates_each_dataset_to_a_separate_logical_r1(self) -> None:
        payload = {
            "schema_version": 2,
            "project": {
                "project_id": "project", "name": "Project", "metadata": {}, "analysis_results": [],
                "datasets": [_v2_entry("first"), _v2_entry("second")],
            },
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            original = json.dumps(payload, sort_keys=True)
            path.write_text(original, encoding="utf-8")
            loaded = load_project(path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(loaded.logical_dataset_ids, ("first", "second"))
            self.assertTrue(loaded.is_current_revision("first"))
            save_project(loaded, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], PROJECT_SCHEMA_VERSION)

    def test_v3_round_trip_and_unknown_newer_schema(self) -> None:
        project = Project.create("project", "Project").add_dataset(_dataset("source"))
        project = project.add_dataset_revision("source", _dataset("source_r2"), operation=RevisionOperation.OTHER)
        project = project.archive_logical_dataset("source")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "project.json"
            save_project(project, path)
            loaded = load_project(path)
            self.assertEqual(loaded.dataset_revision_history("source"), project.dataset_revision_history("source"))
            path.write_text(json.dumps({"schema_version": 999, "project": {}}), encoding="utf-8")
            with self.assertRaises(ProjectPersistenceError):
                load_project(path)


def _v2_entry(dataset_id: str) -> dict[str, object]:
    return {
        "dataset": {
            "dataset_model": "SequenceDataset",
            "dataset_id": dataset_id,
            "name": dataset_id,
            "source_type": "IMPORTED_FASTA",
            "metadata": {},
            "records": [{"sequence_id": f"{dataset_id}-record", "sequence": "ATGC", "description": None, "metadata": {}, "provenance": {"source_records": []}}],
        },
        "display_name": dataset_id,
        "parent_dataset_id": None,
        "derivation_type": None,
        "metadata": {},
        "lineage_relations": [],
    }
