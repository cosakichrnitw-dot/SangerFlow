"""Tests for immutable BOLD barcode-identification result models."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.analysis_result import AnalysisResultType
from core.bold_result import BoldHit, BoldResultDataset


def make_hit(query_id: str = "IK345", process_id: str | None = "BOLD:AAA001") -> BoldHit:
    return BoldHit(
        query_id=query_id,
        process_id=process_id,
        record_id="REC-001" if process_id == "BOLD:AAA001" else "REC-002",
        species_name="Rhynchobatus australiae",
        genus="Rhynchobatus",
        family="Rhinidae",
        order="Rhinopristiformes",
        phylum="Chordata",
        bin_uri="BOLD:AAA001",
        similarity=99.4,
        database="BOLD",
        country="Indonesia",
        institution="SangerFlow Reference Collection",
        specimen_id="SF-001",
        collection_date="2026-08-05",
    )


class BoldResultTests(unittest.TestCase):
    def test_creates_hit_and_preserves_taxonomy_bin_and_specimen_context(self) -> None:
        hit = make_hit()

        self.assertEqual(hit.query_id, "IK345")
        self.assertEqual(hit.species_name, "Rhynchobatus australiae")
        self.assertEqual(hit.family, "Rhinidae")
        self.assertEqual(hit.bin_uri, "BOLD:AAA001")
        self.assertEqual(hit.country, "Indonesia")
        self.assertEqual(hit.specimen_id, "SF-001")

    def test_dataset_supports_multiple_queries_and_exposes_common_analysis_result(self) -> None:
        first = make_hit("IK345", "BOLD:AAA001")
        second = make_hit("IK346", "BOLD:BBB002")
        metadata = {"workflow": "BOLD identification"}
        result = BoldResultDataset(
            "coi-bold", "COI BOLD", "coi-trimmed", "COI", "BOLD", (first, second), metadata
        )
        metadata["workflow"] = "changed"

        self.assertEqual(result.query_ids(), ("IK345", "IK346"))
        self.assertEqual(result.hit_count(), 2)
        self.assertEqual(result.get_hits("IK345"), (first,))
        self.assertEqual(result.metadata["workflow"], "BOLD identification")
        self.assertEqual(result.analysis_result.result_type, AnalysisResultType.BOLD)
        self.assertEqual(result.analysis_result.parent_dataset_id, "coi-trimmed")
        with self.assertRaises(TypeError):
            result.metadata["workflow"] = "changed"  # type: ignore[index]

    def test_values_are_immutable_and_invalid_similarity_or_identifiers_are_rejected(self) -> None:
        hit = make_hit()
        with self.assertRaises(FrozenInstanceError):
            hit.bin_uri = "BOLD:CHANGED"  # type: ignore[misc]
        with self.assertRaisesRegex(ValueError, "similarity"):
            BoldHit(query_id="IK345", database="BOLD", similarity=100.1)
        with self.assertRaisesRegex(ValueError, "query_id"):
            BoldHit(query_id="", database="BOLD")
        with self.assertRaisesRegex(ValueError, "database"):
            BoldHit(query_id="IK345", database="")

    def test_duplicate_bold_hit_identity_within_query_is_rejected(self) -> None:
        hit = make_hit()
        with self.assertRaisesRegex(ValueError, "duplicate BOLD hit IDs"):
            BoldResultDataset("duplicate", "Duplicate", "input", "COI", "BOLD", (hit, hit))


if __name__ == "__main__":
    unittest.main()
