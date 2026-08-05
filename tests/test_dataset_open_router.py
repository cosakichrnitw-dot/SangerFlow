"""Tests for the callback-only sequence dataset open router."""

from __future__ import annotations

import unittest

from core.dataset_open_router import (
    DatasetOpenRouteError,
    DatasetOpenRouter,
)
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


def make_dataset(
    dataset_id: str,
    source_type: SourceType,
    sequences: tuple[tuple[str, str], ...] = (("record", "ATGC"),),
    *,
    metadata: dict[str, object] | None = None,
) -> SequenceDataset:
    return SequenceDataset(
        dataset_id=dataset_id,
        name=dataset_id,
        source_type=source_type,
        records=tuple(SequenceRecord(identifier, sequence) for identifier, sequence in sequences),
        metadata=metadata,
    )


class DatasetOpenRouterTests(unittest.TestCase):
    def test_routes_by_source_type_to_registered_callback(self) -> None:
        imported = make_dataset("imported", SourceType.IMPORTED_FASTA)
        reviewed = make_dataset("reviewed", SourceType.REVIEWED_CONSENSUS)
        received: list[tuple[str, SourceType]] = []
        router = DatasetOpenRouter(
            {
                SourceType.IMPORTED_FASTA: lambda context: received.append(
                    (context.dataset.dataset_id, context.source_type)
                ),
                SourceType.REVIEWED_CONSENSUS: lambda context: received.append(
                    (context.dataset.dataset_id, context.source_type)
                ),
            }
        )

        router.open(imported)
        router.open(reviewed)

        self.assertEqual(
            received,
            [
                ("imported", SourceType.IMPORTED_FASTA),
                ("reviewed", SourceType.REVIEWED_CONSENSUS),
            ],
        )

    def test_source_type_has_priority_over_gap_and_alignment_metadata(self) -> None:
        imported_with_alignment_hints = make_dataset(
            "gap-containing-import",
            SourceType.IMPORTED_FASTA,
            (("one", "ATG-C"), ("two", "ATGTC")),
            metadata={"inferred_alignment": True},
        )
        received: list[SourceType] = []
        router = DatasetOpenRouter(
            {
                SourceType.IMPORTED_FASTA: lambda context: received.append(context.source_type),
                SourceType.IMPORTED_ALIGNMENT: lambda context: received.append(context.source_type),
            }
        )

        router.open(imported_with_alignment_hints)

        self.assertEqual(received, [SourceType.IMPORTED_FASTA])

    def test_context_exposes_supplementary_structure_and_metadata_hints(self) -> None:
        alignment = make_dataset(
            "alignment",
            SourceType.IMPORTED_ALIGNMENT,
            (("one", "ATG-C"), ("two", "ATGTC")),
            metadata={"inferred_alignment": True},
        )
        received = []
        router = DatasetOpenRouter({SourceType.IMPORTED_ALIGNMENT: received.append})

        router.open(alignment)

        context = received[0]
        self.assertIs(context.dataset, alignment)
        self.assertTrue(context.has_gaps)
        self.assertTrue(context.is_equal_length)
        self.assertTrue(context.inferred_alignment)

    def test_missing_callback_is_an_explicit_error_or_uses_explicit_fallback(self) -> None:
        dataset = make_dataset("raw", SourceType.AB1_RAW)
        router = DatasetOpenRouter()
        with self.assertRaisesRegex(DatasetOpenRouteError, "no open callback"):
            router.open(dataset)

        received = []
        fallback_router = DatasetOpenRouter(fallback_callback=received.append)
        fallback_router.open(dataset)
        self.assertEqual(received[0].source_type, SourceType.AB1_RAW)

    def test_registration_replacement_removal_and_input_validation(self) -> None:
        router = DatasetOpenRouter()
        first = []
        second = []
        router.register(SourceType.AB1_TRIMMED, first.append)
        router.register(SourceType.AB1_TRIMMED, second.append)
        self.assertTrue(router.has_callback(SourceType.AB1_TRIMMED))
        router.open(make_dataset("trimmed", SourceType.AB1_TRIMMED))
        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        router.unregister(SourceType.AB1_TRIMMED)
        self.assertFalse(router.has_callback(SourceType.AB1_TRIMMED))
        with self.assertRaises(ValueError):
            router.register("AB1_RAW", lambda _context: None)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            router.register(SourceType.AB1_RAW, "not callable")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
