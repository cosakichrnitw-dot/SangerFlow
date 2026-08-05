"""Tests for immutable query-ID selection from BLAST result datasets."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.blast_filter import BlastResultFilter, BlastResultSelection, apply_blast_filter
from core.blast_result import BlastHit, BlastResultDataset


def hit(
    query_id: str,
    accession: str,
    *,
    scientific_name: str = "Rhynchobatus australiae",
    organism: str = "Rhynchobatus australiae",
    identity: float = 99.0,
    coverage: float = 98.0,
    evalue: float = 1e-30,
) -> BlastHit:
    return BlastHit(
        query_id=query_id,
        hit_accession=accession,
        scientific_name=scientific_name,
        organism=organism,
        identity=identity,
        query_coverage=coverage,
        evalue=evalue,
        alignment_length=658,
        database="nt",
    )


def make_result() -> BlastResultDataset:
    return BlastResultDataset(
        "coi-blast",
        "COI BLAST",
        (
            hit("IK345", "first-345", identity=99.5, coverage=98.0, evalue=1e-50),
            hit("IK345", "second-345", scientific_name="Dasyatis kuhlii", identity=95.0),
            hit("IK346", "first-346", scientific_name="Dasyatis kuhlii", organism="Blue-spotted stingray", identity=96.0, coverage=88.0, evalue=1e-10),
            hit("IK347", "first-347", identity=98.5, coverage=97.0, evalue=1e-5),
        ),
        "coi-trimmed",
    )


class BlastFilterTests(unittest.TestCase):
    def test_scientific_name_and_organism_filters_select_queries_in_source_order(self) -> None:
        result = make_result()
        scientific_selection = apply_blast_filter(
            result, BlastResultFilter(scientific_name="Rhynchobatus australiae")
        )
        organism_selection = apply_blast_filter(
            result, BlastResultFilter(organism="blue-spotted")
        )

        self.assertEqual(scientific_selection.selected_query_ids, ("IK345", "IK347"))
        self.assertEqual(organism_selection.selected_query_ids, ("IK346",))

    def test_identity_coverage_and_evalue_thresholds_apply_to_top_hits(self) -> None:
        result = make_result()

        self.assertEqual(
            apply_blast_filter(result, BlastResultFilter(min_identity=99.0)).selected_query_ids,
            ("IK345",),
        )
        self.assertEqual(
            apply_blast_filter(result, BlastResultFilter(min_coverage=97.0)).selected_query_ids,
            ("IK345", "IK347"),
        )
        self.assertEqual(
            apply_blast_filter(result, BlastResultFilter(max_evalue=1e-20)).selected_query_ids,
            ("IK345",),
        )

    def test_any_hit_policy_is_available_without_changing_default_top_hit_policy(self) -> None:
        result = make_result()
        self.assertEqual(
            apply_blast_filter(
                result, BlastResultFilter(scientific_name="Dasyatis kuhlii")
            ).selected_query_ids,
            ("IK346",),
        )
        self.assertEqual(
            apply_blast_filter(
                result,
                BlastResultFilter(scientific_name="Dasyatis kuhlii", top_hit_only=False),
            ).selected_query_ids,
            ("IK345", "IK346"),
        )

    def test_selection_keeps_source_result_id_and_read_only_filter_metadata(self) -> None:
        result = make_result()
        selection = apply_blast_filter(result, BlastResultFilter(min_identity=98.0))

        self.assertIsInstance(selection, BlastResultSelection)
        self.assertEqual(selection.source_result_id, "coi-blast")
        self.assertEqual(selection.selected_query_ids, ("IK345", "IK347"))
        self.assertEqual(selection.filter_metadata["min_identity"], 98.0)
        self.assertTrue(selection.filter_metadata["top_hit_only"])
        with self.assertRaises(TypeError):
            selection.filter_metadata["min_identity"] = 1.0  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            selection.source_result_id = "changed"  # type: ignore[misc]
        self.assertEqual(result.query_ids(), ("IK345", "IK346", "IK347"))
        self.assertEqual(result.hit_count(), 4)

    def test_rejects_invalid_thresholds_inputs_and_empty_results(self) -> None:
        result = make_result()
        with self.assertRaisesRegex(ValueError, "min_identity"):
            BlastResultFilter(min_identity=101)
        with self.assertRaisesRegex(ValueError, "min_coverage"):
            BlastResultFilter(min_coverage=-1)
        with self.assertRaisesRegex(ValueError, "max_evalue"):
            BlastResultFilter(max_evalue=-1)
        with self.assertRaisesRegex(ValueError, "top_hit_only"):
            BlastResultFilter(top_hit_only="yes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "BlastResultDataset"):
            apply_blast_filter(object(), BlastResultFilter())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            apply_blast_filter(BlastResultDataset("empty", "Empty", (), "input"), BlastResultFilter())


if __name__ == "__main__":
    unittest.main()
