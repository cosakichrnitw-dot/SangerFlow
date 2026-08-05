"""Tests for the Project Dataset Manager's GUI-independent behavior."""

from __future__ import annotations

import unittest

from core.project import DerivationType, Project
from core.sequence_dataset import SequenceDataset, SourceType
from core.dataset_open_router import DatasetOpenRouter, DatasetOpenRouteError
from workflow.mafft_workflow import align_sequence_dataset
from workflow.project_alignment import add_alignment_to_project
from workflow.project_blast import add_blast_result_to_project
from core.blast_result import BlastHit, BlastResultDataset
from types import SimpleNamespace
from unittest.mock import patch
from gui.project_dataset_manager import (
    DatasetSelectionError,
    ProjectDatasetManagerState,
)


def make_dataset(
    dataset_id: str,
    *,
    source_type: SourceType = SourceType.IMPORTED_FASTA,
    sequences: tuple[tuple[str, str], ...] = (("record", "ATGC"),),
) -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(dataset_id, f"{dataset_id} dataset", source_type, sequences)


def make_project() -> tuple[Project, SequenceDataset, SequenceDataset, SequenceDataset]:
    imported = make_dataset("imported")
    aligned = make_dataset(
        "aligned",
        source_type=SourceType.IMPORTED_ALIGNMENT,
        sequences=(("a", "ATG-C"), ("b", "ATGTC")),
    )
    reviewed = make_dataset("reviewed")
    project = (
        Project.create("wedgefish", "Central Java Wedgefish")
        .add_dataset(imported, derivation_type=DerivationType.IMPORTED)
        .add_dataset(
            aligned,
            parent_dataset_id="imported",
            derivation_type=DerivationType.ALIGNED_WITH_MAFFT,
        )
        .add_dataset(
            reviewed,
            parent_dataset_id="aligned",
            derivation_type=DerivationType.REVIEWED_FROM_CONSENSUS,
        )
    )
    return project, imported, aligned, reviewed


