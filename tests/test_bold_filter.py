"""Tests for immutable query-ID selection from BOLD result datasets."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from core.bold_filter import BoldResultFilter, BoldResultSelection, apply_bold_filter
from core.bold_result import BoldHit, BoldResultDataset


def hit(
    query_id: str,
    process_id: str,
    *,
    species_name: str = "Rhynchobatus australiae",
    genus: str = "Rhynchobatus",
    family: str = "Rhinidae",
    bin_uri: str = "BOLD:AAA001",
    similarity: float | None = 99.0,
    country: str | None = "Indonesia",
) -> BoldHit:
    return BoldHit(
        query_id=query_id,
        process_id=process_id,
        species_name=species_name,
        genus=genus,
        family=family,
        bin_uri=bin_uri,
        similarity=similarity,
        country=country,
        database="BOLD",
    )


def make_result() -> BoldResultDataset:
    return BoldResultDataset(
        "coi-bold",
        "COI BOLD",
        "coi-trimmed",
        "COI",
        "BOLD",
        (
            hit("IK345", "first-345", similarity=99.5, country="Indonesia"),
            hit("IK345", "second-345", species_name="Dasyatis kuhlii", genus="Dasyatis", similarity=95.0),
            hit("IK346", "first-346", species_name="Dasyatis kuhlii", genus="Dasyatis", family="Dasyatidae", similarity=96.0, country="Malaysia"),
            hit("IK347", "first-347", similarity=98.5, country="Indonesia"),
        ),
    )


class BoldFilterTests(unittest.TestCase):
    def test_taxonomic_and_country_criteria_select_source_query_order(self) -> None:
        result = make_result()
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(species_name="Rhynchobatus australiae")).selected_query_ids,
            ("IK345", "IK347"),
        )
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(genus="Dasyatis")).selected_query_ids,
            ("IK346",),
        )
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(country="malay")).selected_query_ids,
            ("IK346",),
        )

    def test_similarity_and_bin_criteria_apply_to_top_hits(self) -> None:
        result = make_result()
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(min_similarity=99.0)).selected_query_ids,
            ("IK345",),
        )
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(bin_uri="BOLD:AAA001")).selected_query_ids,
            ("IK345", "IK346", "IK347"),
        )

    def test_any_hit_policy_is_available_without_changing_default_top_hit_policy(self) -> None:
        result = make_result()
        self.assertEqual(
            apply_bold_filter(result, BoldResultFilter(species_name="Dasyatis kuhlii")).selected_query_ids,
            ("IK346",),
        )
        self.assertEqual(
            apply_bold_filter(
                result,
                BoldResultFilter(species_name="Dasyatis kuhlii", top_hit_only=False),
            ).selected_query_ids,
            ("IK345", "IK346"),
        )

    def test_selection_keeps_source_result_and_read_only_filter_metadata(self) -> None:
        result = make_result()
        selection = apply_bold_filter(result, BoldResultFilter(min_similarity=98.0))

        self.assertIsInstance(selection, BoldResultSelection)
        self.assertEqual(selection.source_result_id, "coi-bold")
        self.assertEqual(selection.selected_query_ids, ("IK345", "IK347"))
        self.assertEqual(selection.filter_metadata["min_similarity"], 98.0)
        self.assertTrue(selection.filter_metadata["top_hit_only"])
        with self.assertRaises(TypeError):
            selection.filter_metadata["min_similarity"] = 1.0  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            selection.source_result_id = "changed"  # type: ignore[misc]
        self.assertEqual(result.query_ids(), ("IK345", "IK346", "IK347"))
        self.assertEqual(result.hit_count(), 4)

    def test_rejects_invalid_criteria_inputs_and_empty_results(self) -> None:
        result = make_result()
        with self.assertRaisesRegex(ValueError, "min_similarity"):
            BoldResultFilter(min_similarity=101)
        with self.assertRaisesRegex(ValueError, "country"):
            BoldResultFilter(country="")
        with self.assertRaisesRegex(ValueError, "top_hit_only"):
            BoldResultFilter(top_hit_only="yes")  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "BoldResultDataset"):
            apply_bold_filter(object(), BoldResultFilter())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "at least one hit"):
            apply_bold_filter(
                BoldResultDataset("empty", "Empty", "input", None, "BOLD", ()),
                BoldResultFilter(),
            )


if __name__ == "__main__":
    unittest.main()
