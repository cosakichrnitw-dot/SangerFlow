"""Focused coverage for the read-only Project QC & Provenance summary."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
studio_root = Path(__file__).resolve().parents[1]
repository_root = studio_root.parent
sys.path.insert(0, str(studio_root))
sys.path.insert(0, str(repository_root))

from app.qt_runtime import configure_qt_plugins

configure_qt_plugins()

from PySide6.QtWidgets import QApplication

from app.app_state import AppState
from app.main_window import MainWindow
from controllers.project_controller import ProjectController
from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.blast_result import BlastHit, BlastResultDataset
from core.lineage import LineageRelation, LineageRelationType, LineageSourceKind, RecordProvenance, RecordRef
from core.project import Project, RevisionOperation
from core.result_repository import FilesystemResultRepository
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType
from persistence.project_bundle import load_project_bundle, save_project_bundle
from services.project_provenance_summary import (
    AVAILABLE,
    NOT_RECORDED,
    UNAVAILABLE,
    build_project_provenance_summary,
    provenance_chain,
)
from widgets.viewers.project_provenance_viewer import ProjectProvenanceViewer
from widgets.viewers.viewer_context import ViewerContext


class _TabRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    def open_viewer(self, viewer: object, *, resource_key: str) -> str:
        self.calls.append((viewer, resource_key))
        return getattr(viewer, "viewer_id")


def _project() -> Project:
    raw_a = SequenceDataset(
        "raw-a", "Cirebon reads", SourceType.AB1_TRIMMED,
        (SequenceRecord("R1", "ATGC", metadata={"source_batch": "Cirebon", "source_filename": "R1.ab1", "source_filepath": "/missing/R1.ab1"}),),
    )
    raw_b = SequenceDataset(
        "raw-b", "Rembang reads", SourceType.AB1_TRIMMED,
        (SequenceRecord("R1", "ATGT", metadata={"source_batch": "Rembang", "source_filename": "R1.ab1"}),),
    )
    reviewed = SequenceDataset(
        "reviewed", "Reviewed Consensus", SourceType.REVIEWED_CONSENSUS,
        (SequenceRecord(
            "sample-1", "ATGC", metadata={
                "original_consensus": "ATGT", "reviewed_consensus": "ATGC",
                "review_decisions": ({"position": 4, "from": "T", "to": "C"},),
                "blast_best_hit": "Rhynchobatus australiae mitochondrion",
                "blast_scientific_name": "Rhynchobatus australiae",
                "blast_identity": 99.1, "blast_query_coverage": 100.0,
                "blast_accession": "ACC1",
                "pairing_resolution": "MANUAL",
            },
            provenance=RecordProvenance((RecordRef("raw-a", "R1"), RecordRef("raw-b", "R1"))),
        ),),
    )
    derived = SequenceDataset(
        "derived", "Derived selection", SourceType.DERIVED,
        (SequenceRecord("sample-1", "ATGC", provenance=RecordProvenance((RecordRef("reviewed", "sample-1"),))),),
    )
    alignment_one = AlignmentDataset(
        "alignment-r1", "COI alignment", "derived",
        (AlignmentRecord("sample-1", "sample-1", "AT-GC"),),
        marker_regions=(MarkerRegion("COI", 1, 5),),
        metadata={"excluded_columns": (2,), "edited_positions": (("sample-1", 3),)},
    )
    alignment_two = AlignmentDataset(
        "alignment-r2", "COI alignment", "derived",
        (AlignmentRecord("sample-1", "sample-1", "AT-NC"),),
        metadata={"deleted_columns": (3,), "marker_regions_invalidated_by_deleted_columns": True},
    )
    project = Project.create("project", "QC Project").add_dataset(raw_a).add_dataset(raw_b)
    project = project.add_dataset(
        reviewed,
        lineage_relations=(
            LineageRelation(LineageSourceKind.DATASET, "raw-a", LineageRelationType.REVIEWED_FROM_CONSENSUS),
            LineageRelation(LineageSourceKind.DATASET, "raw-b", LineageRelationType.REVIEWED_FROM_CONSENSUS),
        ),
    )
    project = project.add_dataset(
        derived,
        lineage_relations=(LineageRelation(LineageSourceKind.DATASET, "reviewed", LineageRelationType.SUBSET_FROM_DATASET),),
    )
    project = project.add_dataset(
        alignment_one,
        lineage_relations=(LineageRelation(LineageSourceKind.DATASET, "derived", LineageRelationType.ALIGNMENT_FROM_DATASET),),
    )
    return project.add_dataset_revision(
        "alignment-r1", alignment_two, operation=RevisionOperation.ALIGNMENT_EDIT,
        lineage_relations=project.get_entry("alignment-r1").lineage_relations,
    )


class ProjectProvenanceSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_overview_lineage_and_alignment_are_persisted_facts(self) -> None:
        summary = build_project_provenance_summary(_project())
        self.assertEqual(summary.overview.dataset_count, 6)
        self.assertEqual(summary.overview.sequence_dataset_count, 4)
        self.assertEqual(summary.overview.alignment_dataset_count, 2)
        self.assertEqual((summary.overview.current_count, summary.overview.superseded_count, summary.overview.archived_count), (5, 1, 0))
        revised = next(row for row in summary.lineage if row.dataset_id == "alignment-r2")
        self.assertEqual(revised.revision, 2)
        self.assertIn("Revision: alignment-r1", revised.sources)
        alignment = next(row for row in summary.alignments if row.dataset_id == "alignment-r2")
        self.assertEqual(alignment.deleted_columns, "1")
        self.assertEqual(alignment.marker_region_state, "Invalidated by column deletion")

    def test_recursive_recordrefs_preserve_same_named_source_records_and_reviewed_pair(self) -> None:
        summary = build_project_provenance_summary(_project())
        chain = provenance_chain(summary, RecordRef("derived", "sample-1"))
        self.assertEqual(tuple(node.record_ref for node in chain), (
            RecordRef("derived", "sample-1"), RecordRef("reviewed", "sample-1"),
            RecordRef("raw-a", "R1"), RecordRef("raw-b", "R1"),
        ))
        self.assertEqual(chain[2].source_batch, "Cirebon")
        self.assertEqual(chain[3].source_batch, "Rembang")
        self.assertEqual(chain[2].ab1_source_state, UNAVAILABLE)
        self.assertEqual(chain[3].ab1_source_state, NOT_RECORDED)
        self.assertEqual(chain[1].review_pairing_state, "Reviewed consensus (1 change); 1 persisted decision; Manual pair")

    def test_blast_metadata_is_not_misrepresented_as_payload(self) -> None:
        project = _project()
        summary = build_project_provenance_summary(project)
        identification = next(row for row in summary.identifications if row.dataset_id == "reviewed")
        self.assertEqual(identification.scientific_name, "Rhynchobatus australiae")
        self.assertEqual(identification.result_id, NOT_RECORDED)
        self.assertEqual(identification.payload_state, NOT_RECORDED)

        result = BlastResultDataset(
            "blast-1", "BLAST", (
                BlastHit("sample-1", "ACC1", "Rhynchobatus australiae", "Rhynchobatus australiae", 99.1, 100.0, 0.0, 4, "nt"),
            ), "reviewed",
        )
        project = project.add_analysis_result(result.analysis_result)
        unresolved = build_project_provenance_summary(project)
        unresolved_row = next(item for item in unresolved.identifications if item.dataset_id == "reviewed")
        self.assertEqual(unresolved_row.result_id, "blast-1")
        self.assertEqual(unresolved_row.result_reference_state, AVAILABLE)
        self.assertEqual(unresolved_row.payload_state, UNAVAILABLE)
        with TemporaryDirectory() as directory:
            repository = FilesystemResultRepository(directory)
            repository.register_result(result)
            resolved = build_project_provenance_summary(project, result_repository=repository)
            row = next(item for item in resolved.identifications if item.dataset_id == "reviewed")
            self.assertEqual(row.result_id, "blast-1")
            self.assertEqual(row.result_reference_state, AVAILABLE)
            self.assertEqual(row.payload_state, AVAILABLE)

    def test_ab1_availability_uses_safe_absolute_then_workspace_candidates(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "original.ab1"
            original.touch()
            workspace_file = root / "Raw_Data" / "workspace.ab1"
            workspace_file.parent.mkdir()
            workspace_file.touch()

            def state_for(metadata: dict[str, object]) -> str:
                dataset = SequenceDataset(
                    "sources",
                    "Sources",
                    SourceType.AB1_TRIMMED,
                    (SequenceRecord("read", "ATGC", metadata=metadata),),
                )
                project = Project.create("sources-project", "Sources").add_dataset(dataset)
                return build_project_provenance_summary(project, workspace_root=root).provenance_nodes[
                    RecordRef("sources", "read")
                ].ab1_source_state

            self.assertEqual(state_for({"source_filepath": str(original)}), AVAILABLE)
            self.assertEqual(
                state_for({
                    "source_filepath": str(root / "missing-original.ab1"),
                    "workspace_relative_path": "Raw_Data/workspace.ab1",
                }),
                AVAILABLE,
            )
            self.assertEqual(
                state_for({
                    "source_filepath": str(root / "missing-original.ab1"),
                    "workspace_relative_path": "Raw_Data/missing-workspace.ab1",
                }),
                UNAVAILABLE,
            )
            self.assertEqual(state_for({}), NOT_RECORDED)

    def test_dangling_and_cyclic_provenance_terminate_safely(self) -> None:
        dangling = SequenceDataset(
            "dangling",
            "Dangling",
            SourceType.DERIVED,
            (SequenceRecord("record", "ATGC", provenance=RecordProvenance((RecordRef("missing", "source"),))),),
        )
        dangling_project = Project.create("dangling-project", "Dangling").add_dataset(dangling)
        dangling_summary = build_project_provenance_summary(dangling_project)
        dangling_chain = provenance_chain(dangling_summary, RecordRef("dangling", "record"))
        self.assertEqual(dangling_chain[-1].record_ref, RecordRef("missing", "source"))
        self.assertEqual(dangling_chain[-1].state, UNAVAILABLE)

        left = SequenceDataset(
            "left", "Left", SourceType.DERIVED,
            (SequenceRecord("record", "ATGC", provenance=RecordProvenance((RecordRef("right", "record"),))),),
        )
        right = SequenceDataset(
            "right", "Right", SourceType.DERIVED,
            (SequenceRecord("record", "ATGC", provenance=RecordProvenance((RecordRef("left", "record"),))),),
        )
        cyclic_project = Project.create("cyclic-project", "Cyclic").add_dataset(left).add_dataset(right)
        cyclic_summary = build_project_provenance_summary(cyclic_project)
        cyclic_chain = provenance_chain(cyclic_summary, RecordRef("left", "record"))
        self.assertEqual(tuple(node.record_ref for node in cyclic_chain), (RecordRef("left", "record"), RecordRef("right", "record")))

    def test_explicit_zero_count_is_not_no_record(self) -> None:
        alignment = AlignmentDataset(
            "zero-alignment", "Zero alignment", "derived",
            (AlignmentRecord("sample", "sample", "ATGC"),),
            metadata={"excluded_columns": ()},
        )
        project = Project.create("zero-project", "Zero").add_dataset(alignment)
        row = build_project_provenance_summary(project).alignments[0]
        self.assertEqual(row.excluded_columns, "0")
        self.assertEqual(row.deleted_columns, "No record")

    def test_summary_does_not_invoke_scientific_workflows(self) -> None:
        with (
            patch("core.ab1_reader.read_ab1", side_effect=AssertionError("AB1 parsing")),
            patch("core.consensus.build_consensus", side_effect=AssertionError("consensus")),
            patch("workflow.mafft_workflow.align_sequence_dataset", side_effect=AssertionError("MAFFT")),
            patch("workflow.ncbi_blast_service.NcbiBlastRunner.run_dataset", side_effect=AssertionError("BLAST")),
        ):
            summary = build_project_provenance_summary(_project())
        self.assertEqual(summary.overview.dataset_count, 6)

    def test_summary_is_read_only_and_bundle_reopen_keeps_persisted_facts(self) -> None:
        project = _project()
        before = project
        summary = build_project_provenance_summary(project)
        self.assertIs(project, before)
        with TemporaryDirectory() as directory:
            bundle = Path(directory) / "project.sangerflow"
            save_project_bundle(project, bundle)
            loaded = load_project_bundle(bundle).project
        reloaded = build_project_provenance_summary(loaded)
        self.assertEqual(summary.overview, reloaded.overview)
        self.assertEqual(summary.lineage, reloaded.lineage)

    def test_viewer_is_read_only(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        project = _project()
        state.set_project(project)
        viewer = ProjectProvenanceViewer(project, ViewerContext(state, controller))
        self.assertEqual(viewer.viewer_title, "Project QC & Provenance")
        self.assertEqual(viewer.summary.overview.dataset_count, 6)
        self.assertFalse(viewer.is_dirty)
        viewer.close_viewer()
        viewer.deleteLater()

    def test_viewer_displays_blast_identity_and_query_coverage(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        state.set_project(_project())
        viewer = ProjectProvenanceViewer(_project(), ViewerContext(state, controller))
        try:
            headers = tuple(
                viewer._identification_table.horizontalHeaderItem(index).text()
                for index in range(viewer._identification_table.columnCount())
            )
            self.assertIn("Identity", headers)
            self.assertIn("Query Coverage", headers)
            row = next(
                row_index
                for row_index in range(viewer._identification_table.rowCount())
                if viewer._identification_table.item(row_index, 1).text() == "sample-1"
            )
            self.assertEqual(viewer._identification_table.item(row, headers.index("Identity")).text(), "99.1")
            self.assertEqual(viewer._identification_table.item(row, headers.index("Query Coverage")).text(), "100.0")
        finally:
            viewer.close_viewer()
            viewer.deleteLater()

    def test_viewer_resolves_workspace_source_from_current_bundle(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "Raw_Data" / "read.ab1"
            source.parent.mkdir()
            source.touch()
            dataset = SequenceDataset(
                "workspace-source",
                "Workspace source",
                SourceType.AB1_TRIMMED,
                (SequenceRecord(
                    "read",
                    "ATGC",
                    metadata={
                        "source_filepath": str(root / "missing-original.ab1"),
                        "workspace_relative_path": "Raw_Data/read.ab1",
                    },
                ),),
            )
            project = Project.create("workspace-project", "Workspace").add_dataset(dataset)
            state = AppState()
            controller = ProjectController(state)
            state.set_project(project, bundle_path=str(root / "workspace.sangerflow"))
            viewer = ProjectProvenanceViewer(project, ViewerContext(state, controller))
            try:
                node = viewer.summary.provenance_nodes[RecordRef("workspace-source", "read")]
                self.assertEqual(node.ab1_source_state, AVAILABLE)
            finally:
                viewer.close_viewer()
                viewer.deleteLater()

    def test_controller_opens_one_project_level_viewer_with_stable_resource_key(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        project = _project()
        state.set_project(project)
        tabs = _TabRecorder()
        context = ViewerContext(state, controller, tab_manager=tabs)
        controller.configure_viewer_framework(viewer_registry=object(), viewer_context=context, tab_manager=tabs)
        viewer = controller.open_project_provenance_viewer()
        self.assertEqual(viewer.viewer_title, "Project QC & Provenance")
        self.assertEqual(len(tabs.calls), 1)
        self.assertEqual(tabs.calls[0][1], "project-provenance:project")
        viewer.close_viewer()
        viewer.deleteLater()

    def test_project_menu_exposes_summary_only_when_project_is_open(self) -> None:
        state = AppState()
        controller = ProjectController(state)
        window = MainWindow(state, controller)
        try:
            self.assertFalse(window._project_provenance_action.isEnabled())
            state.set_project(_project())
            self.application.processEvents()
            self.assertTrue(window._project_provenance_action.isEnabled())
        finally:
            window.close()
            window.deleteLater()