class ProjectDatasetManagerStateTests(unittest.TestCase):
    def test_empty_project_has_no_rows(self) -> None:
        state = ProjectDatasetManagerState(Project.create("empty", "Empty"))

        self.assertEqual(state.table_rows(), ())
        self.assertEqual(state.selected_datasets(), ())

    def test_one_dataset_row_uses_default_parent_and_derivation_display(self) -> None:
        dataset = make_dataset("single")
        project = Project.create("project", "Project").add_dataset(dataset)
        row = ProjectDatasetManagerState(project).table_rows()[0]

        self.assertEqual(row.dataset_name, "single dataset")
        self.assertEqual(row.source_type, SourceType.IMPORTED_FASTA.value)
        self.assertEqual(row.sequence_count, 1)
        self.assertEqual(row.length_range, "4–4")
        self.assertEqual(row.has_gaps, "No")
        self.assertEqual(row.parent_dataset_id, "-")
        self.assertEqual(row.derivation_type, "-")

    def test_rows_preserve_project_order_and_show_dataset_information(self) -> None:
        project, _, aligned, _ = make_project()
        rows = ProjectDatasetManagerState(project).table_rows()

        self.assertEqual([row.dataset_id for row in rows], ["imported", "aligned", "reviewed"])
        self.assertEqual(rows[1].source_type, SourceType.IMPORTED_ALIGNMENT.value)
        self.assertEqual(rows[1].sequence_count, 2)
        self.assertEqual(rows[1].length_range, "5–5")
        self.assertEqual(rows[1].has_gaps, "Yes")
        self.assertEqual(rows[1].parent_dataset_id, "imported")
        self.assertEqual(rows[1].derivation_type, DerivationType.ALIGNED_WITH_MAFFT.value)
        self.assertIs(project.get_dataset("aligned"), aligned)

    def test_analysis_result_rows_show_name_type_and_parent_dataset(self) -> None:
        dataset = make_dataset("input", sequences=(("IK345", "ATGC"),))
        blast_result = BlastResultDataset(
            "input-blast", "Input BLAST",
            (BlastHit("IK345", "AB123", "Species one", "Species one", 99.0, 98.0, 1e-20, 658, "nt"),),
            "input",
        )
        project = add_blast_result_to_project(
            Project.create("project", "Project").add_dataset(dataset), blast_result
        )

        rows = ProjectDatasetManagerState(project).analysis_result_rows()

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].display_name, "Input BLAST")
        self.assertEqual(rows[0].result_type, "BLAST")
        self.assertEqual(rows[0].parent_dataset_id, "input")

    def test_select_all_deselect_all_and_selection_order(self) -> None:
        project, imported, aligned, reviewed = make_project()
        state = ProjectDatasetManagerState(project)
        state.set_selected("reviewed", True)
        state.set_selected("imported", True)

        self.assertEqual(state.selected_datasets(), (imported, reviewed))
        state.select_all()
        self.assertEqual(state.selected_datasets(), (imported, aligned, reviewed))
        state.deselect_all()
        self.assertEqual(state.selected_datasets(), ())

    def test_open_callbacks_support_single_and_multiple_selected_datasets(self) -> None:
        project, imported, aligned, _ = make_project()
        state = ProjectDatasetManagerState(project)
        received_one: list[SequenceDataset] = []
        received_many: list[tuple[SequenceDataset, ...]] = []

        state.set_selected("imported", True)
        self.assertEqual(state.open_selected(on_open_dataset=received_one.append), (imported,))
        state.set_selected("aligned", True)
        state.open_selected(on_open_datasets=received_many.append)

        self.assertEqual(received_one, [imported])
        self.assertEqual(received_many, [(imported, aligned)])

    def test_open_prefers_single_callback_for_one_dataset_and_multiple_callback_for_many(self) -> None:
        project, imported, aligned, _ = make_project()
        state = ProjectDatasetManagerState(project)
        received_one: list[SequenceDataset] = []
        received_many: list[tuple[SequenceDataset, ...]] = []

        state.set_selected("imported", True)
        state.open_selected(
            on_open_dataset=received_one.append,
            on_open_datasets=received_many.append,
        )
        state.set_selected("aligned", True)
        state.open_selected(
            on_open_dataset=received_one.append,
            on_open_datasets=received_many.append,
        )

        self.assertEqual(received_one, [imported])
        self.assertEqual(received_many, [(imported, aligned)])

    def test_open_without_callback_or_selection_is_safe(self) -> None:
        project, _, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        with self.assertRaisesRegex(DatasetSelectionError, "select at least"):
            state.open_selected()
        state.set_selected("imported", True)
        with self.assertRaisesRegex(DatasetSelectionError, "no dataset-open callback"):
            state.open_selected()

    def test_open_selected_routes_each_dataset_by_source_type(self) -> None:
        project, imported, aligned, _ = make_project()
        state = ProjectDatasetManagerState(project)
        received: list[tuple[str, SourceType]] = []
        router = DatasetOpenRouter(
            {
                SourceType.IMPORTED_FASTA: lambda context: received.append(
                    (context.dataset.dataset_id, context.source_type)
                ),
                SourceType.IMPORTED_ALIGNMENT: lambda context: received.append(
                    (context.dataset.dataset_id, context.source_type)
                ),
            }
        )
        state.set_selected("aligned", True)
        state.set_selected("imported", True)

        selected = state.open_selected(dataset_open_router=router)

        self.assertEqual(selected, (imported, aligned))
        self.assertEqual(
            received,
            [
                ("imported", SourceType.IMPORTED_FASTA),
                ("aligned", SourceType.IMPORTED_ALIGNMENT),
            ],
        )
        self.assertEqual(project.dataset_ids, ("imported", "aligned", "reviewed"))
        self.assertIs(project.get_dataset("imported"), imported)

    def test_router_without_registered_callback_is_a_safe_open_error(self) -> None:
        project, imported, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        state.set_selected("imported", True)

        with self.assertRaisesRegex(DatasetOpenRouteError, "no open callback"):
            state.open_selected(dataset_open_router=DatasetOpenRouter())
        self.assertEqual(project.dataset_ids, ("imported", "aligned", "reviewed"))
        self.assertIs(project.get_dataset("imported"), imported)

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_align_selected_uses_callback_to_add_alignment_and_update_project(self, _which) -> None:
        input_dataset = make_dataset(
            "input",
            sequences=(("IK345", "ATGCAA"), ("IK346", "ATGTCAA")),
        )
        project = Project.create("project", "Project").add_dataset(input_dataset)
        state = ProjectDatasetManagerState(project)
        changed: list[Project] = []
        state.set_selected("input", True)

        def align_callback(dataset, current_project):
            alignment = align_sequence_dataset(
                dataset,
                runner=lambda _command, **_kwargs: SimpleNamespace(
                    returncode=0,
                    stdout=">IK345\nATG-CAA\n>IK346\nATGTCAA\n",
                    stderr="",
                ),
            )
            return add_alignment_to_project(current_project, alignment)

        updated = state.align_selected(align_callback, on_project_changed=changed.append)

        self.assertEqual(project.dataset_ids, ("input",))
        self.assertEqual(updated.dataset_ids, ("input", "input_mafft"))
        self.assertEqual(
            updated.get_entry("input_mafft").derivation_type,
            DerivationType.ALIGNED_WITH_MAFFT,
        )
        self.assertEqual(changed, [updated])
        self.assertEqual(input_dataset.records[0].sequence, "ATGCAA")

    def test_align_selected_rejects_existing_alignment_and_gap_input_without_changing_project(self) -> None:
        project, _, aligned, _ = make_project()
        state = ProjectDatasetManagerState(project)
        called = []
        state.set_selected("aligned", True)

        with self.assertRaisesRegex(DatasetSelectionError, "existing alignment"):
            state.align_selected(lambda *_args: called.append("called"))
        self.assertEqual(called, [])
        self.assertEqual(state.project, project)

        gapped = make_dataset("gapped", sequences=(("one", "ATG-C"), ("two", "ATGTC")))
        gapped_project = Project.create("gapped-project", "Gapped").add_dataset(gapped)
        gapped_state = ProjectDatasetManagerState(gapped_project)
        gapped_state.set_selected("gapped", True)
        with self.assertRaisesRegex(DatasetSelectionError, "gap-free"):
            gapped_state.align_selected(lambda *_args: called.append("called"))
        self.assertEqual(gapped_state.project, gapped_project)

    def test_alignment_callback_failure_leaves_project_unchanged(self) -> None:
        project, _, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        state.set_selected("imported", True)

        with self.assertRaisesRegex(RuntimeError, "MAFFT failed"):
            state.align_selected(lambda *_args: (_ for _ in ()).throw(RuntimeError("MAFFT failed")))
        self.assertEqual(state.project, project)

    def test_run_blast_selected_delegates_one_dataset_and_publishes_updated_project(self) -> None:
        input_dataset = make_dataset("input", sequences=(("IK345", "ATGC"),))
        project = Project.create("project", "Project").add_dataset(input_dataset)
        state = ProjectDatasetManagerState(project)
        changed: list[Project] = []
        received: list[tuple[SequenceDataset, Project]] = []
        state.set_selected("input", True)

        def blast_callback(dataset: SequenceDataset, current_project: Project) -> Project:
            received.append((dataset, current_project))
            result = BlastResultDataset(
                "input-blast", "Input BLAST",
                (BlastHit("IK345", "AB123", "Species one", "Species one", 99.0, 98.0, 1e-20, 658, "nt"),),
                dataset.dataset_id,
            )
            return add_blast_result_to_project(current_project, result)

        updated = state.run_blast_selected(blast_callback, on_project_changed=changed.append)

        self.assertEqual(received, [(input_dataset, project)])
        self.assertEqual(project.analysis_result_ids, ())
        self.assertEqual(updated.analysis_result_ids, ("input-blast",))
        self.assertEqual(changed, [updated])

    def test_run_blast_selected_requires_exactly_one_dataset_and_leaves_project_unchanged_on_failure(self) -> None:
        project, _, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        with self.assertRaisesRegex(DatasetSelectionError, "exactly one"):
            state.run_blast_selected(lambda _dataset, current_project: current_project)
        state.set_selected("imported", True)
        state.set_selected("aligned", True)
        with self.assertRaisesRegex(DatasetSelectionError, "exactly one"):
            state.run_blast_selected(lambda _dataset, current_project: current_project)
        state.deselect_all()
        state.set_selected("imported", True)
        with self.assertRaisesRegex(DatasetSelectionError, "must return a Project"):
            state.run_blast_selected(lambda *_args: object())  # type: ignore[arg-type]
        self.assertEqual(state.project, project)

    def test_remove_updates_manager_project_but_not_original_project_or_dataset(self) -> None:
        project, imported, aligned, reviewed = make_project()
        state = ProjectDatasetManagerState(project)
        state.set_selected("reviewed", True)
        updated = state.remove_selected()

        self.assertEqual(project.dataset_ids, ("imported", "aligned", "reviewed"))
        self.assertEqual(updated.dataset_ids, ("imported", "aligned"))
        self.assertEqual([row.dataset_id for row in state.table_rows()], ["imported", "aligned"])
        self.assertEqual(reviewed.records[0].sequence, "ATGC")
        self.assertIs(updated.get_dataset("imported"), imported)
        self.assertIs(updated.get_dataset("aligned"), aligned)

    def test_remove_notifies_project_changed_callback(self) -> None:
        project, _, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        received_projects: list[Project] = []
        state.set_selected("reviewed", True)

        updated = state.remove_selected(on_project_changed=received_projects.append)

        self.assertEqual(received_projects, [updated])

    def test_remove_rejects_a_parent_that_has_an_unselected_child(self) -> None:
        project, _, _, _ = make_project()
        state = ProjectDatasetManagerState(project)
        state.set_selected("imported", True)

        with self.assertRaisesRegex(ValueError, "children exist"):
            state.remove_selected()
        self.assertEqual(state.project, project)

    def test_remove_selected_child_and_parent_is_processed_safely(self) -> None:
        imported = make_dataset("imported")
        child = make_dataset("child")
        project = Project.create("project", "Project").add_dataset(imported).add_dataset(
            child, parent_dataset_id="imported", derivation_type=DerivationType.SUBSET_FROM_DATASET
        )
        state = ProjectDatasetManagerState(project)
        state.set_selected("imported", True)
        state.set_selected("child", True)

        self.assertEqual(state.remove_selected().dataset_ids, ())


if __name__ == "__main__":
    unittest.main()
