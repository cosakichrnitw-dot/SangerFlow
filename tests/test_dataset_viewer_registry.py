"""Tests for callback-only dataset viewer registry behavior."""

from __future__ import annotations

import unittest

from core.dataset_open_router import DatasetOpenRouteError, DatasetOpenRouter
from core.dataset_viewer_registry import (
    DatasetViewerRegistry,
    register_alignment_dataset_viewer,
    register_default_dataset_viewers,
)
from core.project import Project
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.alignment_viewer_adapter import AlignmentViewerInput


def make_dataset() -> SequenceDataset:
    return SequenceDataset.from_sequence_pairs(
        "alignment", "Alignment", SourceType.IMPORTED_ALIGNMENT, [("one", "ATG-C"), ("two", "ATGTC")]
    )


class DatasetViewerRegistryTests(unittest.TestCase):
    def test_register_get_and_has_callback(self) -> None:
        registry = DatasetViewerRegistry()
        received = []
        callback = received.append

        registry.register(SourceType.IMPORTED_ALIGNMENT, callback)

        self.assertTrue(registry.has_callback(SourceType.IMPORTED_ALIGNMENT))
        self.assertIs(registry.get_callback(SourceType.IMPORTED_ALIGNMENT), callback)

    def test_duplicate_registration_is_rejected_and_unregister_removes_callback(self) -> None:
        registry = DatasetViewerRegistry()
        callback = lambda _context: None
        registry.register(SourceType.IMPORTED_FASTA, callback)
        with self.assertRaisesRegex(ValueError, "already registered"):
            registry.register(SourceType.IMPORTED_FASTA, callback)

        registry.unregister(SourceType.IMPORTED_FASTA)
        self.assertFalse(registry.has_callback(SourceType.IMPORTED_FASTA))
        with self.assertRaisesRegex(KeyError, "no callback"):
            registry.get_callback(SourceType.IMPORTED_FASTA)
        registry.unregister(SourceType.IMPORTED_FASTA)

    def test_multiple_source_types_are_copied_to_router_and_route_datasets(self) -> None:
        registry = DatasetViewerRegistry()
        received = []
        registry.register(SourceType.IMPORTED_FASTA, lambda context: received.append(context.source_type))
        registry.register(SourceType.IMPORTED_ALIGNMENT, lambda context: received.append(context.source_type))
        router = DatasetOpenRouter()

        registry.register_router(router)
        router.open(
            SequenceDataset.from_sequence_pairs(
                "fasta", "FASTA", SourceType.IMPORTED_FASTA, [("one", "ATGC")]
            )
        )
        router.open(make_dataset())

        self.assertEqual(received, [SourceType.IMPORTED_FASTA, SourceType.IMPORTED_ALIGNMENT])

    def test_registry_does_not_change_project_or_dataset(self) -> None:
        dataset = make_dataset()
        project = Project.create("project", "Project").add_dataset(dataset)
        registry = DatasetViewerRegistry()
        registry.register(SourceType.IMPORTED_ALIGNMENT, lambda _context: None)
        router = DatasetOpenRouter()
        registry.register_router(router)

        router.open(dataset)

        self.assertEqual(project.dataset_ids, ("alignment",))
        self.assertIs(project.get_dataset("alignment"), dataset)
        self.assertEqual(dataset.records[0].sequence, "ATG-C")

    def test_alignment_dataset_callback_registration_routes_dataset_not_context(self) -> None:
        dataset = make_dataset()
        registry = DatasetViewerRegistry()
        received: list[SequenceDataset] = []
        register_alignment_dataset_viewer(registry, received.append)
        router = DatasetOpenRouter()

        registry.register_router(router)
        router.open(dataset)

        self.assertEqual(received, [dataset])
        self.assertEqual(dataset.records[0].sequence, "ATG-C")

    def test_default_alignment_registration_coexists_with_other_source_callbacks(self) -> None:
        alignment = make_dataset()
        fasta = SequenceDataset.from_sequence_pairs(
            "fasta", "FASTA", SourceType.IMPORTED_FASTA, [("one", "ATGC")]
        )
        registry = DatasetViewerRegistry()
        received: list[object] = []
        registry.register(SourceType.IMPORTED_FASTA, lambda context: received.append(context.source_type))
        register_default_dataset_viewers(registry, alignment_callback=received.append)
        router = DatasetOpenRouter()
        registry.register_router(router)

        router.open(fasta)
        router.open(alignment)

        self.assertEqual(received[0], SourceType.IMPORTED_FASTA)
        self.assertIsInstance(received[1], AlignmentViewerInput)
        self.assertEqual(
            [record.id for record in received[1]],
            ["one", "two"],
        )
        self.assertEqual(
            [str(record.seq) for record in received[1]],
            ["ATG-C", "ATGTC"],
        )
        self.assertEqual(alignment.records[0].sequence, "ATG-C")

    def test_default_alignment_registration_passes_viewer_input_not_dataset(self) -> None:
        alignment = make_dataset()
        registry = DatasetViewerRegistry()
        received = []
        register_default_dataset_viewers(registry, alignment_callback=received.append)
        router = DatasetOpenRouter()
        registry.register_router(router)

        router.open(alignment)

        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], AlignmentViewerInput)
        self.assertNotIsInstance(received[0], SequenceDataset)
        self.assertEqual(received[0].alignment_length, 5)

    def test_unregistered_source_type_remains_a_safe_router_error(self) -> None:
        registry = DatasetViewerRegistry()
        register_alignment_dataset_viewer(registry, lambda _dataset: None)
        router = DatasetOpenRouter()
        registry.register_router(router)
        fasta = SequenceDataset.from_sequence_pairs(
            "fasta", "FASTA", SourceType.IMPORTED_FASTA, [("one", "ATGC")]
        )

        with self.assertRaisesRegex(DatasetOpenRouteError, "no open callback"):
            router.open(fasta)


if __name__ == "__main__":
    unittest.main()
