"""Tests for FASTA import into the shared sequence dataset model."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.fasta_dataset import FastaOpenMode, read_fasta_dataset
from core.sequence_dataset import SourceType


class FastaDatasetTests(unittest.TestCase):
    def write_fasta(self, directory: str, filename: str, content: str) -> Path:
        path = Path(directory) / filename
        path.write_text(content, encoding="utf-8")
        return path

    def test_reads_fas_and_fasta_files_preserving_order_and_description(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fas_path = self.write_fasta(
                directory,
                "samples.fas",
                ">IK345 first record\natgc\n>IK346 second record\nATGT\n",
            )
            fasta_path = self.write_fasta(directory, "second.fasta", ">IK347\nATGC\n")

            dataset = read_fasta_dataset(fas_path)
            second = read_fasta_dataset(fasta_path)

        self.assertEqual(dataset.sequence_ids, ("IK345", "IK346"))
        self.assertEqual(dataset.records[0].description, "first record")
        self.assertEqual(dataset.records[1].description, "second record")
        self.assertEqual(dataset.records[0].sequence, "ATGC")
        self.assertEqual(second.sequence_ids, ("IK347",))

    def test_iupac_and_gap_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "iupac.fa", ">sample\nacgtnryswkmbdhv-\n")
            dataset = read_fasta_dataset(path)

        self.assertEqual(dataset.records[0].sequence, "ACGTNRYSWKMBDHV-")
        self.assertTrue(dataset.has_gaps)

    def test_duplicate_ids_empty_input_empty_record_and_invalid_symbols_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = self.write_fasta(directory, "duplicate.fna", ">same\nATGC\n>same\nATGT\n")
            empty = self.write_fasta(directory, "empty.fasta", "")
            empty_record = self.write_fasta(directory, "empty-record.fa", ">empty\n")
            invalid = self.write_fasta(directory, "invalid.fas", ">invalid\nATUZ\n")

            with self.assertRaisesRegex(ValueError, "duplicate"):
                read_fasta_dataset(duplicate)
            with self.assertRaisesRegex(ValueError, "no records"):
                read_fasta_dataset(empty)
            with self.assertRaisesRegex(ValueError, "must not be empty"):
                read_fasta_dataset(empty_record)
            with self.assertRaisesRegex(ValueError, "invalid DNA/IUPAC"):
                read_fasta_dataset(invalid)

    def test_missing_file_and_invalid_open_mode_are_rejected(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "does not exist"):
            read_fasta_dataset("missing.fasta")
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "sample.fasta", ">sample\nATGC\n")
            with self.assertRaisesRegex(ValueError, "open_as"):
                read_fasta_dataset(path, open_as="not-a-mode")

    def test_explicit_and_auto_alignment_classification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            aligned = self.write_fasta(directory, "aligned.fasta", ">one\nATG-C\n>two\nATGTC\n")
            same_length_ungapped = self.write_fasta(directory, "same.fasta", ">one\nATGCA\n>two\nATGTA\n")

            auto_aligned = read_fasta_dataset(aligned, open_as="auto")
            auto_ungapped = read_fasta_dataset(same_length_ungapped, open_as=FastaOpenMode.AUTO)
            explicit_alignment = read_fasta_dataset(same_length_ungapped, open_as="alignment")
            explicit_unaligned = read_fasta_dataset(aligned, open_as="unaligned")

        self.assertEqual(auto_aligned.source_type, SourceType.IMPORTED_ALIGNMENT)
        self.assertTrue(auto_aligned.metadata["inferred_alignment"])
        self.assertEqual(auto_ungapped.source_type, SourceType.IMPORTED_FASTA)
        self.assertFalse(auto_ungapped.metadata["inferred_alignment"])
        self.assertEqual(explicit_alignment.source_type, SourceType.IMPORTED_ALIGNMENT)
        self.assertEqual(explicit_unaligned.source_type, SourceType.IMPORTED_FASTA)

    def test_metadata_is_read_only_and_source_file_is_not_changed(self) -> None:
        content = ">IK345 description\nATGC\n"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "my sample.fasta", content)
            dataset = read_fasta_dataset(path)
            after_read = path.read_text(encoding="utf-8")

        self.assertEqual(after_read, content)
        self.assertEqual(dataset.dataset_id, "my_sample")
        self.assertEqual(dataset.name, "my sample.fasta")
        self.assertEqual(dataset.metadata["original_filename"], "my sample.fasta")
        self.assertEqual(dataset.metadata["requested_open_as"], "auto")
        self.assertEqual(dataset.metadata["sequence_count"], 1)
        self.assertEqual(dataset.metadata["minimum_length"], 4)
        self.assertEqual(dataset.metadata["maximum_length"], 4)
        self.assertFalse(dataset.metadata["has_gaps"])
        with self.assertRaises(TypeError):
            dataset.metadata["name"] = "changed"  # type: ignore[index]

    def test_fasta_content_is_accepted_even_with_an_unusual_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_fasta(directory, "input.sequence", ">sample\nATGC\n")
            dataset = read_fasta_dataset(path)

        self.assertEqual(dataset.sequence_ids, ("sample",))


if __name__ == "__main__":
    unittest.main()
