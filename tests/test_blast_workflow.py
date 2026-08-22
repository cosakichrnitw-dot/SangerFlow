"""Tests for the injected-runner BLAST workflow adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import patch
import unittest

from core.analysis_result import AnalysisResultType
from core.blast_result import BlastAnalysisMode, BlastResultDataset
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.blast_workflow import run_blast_workflow


def make_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-trimmed",
        "COI trimmed reads",
        SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )


def raw_hit(*, accession: str = "AB123456", species: str = "Rhynchobatus australiae") -> dict[str, object]:
    return {
        "species": species,
        "identity": 99.5,
        "coverage": 98.0,
        "alignment_length": 658,
        "e_value": 1e-50,
        "accession": accession,
        "title": f"{accession} {species}",
    }


class BlastWorkflowTests(unittest.TestCase):
    def test_runner_builds_ordered_identification_result_and_common_analysis_result(self) -> None:
        dataset = make_dataset()
        calls: list[str] = []

        def runner(sequence: str) -> list[dict[str, object]]:
            calls.append(sequence)
            return [raw_hit(accession=f"ACC-{sequence[-1]}")]

        result = run_blast_workflow(
            dataset,
            analysis_mode=BlastAnalysisMode.IDENTIFICATION,
            marker="COI",
            database="nt",
            runner=runner,
        )

        self.assertIsInstance(result, BlastResultDataset)
        self.assertEqual(calls, ["ATGC", "ATGT"])
        self.assertEqual(result.parent_dataset_id, "coi-trimmed")
        self.assertEqual(result.analysis_mode, BlastAnalysisMode.IDENTIFICATION)
        self.assertEqual(result.marker, "COI")
        self.assertEqual(result.database, "nt")
        self.assertEqual(result.query_ids(), ("IK345", "IK346"))
        self.assertEqual(tuple(hit.hit_accession for hit in result.get_hits("IK345")), ("ACC-C",))
        self.assertEqual(result.analysis_result.result_type, AnalysisResultType.BLAST)
        self.assertEqual(result.analysis_result.parent_dataset_id, dataset.dataset_id)
        self.assertEqual(result.metadata["input_source_type"], SourceType.AB1_TRIMMED.value)
        self.assertEqual(dataset.records[0].sequence, "ATGC")
        with self.assertRaises(FrozenInstanceError):
            result.name = "changed"  # type: ignore[misc]

    def test_qc_mode_uses_injected_runner_and_preserves_multiple_hit_order(self) -> None:
        dataset = make_dataset()
        result = run_blast_workflow(
            dataset,
            analysis_mode=BlastAnalysisMode.QC,
            database="contaminant-check",
            runner=lambda sequence: [raw_hit(accession=f"first-{sequence}"), raw_hit(accession=f"second-{sequence}")],
        )

        self.assertEqual(result.analysis_mode, BlastAnalysisMode.QC)
        self.assertEqual(result.database, "contaminant-check")
        self.assertEqual(
            tuple(hit.hit_accession for hit in result.hits),
            ("first-ATGC", "second-ATGC", "first-ATGT", "second-ATGT"),
        )

    def test_default_runner_delegates_to_ncbi_url_api_runner(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"),)
        )
        with patch("workflow.ncbi_blast_service.NcbiBlastRunner.__call__", return_value=[raw_hit()]) as ncbi_runner:
            result = run_blast_workflow(
                dataset,
                analysis_mode=BlastAnalysisMode.IDENTIFICATION,
                database="nt",
            )

        ncbi_runner.assert_called_once_with("ATGC")
        self.assertEqual(result.hit_count(), 1)

    def test_rejects_invalid_inputs_and_empty_runner_results(self) -> None:
        dataset = make_dataset()
        with self.assertRaisesRegex(ValueError, "analysis_mode"):
            run_blast_workflow(dataset, analysis_mode="QC", runner=lambda _: [raw_hit()])  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "database"):
            run_blast_workflow(dataset, analysis_mode=BlastAnalysisMode.QC, database=" ", runner=lambda _: [raw_hit()])
        with self.assertRaisesRegex(ValueError, "no hits"):
            run_blast_workflow(dataset, analysis_mode=BlastAnalysisMode.QC, runner=lambda _: [])
        with self.assertRaisesRegex(ValueError, "hit mappings"):
            run_blast_workflow(dataset, analysis_mode=BlastAnalysisMode.QC, runner=lambda _: ["not-a-hit"])  # type: ignore[list-item]


if __name__ == "__main__":
    unittest.main()
