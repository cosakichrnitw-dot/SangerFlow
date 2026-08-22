"""Tests for portable Project zip bundles."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.project import DerivationType, Project
from core.result_repository import FilesystemResultRepository
from core.sequence_dataset import SequenceDataset, SourceType
from persistence.project_bundle import (
    PROJECT_BUNDLE_SCHEMA_VERSION,
    ProjectBundleError,
    ProjectBundleOptions,
    load_project_bundle,
    save_project_bundle,
)


def make_project_and_result() -> tuple[Project, BlastResultDataset]:
    source = SequenceDataset.from_sequence_pairs(
        "coi", "COI", SourceType.IMPORTED_FASTA, (("IK345", "ATGC"),)
    )
    aligned = SequenceDataset.from_sequence_pairs(
        "coi-aligned", "COI aligned", SourceType.IMPORTED_ALIGNMENT, (("IK345", "ATGC"),)
    )
    project = Project.create("central-java", "Central Java", {"marker": "COI"})
    project = project.add_dataset(source)
    project = project.add_dataset(
        aligned,
        parent_dataset_id="coi",
        derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
    )
    result = BlastResultDataset(
        result_id="blast-001",
        name="BLAST result",
        parent_dataset_id="coi-aligned",
        analysis_mode=BlastAnalysisMode.IDENTIFICATION,
        database="nt",
        hits=(BlastHit("IK345", "AB1", "Species", "Species sp.", 99, 100, 0, 650, "nt"),),
    )
    return project.add_analysis_result(result.analysis_result), result


class ProjectBundleTests(unittest.TestCase):
    def test_save_load_roundtrip_preserves_project_lineage_and_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project, result = make_project_and_result()
            repository = FilesystemResultRepository(root / "repository")
            repository.register_result(result)
            bundle = root / "central-java.sangerflow"

            save_project_bundle(project, bundle, repository=repository)
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("project.json", archive.namelist())
                self.assertIn("bundle.json", archive.namelist())
                self.assertIn("datasets/manifest.json", archive.namelist())
                self.assertIn("results/index.json", archive.namelist())
                self.assertIn("metadata/manifest.json", archive.namelist())

            loaded = load_project_bundle(bundle)
            try:
                self.assertEqual(loaded.project.dataset_ids, ("coi", "coi-aligned"))
                self.assertEqual(loaded.project.lineage("coi-aligned"), ("coi", "coi-aligned"))
                self.assertEqual(loaded.project.analysis_lineage("blast-001"), ("coi", "coi-aligned", "blast-001"))
                self.assertEqual(loaded.repository.get_result("blast-001").hits, result.hits)
                self.assertEqual(loaded.metadata["schema_version"], PROJECT_BUNDLE_SCHEMA_VERSION)
            finally:
                loaded.cleanup()
            self.assertEqual(project.dataset_ids, ("coi", "coi-aligned"))

    def test_options_can_exclude_result_payloads(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            project, result = make_project_and_result()
            repository = FilesystemResultRepository(root / "repository")
            repository.register_result(result)
            bundle = root / "without-results.sangerflow"
            save_project_bundle(project, bundle, repository, {"include_results": False})
            loaded = load_project_bundle(bundle)
            try:
                self.assertFalse(loaded.repository.has_result("blast-001"))
                self.assertTrue(loaded.project.has_analysis_result("blast-001"))
            finally:
                loaded.cleanup()

    def test_raw_data_embedding_option_is_explicitly_rejected(self) -> None:
        """Avoid falsely claiming that portable bundles contain AB1 payloads."""

        with TemporaryDirectory() as directory:
            project, _result = make_project_and_result()
            with self.assertRaisesRegex(ProjectBundleError, "include_raw_data is not implemented"):
                save_project_bundle(
                    project,
                    Path(directory) / "raw-requested.sangerflow",
                    options=ProjectBundleOptions(include_raw_data=True),
                )

    def test_rejects_corrupt_missing_project_and_unsupported_schema_bundles(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corrupt = root / "corrupt.sangerflow"
            corrupt.write_text("not a zip", encoding="utf-8")
            with self.assertRaises(ProjectBundleError):
                load_project_bundle(corrupt)

            missing_project = root / "missing-project.sangerflow"
            with zipfile.ZipFile(missing_project, "w") as archive:
                archive.writestr(
                    "bundle.json",
                    json.dumps(
                        {
                            "schema_version": PROJECT_BUNDLE_SCHEMA_VERSION,
                            "sangerflow_version": "development",
                            "created_at": "2026-08-05T00:00:00+00:00",
                        }
                    ),
                )
            with self.assertRaisesRegex(ProjectBundleError, "project.json"):
                load_project_bundle(missing_project)

            unsupported = root / "unsupported.sangerflow"
            with zipfile.ZipFile(unsupported, "w") as archive:
                archive.writestr(
                    "bundle.json",
                    json.dumps(
                        {
                            "schema_version": PROJECT_BUNDLE_SCHEMA_VERSION + 1,
                            "sangerflow_version": "development",
                            "created_at": "2026-08-05T00:00:00+00:00",
                        }
                    ),
                )
                archive.writestr("project.json", "{}")
            with self.assertRaisesRegex(ProjectBundleError, "schema_version"):
                load_project_bundle(unsupported)


if __name__ == "__main__":
    unittest.main()
