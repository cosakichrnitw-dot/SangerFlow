"""Tests for immutable in-memory BLAST result values."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType


def make_hit(query_id: str = "IK345", accession: str = "AB123456") -> BlastHit:
    return BlastHit(
        query_id=query_id,
        hit_accession=accession,
        scientific_name="Rhynchobatus australiae",
        organism="Rhynchobatus australiae",
        identity=99.5,
        query_coverage=98.0,
        evalue=1e-50,
        alignment_length=658,
        database="nt",
    )


class BlastResultTests(unittest.TestCase):
    def test_creates_valid_hit_and_rejects_invalid_numeric_values(self) -> None:
        hit = make_hit()
        self.assertEqual(hit.query_id, "IK345")
        self.assertEqual(hit.identity, 99.5)
        with self.assertRaisesRegex(ValueError, "identity"):
            BlastHit(**{**hit.__dict__, "identity": 101})
        with self.assertRaisesRegex(ValueError, "query_coverage"):
            BlastHit(**{**hit.__dict__, "query_coverage": -1})
        with self.assertRaisesRegex(ValueError, "evalue"):
            BlastHit(**{**hit.__dict__, "evalue": -0.1})
        with self.assertRaisesRegex(ValueError, "alignment_length"):
            BlastHit(**{**hit.__dict__, "alignment_length": 0})

    def test_dataset_keeps_multiple_queries_hit_order_and_parent_metadata(self) -> None:
        metadata = {"analysis_type": "BLAST", "database_version": "test"}
        hits = (make_hit("IK345", "AB1"), make_hit("IK345", "AB2"), make_hit("IK346", "AB3"))
        result = BlastResultDataset(
            "coi-blast", "COI BLAST", hits, "coi-trimmed", metadata=metadata
        )
        metadata["database_version"] = "changed"

        self.assertEqual(result.parent_dataset_id, "coi-trimmed")
        self.assertEqual(result.hit_count(), 3)
        self.assertEqual(result.query_ids(), ("IK345", "IK346"))
        self.assertEqual(
            tuple(hit.hit_accession for hit in result.get_hits("IK345")),
            ("AB1", "AB2"),
        )
        self.assertEqual(result.get_hits("unknown"), ())
        self.assertEqual(result.metadata["analysis_type"], "BLAST")
        self.assertEqual(result.metadata["database_version"], "test")
        with self.assertRaises(TypeError):
            result.metadata["analysis_type"] = "changed"  # type: ignore[index]

    def test_result_values_are_frozen_and_do_not_change_project_or_sequence_dataset(self) -> None:
        hit = make_hit()
        result = BlastResultDataset("result", "Result", (hit,), "input")
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, [("IK345", "ATGC")]
        )
        project = Project.create("project", "Project").add_dataset(dataset)

        with self.assertRaises(FrozenInstanceError):
            result.name = "Changed"  # type: ignore[misc]
        self.assertEqual(project.dataset_ids, ("input",))
        self.assertIs(project.get_dataset("input"), dataset)
        self.assertEqual(dataset.records[0].sequence, "ATGC")

    def test_qc_and_identification_modes_preserve_optional_marker_and_database(self) -> None:
        qc_result = BlastResultDataset(
            "qc-result",
            "Contamination QC",
            (make_hit(),),
            "trimmed",
            analysis_mode=BlastAnalysisMode.QC,
            marker="COI",
            database="nt",
        )
        identification_result = BlastResultDataset(
            "identification-result",
            "DNA barcoding identification",
            (make_hit(),),
            "reviewed-consensus",
            analysis_mode=BlastAnalysisMode.IDENTIFICATION,
            marker="COI-5P",
            database="BOLD reference set",
        )

        self.assertIs(qc_result.analysis_mode, BlastAnalysisMode.QC)
        self.assertEqual(qc_result.marker, "COI")
        self.assertEqual(qc_result.database, "nt")
        self.assertIs(identification_result.analysis_mode, BlastAnalysisMode.IDENTIFICATION)
        self.assertEqual(identification_result.marker, "COI-5P")
        self.assertEqual(identification_result.database, "BOLD reference set")
        with self.assertRaises(FrozenInstanceError):
            qc_result.marker = "16S"  # type: ignore[misc]

    def test_invalid_analysis_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "analysis_mode"):
            BlastResultDataset(
                "invalid",
                "Invalid",
                (make_hit(),),
                "input",
                analysis_mode="QC",  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
