"""Tests for marker-region partition definitions."""

from __future__ import annotations

import unittest

from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.sequence_dataset import SequenceDataset, SourceType
from export.partition_export import PartitionDefinition, create_partition_definition


def make_source() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "source", "Source", SourceType.IMPORTED_FASTA, (("A", "ATGCATGC"), ("B", "ATGTATGC"))
    )


def make_alignment(regions: tuple[MarkerRegion, ...]) -> AlignmentDataset:
    return AlignmentDataset.from_sequence_dataset(
        alignment_id="aligned",
        name="Aligned",
        parent_dataset=make_source(),
        records=(
            AlignmentRecord("A", "A", "ATGCATGC"),
            AlignmentRecord("B", "B", "ATGTATGC"),
        ),
        marker_regions=regions,
    )


class PartitionExportTests(unittest.TestCase):
    def test_single_marker_generates_all_supported_formats(self) -> None:
        definition = create_partition_definition(make_alignment((MarkerRegion("COI", 1, 8),)))

        self.assertIsInstance(definition, PartitionDefinition)
        self.assertEqual(definition.iqtree, "COI = 1-8")
        self.assertEqual(definition.raxml, "DNA, COI = 1-8")
        self.assertEqual(definition.nexus_charset, "CHARSET COI = 1-8;")

    def test_multiple_markers_preserve_marker_order_for_concatenation(self) -> None:
        definition = create_partition_definition(
            make_alignment((MarkerRegion("COI", 1, 5), MarkerRegion("12S", 6, 8)))
        )

        self.assertEqual(definition.iqtree, "COI = 1-5\n12S = 6-8")
        self.assertEqual(definition.raxml, "DNA, COI = 1-5\nDNA, 12S = 6-8")
        self.assertEqual(
            definition.nexus_charset,
            "CHARSET COI = 1-5;\nCHARSET 12S = 6-8;",
        )

    def test_rejects_overlap_missing_regions_and_invalid_model_ranges(self) -> None:
        overlapping = make_alignment((MarkerRegion("COI", 1, 5), MarkerRegion("12S", 5, 8)))
        with self.assertRaisesRegex(ValueError, "overlap"):
            create_partition_definition(overlapping)
        with self.assertRaisesRegex(ValueError, "at least one marker"):
            create_partition_definition(make_alignment(()))
        with self.assertRaisesRegex(ValueError, "outside alignment length"):
            make_alignment((MarkerRegion("COI", 1, 9),))
        with self.assertRaisesRegex(ValueError, "1-based"):
            MarkerRegion("COI", 5, 4)


if __name__ == "__main__":
    unittest.main()
