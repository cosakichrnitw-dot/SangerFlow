"""Tests for the common immutable analysis-result model."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.blast_result import BlastHit, BlastResultDataset


class AnalysisResultTests(unittest.TestCase):
    def test_creates_an_immutable_result_with_type_parent_and_metadata(self) -> None:
        metadata = {"tool": "ASAP", "run_label": "COI exploration"}
        result = AnalysisResult(
            result_id="asap-coi-1",
            name="COI ASAP",
            result_type=AnalysisResultType.SPECIES_DELIMITATION,
            parent_dataset_id="coi-alignment",
            metadata=metadata,
        )
        metadata["tool"] = "changed"

        self.assertEqual(result.result_type, AnalysisResultType.SPECIES_DELIMITATION)
        self.assertEqual(result.parent_dataset_id, "coi-alignment")
        self.assertEqual(result.metadata["tool"], "ASAP")
        with self.assertRaises(TypeError):
            result.metadata["tool"] = "changed"  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            result.name = "Changed"  # type: ignore[misc]

    def test_supports_each_declared_result_type(self) -> None:
        for result_type in AnalysisResultType:
            with self.subTest(result_type=result_type):
                result = AnalysisResult(
                    result_id=f"result-{result_type.value.lower()}",
                    name=result_type.value,
                    result_type=result_type,
                    parent_dataset_id="source",
                )
                self.assertIs(result.result_type, result_type)

    def test_rejects_invalid_result_type_and_required_identifiers(self) -> None:
        with self.assertRaisesRegex(ValueError, "result_type"):
            AnalysisResult(
                "invalid", "Invalid", "BLAST", "source"  # type: ignore[arg-type]
            )
        with self.assertRaisesRegex(ValueError, "result_id"):
            AnalysisResult("", "Name", AnalysisResultType.BOLD, "source")
        with self.assertRaisesRegex(ValueError, "parent_dataset_id"):
            AnalysisResult("result", "Name", AnalysisResultType.BOLD, "")

    def test_blast_result_exposes_compatible_common_result(self) -> None:
        hit = BlastHit(
            query_id="IK345",
            hit_accession="AB123456",
            scientific_name="Rhynchobatus australiae",
            organism="Rhynchobatus australiae",
            identity=99.5,
            query_coverage=98.0,
            evalue=1e-50,
            alignment_length=658,
            database="nt",
        )
        blast_result = BlastResultDataset(
            "blast-coi",
            "COI BLAST",
            (hit,),
            "coi-trimmed",
            metadata={"analysis_mode": "IDENTIFICATION"},
        )

        common_result = blast_result.analysis_result
        self.assertIsInstance(common_result, AnalysisResult)
        self.assertEqual(common_result.result_type, AnalysisResultType.BLAST)
        self.assertEqual(common_result.result_id, blast_result.result_id)
        self.assertEqual(common_result.parent_dataset_id, blast_result.parent_dataset_id)
        self.assertEqual(common_result.metadata, blast_result.metadata)
        self.assertEqual(blast_result.hit_count(), 1)
        self.assertEqual(blast_result.get_hits("IK345"), (hit,))


if __name__ == "__main__":
    unittest.main()
