"""Tests for CSV/XLSX sample metadata import and immutable dataset merge."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from core.lineage import RecordProvenance, RecordRef
from metadata.sample_metadata import (
    import_sample_metadata,
    merge_sample_metadata,
    merge_sample_metadata_for_datasets,
)


def make_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "coi", "COI", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"), ("IK346", "ATGT"))
    )


class SampleMetadataTests(unittest.TestCase):
    @staticmethod
    def duplicate_scope() -> tuple[SequenceDataset, SequenceDataset]:
        return (
            SequenceDataset(
                "run_a", "Run A", SourceType.AB1_TRIMMED,
                (SequenceRecord("R1", "ATGC", metadata={"source_batch": "Batch-A"}),),
            ),
            SequenceDataset(
                "run_b", "Run B", SourceType.AB1_TRIMMED,
                (SequenceRecord("R1", "ATGT", metadata={"source_batch": "Batch-B"}),),
            ),
        )
    def test_imports_csv_and_merges_metadata_without_changing_original_dataset(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "samples.csv"
            path.write_text(
                "Sample_ID,Species,Country,Latitude,Longitude,Voucher\n"
                "IK345,Rhynchobatus,Indonesia,-6.8,110.4,V001\n"
                "IK346,Rhynchobatus,Indonesia,-6.9,110.5,V002\n",
                encoding="utf-8",
            )
            table = import_sample_metadata(path)
            original = make_dataset()
            merged = merge_sample_metadata(original, table)

            self.assertEqual(table.sample_ids, ("IK345", "IK346"))
            self.assertEqual(table.get_record("IK345").metadata["country"], "Indonesia")
            self.assertEqual(table.get_record("IK345").metadata["latitude"], -6.8)
            self.assertEqual(merged.get_record("IK345").metadata["voucher"], "V001")
            self.assertEqual(merged.get_record("IK346").metadata["longitude"], 110.5)
            self.assertEqual(original.get_record("IK345").metadata, {})
            self.assertTrue(merged.metadata["sample_metadata_merged"])
            self.assertEqual(
                merged.get_record("IK345").provenance,
                RecordProvenance((RecordRef("coi", "IK345"),)),
            )
            with self.assertRaises(TypeError):
                merged.get_record("IK345").metadata["country"] = "changed"  # type: ignore[index]

    def test_imports_xlsx(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "samples.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Sample_ID", "Country", "Collection_Date"])
            sheet.append(["IK345", "Indonesia", "2026-08-05"])
            workbook.save(path)
            table = import_sample_metadata(path)

            self.assertEqual(table.columns, ("sample_id", "country", "collection_date"))
            self.assertEqual(table.get_record("IK345").metadata["collection_date"], "2026-08-05")

    def test_rejects_unmatched_duplicate_and_missing_sample_id_column(self) -> None:
        with TemporaryDirectory() as directory:
            unmatched_path = Path(directory) / "unmatched.csv"
            unmatched_path.write_text("Sample_ID,Country\nUNKNOWN,Indonesia\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmatched"):
                merge_sample_metadata(make_dataset(), import_sample_metadata(unmatched_path))

            duplicate_path = Path(directory) / "duplicate.csv"
            duplicate_path.write_text("Sample_ID,Country\nIK345,Indonesia\nIK345,Japan\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate Sample_ID"):
                import_sample_metadata(duplicate_path)

            missing_column = Path(directory) / "missing.csv"
            missing_column.write_text("Species,Country\nRhynchobatus,Indonesia\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Sample_ID"):
                import_sample_metadata(missing_column)

    def test_duplicate_sample_ids_match_source_batch_from_csv_and_preserve_identity(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.csv"
            path.write_text(
                "Sample_ID,Source_Batch,Location,Notes\n"
                "R1,Batch-A,Rembang,日本語の注記\n"
                "R1,Batch-B,Cirebon,échantillon\n",
                encoding="utf-8",
            )
            first, second = merge_sample_metadata_for_datasets(
                self.duplicate_scope(), import_sample_metadata(path)
            )
        self.assertEqual(first.get_record("R1").metadata["location"], "Rembang")
        self.assertEqual(second.get_record("R1").metadata["location"], "Cirebon")
        self.assertEqual(first.get_record("R1").metadata["source_batch"], "Batch-A")
        self.assertEqual(second.get_record("R1").metadata["source_batch"], "Batch-B")
        self.assertEqual(first.get_record("R1").metadata["notes"], "日本語の注記")
        self.assertEqual(first.get_record("R1").sequence_id, "R1")

    def test_duplicate_sample_ids_require_source_batch_and_reject_wrong_or_duplicate_batch(self) -> None:
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.csv"
            missing.write_text("Sample_ID,Location\nR1,Rembang\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "ambiguous metadata match.*R1"):
                merge_sample_metadata_for_datasets(self.duplicate_scope(), import_sample_metadata(missing))

            wrong = Path(directory) / "wrong.csv"
            wrong.write_text("Sample_ID,Source_Batch,Location\nR1,Other,Rembang\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unmatched.*R1"):
                merge_sample_metadata_for_datasets(self.duplicate_scope(), import_sample_metadata(wrong))

            duplicate = Path(directory) / "duplicate.csv"
            duplicate.write_text(
                "Sample_ID,Source_Batch,Location\nR1,Batch-A,Rembang\nR1,Batch-A,Cirebon\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, r"duplicate Sample_ID \+ Source_Batch.*R1"):
                import_sample_metadata(duplicate)

    def test_duplicate_sample_ids_match_source_batch_from_xlsx(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("Sample_ID", "Source_Batch", "Location"))
            sheet.append(("R1", "Batch-A", "Rembang"))
            sheet.append(("R1", "Batch-B", "Cirebon"))
            workbook.save(path)
            workbook.close()
            first, second = merge_sample_metadata_for_datasets(
                self.duplicate_scope(), import_sample_metadata(path)
            )
        self.assertEqual((first.get_record("R1").metadata["location"], second.get_record("R1").metadata["location"]), ("Rembang", "Cirebon"))


if __name__ == "__main__":
    unittest.main()
