"""Regression tests for the GUI-independent cross-dataset record builder."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.alignment_dataset import AlignmentDataset, AlignmentRecord
from core.lineage import (
    LineageRelationType,
    RecordProvenance,
    RecordRef,
)
from core.project import Project
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from export.sequence_export import export_dataset_to_fasta
from persistence.project_json import load_project, save_project
from workflow.cross_dataset_builder import (
    CrossDatasetSelectionError,
    build_dataset_from_record_refs,
    create_dataset_from_record_refs,
    validate_record_refs,
)


def _dataset(dataset_id: str, records: tuple[SequenceRecord, ...]) -> SequenceDataset:
    return SequenceDataset(
        dataset_id=dataset_id,
        name=dataset_id,
        source_type=SourceType.IMPORTED_FASTA,
        records=records,
    )


def _project() -> Project:
    run_a = _dataset(
        "Run_A",
        (
            SequenceRecord("C1", "ATGC", description="first", metadata={"country": "JP"}),
            SequenceRecord("C2", "ATGT", description="second", metadata={"country": "ID"}),
            SequenceRecord("C3", "ATGA"),
        ),
    )
    run_b = _dataset("Run_B", (SequenceRecord("C3", "TTTT"), SequenceRecord("C4", "TTTA")))
    run_c = _dataset("Run_C", (SequenceRecord("C6", "GGGG"), SequenceRecord("C7", "GGGA")))
    return Project.create("project", "Project").add_dataset(run_a).add_dataset(run_b).add_dataset(run_c)


class CrossDatasetBuilderTests(unittest.TestCase):
    def test_builds_ordered_dataset_across_three_sources_with_direct_provenance(self) -> None:
        project = _project()
        refs = (
            RecordRef("Run_A", "C1"),
            RecordRef("Run_A", "C2"),
            RecordRef("Run_B", "C4"),
            RecordRef("Run_C", "C7"),
        )
        build = build_dataset_from_record_refs(
            project,
            refs,
            dataset_id="Final_COI",
            name="Final COI",
            metadata={"marker": "COI"},
        )

        self.assertEqual(build.dataset.sequence_ids, ("C1", "C2", "C4", "C7"))
        self.assertEqual(build.dataset.source_type, SourceType.DERIVED)
        self.assertEqual(build.dataset.get_record("C1").description, "first")
        self.assertEqual(build.dataset.get_record("C1").metadata["country"], "JP")
        self.assertEqual(build.dataset.metadata["marker"], "COI")
        self.assertEqual(
            tuple(record.provenance for record in build.dataset.records),
            tuple(RecordProvenance((record_ref,)) for record_ref in refs),
        )
        self.assertEqual(
            tuple(relation.source_id for relation in build.lineage_relations),
            ("Run_A", "Run_B", "Run_C"),
        )
        self.assertTrue(
            all(
                relation.relation_type is LineageRelationType.MERGED_FROM_DATASETS
                for relation in build.lineage_relations
            )
        )
        self.assertEqual(project.dataset_ids, ("Run_A", "Run_B", "Run_C"))
        self.assertEqual(project.get_dataset("Run_A").get_record("C1").provenance, RecordProvenance())

    def test_single_source_uses_subset_relation_and_registers_with_project(self) -> None:
        project = _project()
        build = build_dataset_from_record_refs(
            project,
            (RecordRef("Run_B", "C4"),),
            dataset_id="Run_B_subset",
            name="Run B subset",
        )
        self.assertEqual(build.lineage_relations[0].relation_type, LineageRelationType.SUBSET_FROM_DATASET)
        updated = project.add_dataset(build.dataset, lineage_relations=build.lineage_relations)
        self.assertEqual(updated.lineage("Run_B_subset"), ("Run_B", "Run_B_subset"))
        self.assertEqual(updated.get_entry("Run_B_subset").parent_dataset_id, "Run_B")

    def test_validation_rejects_empty_duplicate_missing_unsupported_and_collision_inputs(self) -> None:
        project = _project()
        empty = validate_record_refs(project, ())
        self.assertFalse(empty.is_valid)
        with self.assertRaisesRegex(CrossDatasetSelectionError, "must not be empty"):
            build_dataset_from_record_refs(project, (), dataset_id="empty", name="Empty")

        duplicate = validate_record_refs(
            project,
            (RecordRef("Run_A", "C1"), RecordRef("Run_A", "C1")),
        )
        self.assertEqual(duplicate.duplicate_refs, (RecordRef("Run_A", "C1"),))
        with self.assertRaises(CrossDatasetSelectionError):
            create_dataset_from_record_refs(
                project,
                duplicate.record_refs,
                dataset_id="duplicate",
                name="Duplicate",
            )

        collision = validate_record_refs(
            project,
            (RecordRef("Run_A", "C3"), RecordRef("Run_B", "C3")),
        )
        self.assertEqual(collision.output_id_collisions["C3"], collision.record_refs)
        with self.assertRaisesRegex(CrossDatasetSelectionError, "output sequence_id collisions"):
            build_dataset_from_record_refs(
                project,
                collision.record_refs,
                dataset_id="collision",
                name="Collision",
            )

        missing = validate_record_refs(project, (RecordRef("missing", "C1"),))
        self.assertEqual(missing.missing_datasets, (RecordRef("missing", "C1"),))
        missing_record = validate_record_refs(project, (RecordRef("Run_A", "missing"),))
        self.assertEqual(missing_record.missing_records, (RecordRef("Run_A", "missing"),))

        alignment = AlignmentDataset(
            alignment_id="alignment",
            name="Alignment",
            parent_dataset_id="Run_A",
            records=(AlignmentRecord("C1", "C1", "AT-GC"),),
        )
        project_with_alignment = project.add_dataset(alignment, parent_dataset_id="Run_A")
        unsupported = validate_record_refs(project_with_alignment, (RecordRef("alignment", "C1"),))
        self.assertEqual(unsupported.unsupported_datasets, (RecordRef("alignment", "C1"),))

    def test_explicit_output_names_resolve_collision_without_mutating_sources(self) -> None:
        project = _project()
        refs = (RecordRef("Run_A", "C3"), RecordRef("Run_B", "C3"))
        output_names = {
            refs[0]: "Cirebon_C3",
            refs[1]: "Rembang_C3",
        }
        validation = validate_record_refs(project, refs, output_record_ids=output_names)
        self.assertTrue(validation.is_valid)
        build = build_dataset_from_record_refs(
            project,
            refs,
            dataset_id="resolved",
            name="Resolved",
            output_record_ids=output_names,
        )
        self.assertEqual(build.dataset.sequence_ids, ("Cirebon_C3", "Rembang_C3"))
        self.assertEqual(build.dataset.get_record("Cirebon_C3").metadata["original_record_id"], "C3")
        self.assertEqual(
            build.dataset.get_record("Rembang_C3").provenance,
            RecordProvenance((RecordRef("Run_B", "C3"),)),
        )
        self.assertEqual(project.get_dataset("Run_A").sequence_ids, ("C1", "C2", "C3"))

    def test_shared_direct_source_warning_is_mechanical_not_heuristic(self) -> None:
        raw = _dataset("raw", (SequenceRecord("C1", "ATGC"),))
        source_ref = RecordRef("raw", "C1")
        first = _dataset(
            "first",
            (SequenceRecord("A", "ATGC", provenance=RecordProvenance((source_ref,))),),
        )
        second = _dataset(
            "second",
            (SequenceRecord("B", "ATGC", provenance=RecordProvenance((source_ref,))),),
        )
        project = Project.create("project", "Project").add_dataset(raw).add_dataset(
            first, parent_dataset_id="raw"
        ).add_dataset(second, parent_dataset_id="raw")
        validation = validate_record_refs(
            project,
            (RecordRef("first", "A"), RecordRef("second", "B")),
        )
        self.assertTrue(validation.is_valid)
        self.assertEqual(len(validation.shared_direct_source_warnings), 1)
        self.assertEqual(validation.shared_direct_source_warnings[0].shared_source_records, (source_ref,))
        build = build_dataset_from_record_refs(
            project,
            validation.record_refs,
            dataset_id="output",
            name="Output",
        )
        self.assertEqual(
            build.dataset.get_record("A").provenance,
            RecordProvenance((RecordRef("first", "A"),)),
        )

    def test_roundtrip_and_fasta_export_preserve_lineage_and_record_provenance(self) -> None:
        project = _project()
        refs = (
            RecordRef("Run_A", "C1"),
            RecordRef("Run_A", "C2"),
            RecordRef("Run_B", "C4"),
            RecordRef("Run_C", "C7"),
        )
        build = build_dataset_from_record_refs(project, refs, dataset_id="Final_COI", name="Final COI")
        updated = project.add_dataset(build.dataset, lineage_relations=build.lineage_relations)
        with TemporaryDirectory() as directory:
            directory_path = Path(directory)
            project_path = directory_path / "project.json"
            fasta_path = directory_path / "final.fasta"
            save_project(updated, project_path)
            reloaded = load_project(project_path)
            export_dataset_to_fasta(reloaded.get_dataset("Final_COI"), fasta_path)
            self.assertEqual(
                fasta_path.read_text(encoding="utf-8"),
                ">C1\nATGC\n>C2\nATGT\n>C4\nTTTA\n>C7\nGGGA\n",
            )
        final_entry = reloaded.get_entry("Final_COI")
        self.assertEqual(
            tuple(relation.source_id for relation in final_entry.lineage_relations),
            ("Run_A", "Run_B", "Run_C"),
        )
        self.assertEqual(
            reloaded.get_dataset("Final_COI").get_record("C4").provenance,
            RecordProvenance((RecordRef("Run_B", "C4"),)),
        )


if __name__ == "__main__":
    unittest.main()
