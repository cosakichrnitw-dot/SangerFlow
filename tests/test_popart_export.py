from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from export.popart_export import PopArtExportError, build_popart_rows, export_dataset_to_popart_nexus
from core.project import Project
from persistence.project_bundle import load_project_bundle, save_project_bundle


def _dataset() -> SequenceDataset:
    return SequenceDataset(
        "aligned", "Aligned", SourceType.IMPORTED_ALIGNMENT,
        (
            SequenceRecord("s1", "ATGC", metadata={"Location": "North Coast", "sex": "F"}),
            SequenceRecord("s2", "ATGT", metadata={"location": "South Coast", "sex": "M"}),
            SequenceRecord("s3", "ATGA", metadata={"location": "North Coast"}),
            SequenceRecord("s4", "ATGG", metadata={}),
        ),
    )


class PopArtExportTests(unittest.TestCase):
    def test_taxa_data_and_traits_have_matching_ids_and_one_hot_vectors(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "popart.nex"
            export_dataset_to_popart_nexus(_dataset(), path, trait_field="LOCATION")
            text = path.read_text(encoding="utf-8")
        self.assertIn("BEGIN TAXA;", text)
        self.assertIn("BEGIN DATA;", text)
        self.assertIn("BEGIN TRAITS;", text)
        self.assertIn("DIMENSIONS NTAX=4;", text)
        self.assertIn("DIMENSIONS NTRAITS=2;", text)
        self.assertIn("s1 1,0", text)
        self.assertIn("s3 1,0", text)
        self.assertIn("s4 ?,?", text)

    def test_arbitrary_trait_order_and_missing_exclusion(self) -> None:
        rows, categories, _ = build_popart_rows(
            _dataset(), trait_field="sex", category_order=("M", "F"), missing_values="exclude"
        )
        self.assertEqual(categories, ("M", "F"))
        self.assertEqual(tuple(row[0] for row in rows), ("s1", "s2"))
        self.assertEqual(rows[0][2], ("0", "1"))

    def test_label_collision_and_category_order_mismatch_are_rejected(self) -> None:
        collision = SequenceDataset(
            "collision", "Collision", SourceType.IMPORTED_ALIGNMENT,
            (SequenceRecord("a", "ATGC", metadata={"place": "A B"}), SequenceRecord("b", "ATGT", metadata={"place": "A_B"})),
        )
        with self.assertRaisesRegex(PopArtExportError, "collision"):
            build_popart_rows(collision, trait_field="place")
        with self.assertRaisesRegex(PopArtExportError, "exactly"):
            build_popart_rows(_dataset(), trait_field="location", category_order=("North Coast",))

    def test_metadata_survives_bundle_reload_for_popart_export(self) -> None:
        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "project.sangerflow"
            output = Path(directory) / "reloaded.nex"
            save_project_bundle(Project.create("p", "Project").add_dataset(_dataset()), bundle)
            loaded = load_project_bundle(bundle)
            try:
                export_dataset_to_popart_nexus(loaded.project.get_dataset("aligned"), output, trait_field="location")
            finally:
                loaded.cleanup()
            self.assertIn("North_Coast", output.read_text(encoding="utf-8"))
