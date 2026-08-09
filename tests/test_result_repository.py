"""Tests for filesystem-backed external analysis result storage."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.analysis_result import AnalysisResultType
from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.bold_result import BoldHit, BoldResultDataset
from core.project import Project
from core.result_repository import FilesystemResultRepository, ResultRepositoryError
from core.sequence_dataset import SequenceDataset, SourceType


def make_blast_result() -> BlastResultDataset:
    return BlastResultDataset(
        result_id="blast:IK345/1",
        name="IK345 BLAST",
        parent_dataset_id="coi",
        analysis_mode=BlastAnalysisMode.IDENTIFICATION,
        marker="COI",
        database="nt",
        metadata={"repository_note": "external payload"},
        hits=(
            BlastHit("IK345", "AB123", "Rhynchobatus", "Rhynchobatus sp.", 99, 100, 0.0, 650, "nt"),
        ),
    )


def make_bold_result() -> BoldResultDataset:
    return BoldResultDataset(
        result_id="bold-IK345",
        name="IK345 BOLD",
        parent_dataset_id="coi",
        marker="COI",
        database="BOLD",
        metadata={"repository_note": "external payload"},
        hits=(BoldHit("IK345", process_id="P1", species_name="Rhynchobatus sp.", similarity=99.1, database="BOLD"),),
    )


class FilesystemResultRepositoryTests(unittest.TestCase):
    def test_register_and_get_blast_and_bold_payloads(self) -> None:
        with TemporaryDirectory() as directory:
            repository = FilesystemResultRepository(directory)
            blast = make_blast_result()
            bold = make_bold_result()
            self.assertEqual(repository.register_result(blast), blast.result_id)
            self.assertEqual(repository.register_result(bold), bold.result_id)

            loaded_blast = repository.get_result(blast.result_id)
            loaded_bold = repository.get_result(bold.result_id)
            self.assertIsInstance(loaded_blast, BlastResultDataset)
            self.assertIsInstance(loaded_bold, BoldResultDataset)
            self.assertEqual(loaded_blast.hits, blast.hits)
            self.assertEqual(loaded_bold.hits, bold.hits)
            self.assertTrue(repository.has_result(blast.result_id))
            self.assertTrue((Path(directory) / "results" / "index.json").exists())

    def test_duplicate_invalid_and_missing_results_are_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            repository = FilesystemResultRepository(directory)
            result = make_blast_result()
            repository.register_result(result)
            with self.assertRaisesRegex(ResultRepositoryError, "already exists"):
                repository.register_result(result)
            with self.assertRaises(ResultRepositoryError):
                repository.register_result(object())  # type: ignore[arg-type]
            with self.assertRaisesRegex(ResultRepositoryError, "does not exist"):
                repository.get_result("missing")
            with self.assertRaisesRegex(ResultRepositoryError, "does not exist"):
                repository.remove_result("missing")

    def test_remove_and_project_analysis_reference_resolution(self) -> None:
        with TemporaryDirectory() as directory:
            repository = FilesystemResultRepository(directory)
            blast = make_blast_result()
            repository.register_result(blast)
            dataset = SequenceDataset.from_sequence_pairs(
                "coi", "COI", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"),)
            )
            project = Project.create("project", "Project").add_dataset(dataset)
            project = project.add_analysis_result(blast.analysis_result)
            reference = project.get_analysis_result(blast.result_id)

            resolved = repository.get_for_analysis_result(reference)
            self.assertEqual(resolved.result_id, blast.result_id)
            self.assertEqual(reference.result_type, AnalysisResultType.BLAST)
            repository.remove_result(blast.result_id)
            self.assertFalse(repository.has_result(blast.result_id))
            with self.assertRaisesRegex(ResultRepositoryError, "does not exist"):
                repository.get_for_analysis_result(reference)

    def test_new_repository_instance_reads_existing_index(self) -> None:
        with TemporaryDirectory() as directory:
            blast = make_blast_result()
            FilesystemResultRepository(directory).register_result(blast)
            reloaded_repository = FilesystemResultRepository(directory)
            self.assertEqual(reloaded_repository.get_result(blast.result_id).name, blast.name)


if __name__ == "__main__":
    unittest.main()
