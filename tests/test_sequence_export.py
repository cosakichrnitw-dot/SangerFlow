"""Tests for standard sequence and alignment exports."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.sequence_dataset import SequenceDataset, SourceType
from export.sequence_export import (
    export_alignment_to_fasta,
    export_alignment_to_nexus,
    export_alignment_to_phylip,
    export_dataset_to_fasta,
    export_dataset_to_nexus,
    export_dataset_to_phylip,
)


def make_sequence_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi", "COI", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"), ("IK346", "ATGT"))
    )


def make_alignment_dataset() -> AlignmentDataset:
    source = make_sequence_dataset()
    return AlignmentDataset.from_sequence_dataset(
        alignment_id="coi-aligned",
        name="COI aligned",
        parent_dataset=source,
        records=(
            AlignmentRecord("IK345", "IK345", "ATG-C"),
            AlignmentRecord("IK346", "IK346", "ATGTC"),
        ),
        marker_regions=(MarkerRegion("COI", 1, 5),),
    )


class SequenceExportTests(unittest.TestCase):
    def test_fasta_preserves_sequence_order_for_sequence_and_alignment_datasets(self) -> None:
        with TemporaryDirectory() as directory:
            fasta = Path(directory) / "coi.fasta"
            aligned_fasta = Path(directory) / "coi-aligned.fasta"
            export_dataset_to_fasta(make_sequence_dataset(), fasta)
            export_alignment_to_fasta(make_alignment_dataset(), aligned_fasta)
            self.assertEqual(fasta.read_text(encoding="utf-8"), ">IK345\nATGC\n>IK346\nATGT\n")
            self.assertEqual(
                aligned_fasta.read_text(encoding="utf-8"),
                ">IK345\nATG-C\n>IK346\nATGTC\n",
            )

    def test_phylip_writes_relaxed_header_and_order(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coi.phy"
            export_dataset_to_phylip(make_sequence_dataset(), path)
            self.assertEqual(path.read_text(encoding="utf-8"), "2 4\nIK345 ATGC\nIK346 ATGT\n")
            alignment_path = Path(directory) / "aligned.phy"
            export_alignment_to_phylip(make_alignment_dataset(), alignment_path)
            self.assertIn("2 5\nIK345 ATG-C\nIK346 ATGTC\n", alignment_path.read_text(encoding="utf-8"))

    def test_nexus_writes_standard_matrix_and_alignment_charsets(self) -> None:
        with TemporaryDirectory() as directory:
            dataset_path = Path(directory) / "coi.nex"
            alignment_path = Path(directory) / "aligned.nex"
            export_dataset_to_nexus(make_sequence_dataset(), dataset_path, metadata={"marker": "COI"})
            export_alignment_to_nexus(make_alignment_dataset(), alignment_path)
            dataset_text = dataset_path.read_text(encoding="utf-8")
            alignment_text = alignment_path.read_text(encoding="utf-8")
            self.assertIn("#NEXUS", dataset_text)
            self.assertIn("BEGIN DATA;", dataset_text)
            self.assertIn("MATRIX", dataset_text)
            self.assertIn("IK345 ATGC", dataset_text)
            self.assertIn("END;", dataset_text)
            self.assertIn("BEGIN SETS;", alignment_text)
            self.assertIn("CHARSET COI = 1-5;", alignment_text)

    def test_rejects_invalid_datasets_taxon_ids_and_unequal_phylip_input(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.out"
            with self.assertRaisesRegex(ValueError, "SequenceDataset"):
                export_dataset_to_fasta(object(), path)  # type: ignore[arg-type]
            invalid_ids = SequenceDataset.from_sequence_pairs(
                "bad", "Bad", SourceType.IMPORTED_FASTA, (("bad id", "ATGC"),)
            )
            with self.assertRaisesRegex(ValueError, "taxon IDs"):
                export_dataset_to_fasta(invalid_ids, path)
            unequal = SequenceDataset.from_sequence_pairs(
                "unequal", "Unequal", SourceType.IMPORTED_FASTA, (("A", "ATGC"), ("B", "ATG"))
            )
            with self.assertRaisesRegex(ValueError, "equal-length"):
                export_dataset_to_phylip(unequal, path)


if __name__ == "__main__":
    unittest.main()
