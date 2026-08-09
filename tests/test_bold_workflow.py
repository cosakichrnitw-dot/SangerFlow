"""Tests for the injected-runner BOLD workflow adapter."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.analysis_result import AnalysisResultType
from core.bold_result import BoldResultDataset
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.bold_workflow import BoldWorkflowError, run_bold_workflow


def make_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi-trimmed",
        "COI trimmed reads",
        SourceType.AB1_TRIMMED,
        (("IK345", "ATGC"), ("IK346", "ATGT")),
    )


def raw_hit(query_id: str, *, process_id: str = "BOLD:AAA001", similarity: float = 99.4) -> dict[str, object]:
    return {
        "query_id": query_id,
        "process_id": process_id,
        "record_id": f"REC-{query_id}",
        "species_name": "Rhynchobatus australiae",
        "genus": "Rhynchobatus",
        "family": "Rhinidae",
        "bin_uri": "BOLD:AAA001",
        "similarity": similarity,
        "country": "Indonesia",
    }


class BoldWorkflowTests(unittest.TestCase):
    def test_runner_creates_bold_result_with_metadata_and_common_analysis_result(self) -> None:
        dataset = make_dataset()
        calls: list[str] = []

        def runner(sequence: str) -> dict[str, object]:
            calls.append(sequence)
            query_id = "IK345" if sequence == "ATGC" else "IK346"
            return raw_hit(query_id, process_id=f"BOLD:{query_id}")

        result = run_bold_workflow(dataset, marker="COI", database="BOLD", runner=runner)

        self.assertIsInstance(result, BoldResultDataset)
        self.assertEqual(calls, ["ATGC", "ATGT"])
        self.assertEqual(result.parent_dataset_id, "coi-trimmed")
        self.assertEqual(result.marker, "COI")
        self.assertEqual(result.database, "BOLD")
        self.assertEqual(result.query_ids(), ("IK345", "IK346"))
        self.assertEqual(result.get_hits("IK345")[0].process_id, "BOLD:IK345")
        self.assertEqual(result.metadata["parent_dataset_id"], "coi-trimmed")
        self.assertEqual(result.metadata["marker"], "COI")
        self.assertEqual(result.metadata["database"], "BOLD")
        self.assertEqual(result.metadata["workflow"], "BOLD")
        self.assertEqual(result.analysis_result.result_type, AnalysisResultType.BOLD)
        self.assertEqual(dataset.records[0].sequence, "ATGC")
        with self.assertRaises(FrozenInstanceError):
            result.name = "changed"  # type: ignore[misc]

    def test_runner_accepts_multiple_raw_hit_mappings_per_query(self) -> None:
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"),)
        )
        result = run_bold_workflow(
            dataset,
            runner=lambda _sequence: [
                raw_hit("IK345", process_id="BOLD:ONE"),
                raw_hit("IK345", process_id="BOLD:TWO"),
            ],
        )
        self.assertEqual(result.hit_count(), 2)
        self.assertEqual(
            tuple(hit.process_id for hit in result.get_hits("IK345")),
            ("BOLD:ONE", "BOLD:TWO"),
        )

    def test_rejects_missing_runner_empty_results_query_mismatch_and_invalid_similarity(self) -> None:
        dataset = make_dataset()
        with self.assertRaisesRegex(BoldWorkflowError, "not configured"):
            run_bold_workflow(dataset)
        with self.assertRaisesRegex(BoldWorkflowError, "no hits"):
            run_bold_workflow(dataset, runner=lambda _sequence: [])
        with self.assertRaisesRegex(BoldWorkflowError, "does not match"):
            run_bold_workflow(dataset, runner=lambda _sequence: raw_hit("wrong"))
        with self.assertRaisesRegex(ValueError, "similarity"):
            run_bold_workflow(dataset, runner=lambda _sequence: raw_hit("IK345", similarity=101))
        with self.assertRaisesRegex(BoldWorkflowError, "dataset must"):
            run_bold_workflow(object(), runner=lambda _sequence: raw_hit("IK345"))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
