from dataclasses import FrozenInstanceError
import unittest

from core.assembly_models import (
    AlignmentColumn,
    AssemblyReadView,
    PairAlignment,
    ReadCoordinate,
    ReadOrientation,
)
from core.assembly_view_builders import (
    build_forward_assembly_view,
    build_reverse_assembly_view,
)
from core.models import SangerRead


def make_view(orientation, *, source_filename, sequence, raw_start, reverse=False):
    length = len(sequence)
    order = range(length - 1, -1, -1) if reverse else range(length)
    return AssemblyReadView(
        source_filename=source_filename,
        orientation=orientation,
        sequence=sequence,
        quality=[30 + index for index in order],
        assembly_to_trimmed_index=list(order),
        assembly_to_raw_index=[raw_start + index for index in order],
        assembly_to_raw_trace_position=[1000 + raw_start + index for index in order],
        assembly_to_trimmed_trace_position=[10 * index for index in order],
    )


def make_trimmed_read():
    sequence = "AACGTRYNTA"
    quality = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    base_positions = [100 + index * 10 for index in range(len(sequence))]
    return SangerRead(
        filename="sample.ab1",
        sequence=sequence,
        quality=quality,
        traces={"A": [0] * 300},
        base_positions=base_positions,
        trim_start=2,
        trim_end=7,
        trimmed_sequence="CGTRY",
        trimmed_quality=[12, 13, 14, 15, 16],
        trimmed_base_positions=[0, 10, 20, 30, 40],
    )


class AssemblyReadViewTests(unittest.TestCase):
    def test_view_freezes_coordinate_mappings_and_returns_coordinates(self):
        view = make_view(
            ReadOrientation.REVERSE,
            source_filename="sample_R.ab1",
            sequence="GCAT",
            raw_start=20,
            reverse=True,
        )

        self.assertEqual(view.quality, (33, 32, 31, 30))
        self.assertEqual(view.assembly_to_trimmed_index, (3, 2, 1, 0))
        self.assertEqual(view.assembly_to_raw_index, (23, 22, 21, 20))
        self.assertEqual(view.assembly_to_raw_trace_position, (1023, 1022, 1021, 1020))
        self.assertEqual(view.coordinate_at(0), ReadCoordinate(0, 3, 23, 1023, 30))
        with self.assertRaises(FrozenInstanceError):
            view.sequence = "AAAA"

    def test_view_rejects_mapping_length_mismatch(self):
        with self.assertRaisesRegex(ValueError, "assembly_to_raw_index"):
            AssemblyReadView(
                source_filename="sample_F.ab1",
                orientation=ReadOrientation.FORWARD,
                sequence="AC",
                quality=[30, 31],
                assembly_to_trimmed_index=[0, 1],
                assembly_to_raw_index=[10],
                assembly_to_raw_trace_position=[100, 101],
                assembly_to_trimmed_trace_position=[0, 10],
            )

    def test_view_rejects_negative_quality(self):
        with self.assertRaisesRegex(ValueError, "greater than or equal to zero"):
            AssemblyReadView(
                source_filename="sample_F.ab1",
                orientation=ReadOrientation.FORWARD,
                sequence="AC",
                quality=[30, -1],
                assembly_to_trimmed_index=[0, 1],
                assembly_to_raw_index=[10, 11],
                assembly_to_raw_trace_position=[100, 101],
                assembly_to_trimmed_trace_position=[0, 10],
            )


class AssemblyViewBuilderTests(unittest.TestCase):
    def test_builds_forward_view_with_natural_coordinate_order(self):
        view = build_forward_assembly_view(make_trimmed_read())

        self.assertEqual(view.orientation, ReadOrientation.FORWARD)
        self.assertEqual(view.sequence, "CGTRY")
        self.assertEqual(view.quality, (12, 13, 14, 15, 16))
        self.assertEqual(view.assembly_to_trimmed_index, (0, 1, 2, 3, 4))
        self.assertEqual(view.assembly_to_raw_index, (2, 3, 4, 5, 6))
        self.assertEqual(view.assembly_to_raw_trace_position, (120, 130, 140, 150, 160))
        self.assertEqual(view.assembly_to_trimmed_trace_position, (0, 10, 20, 30, 40))

    def test_builds_reverse_view_from_existing_reverse_complement_view(self):
        view = build_reverse_assembly_view(make_trimmed_read())

        self.assertEqual(view.orientation, ReadOrientation.REVERSE)
        self.assertEqual(view.sequence, "RYACG")
        self.assertEqual(view.quality, (16, 15, 14, 13, 12))
        self.assertEqual(view.assembly_to_trimmed_index, (4, 3, 2, 1, 0))
        self.assertEqual(view.assembly_to_raw_index, (6, 5, 4, 3, 2))
        self.assertEqual(view.assembly_to_raw_trace_position, (160, 150, 140, 130, 120))
        self.assertEqual(view.assembly_to_trimmed_trace_position, (40, 30, 20, 10, 0))


class AlignmentColumnTests(unittest.TestCase):
    def test_column_exposes_indexes_and_gap_information(self):
        forward = ReadCoordinate(2, 2, 12, 112, 20)
        column = AlignmentColumn(4, forward=forward, reverse=None)

        self.assertEqual(column.forward_index, 2)
        self.assertIsNone(column.reverse_index)
        self.assertFalse(column.forward_is_gap)
        self.assertTrue(column.reverse_is_gap)

    def test_gap_gap_column_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "gap-gap"):
            AlignmentColumn(0, forward=None, reverse=None)


class PairAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.forward_view = make_view(
            ReadOrientation.FORWARD,
            source_filename="sample_F.ab1",
            sequence="ACGT",
            raw_start=10,
        )
        self.reverse_view = make_view(
            ReadOrientation.REVERSE,
            source_filename="sample_R.ab1",
            sequence="ACGT",
            raw_start=20,
            reverse=True,
        )

    def test_pair_alignment_preserves_provenance_ready_coordinates(self):
        alignment = PairAlignment(
            forward_view=self.forward_view,
            reverse_view=self.reverse_view,
            columns=[
                AlignmentColumn(
                    0,
                    self.forward_view.coordinate_at(0),
                    self.reverse_view.coordinate_at(0),
                ),
                AlignmentColumn(
                    1,
                    self.forward_view.coordinate_at(1),
                    self.reverse_view.coordinate_at(1),
                ),
                AlignmentColumn(2, self.forward_view.coordinate_at(2), None),
                AlignmentColumn(
                    3,
                    self.forward_view.coordinate_at(3),
                    self.reverse_view.coordinate_at(2),
                ),
                AlignmentColumn(4, None, self.reverse_view.coordinate_at(3)),
            ],
        )

        self.assertEqual(alignment.length, 5)
        self.assertEqual(alignment.column_at(0).reverse.raw_index, 23)
        self.assertEqual(alignment.column_at(0).reverse.raw_trace_position, 1023)
        self.assertEqual(alignment.column_at(2).forward.trimmed_index, 2)
        self.assertTrue(alignment.column_at(2).reverse_is_gap)
        self.assertEqual(alignment.column_at(4).reverse.trimmed_index, 0)

    def test_pair_alignment_rejects_coordinate_not_from_its_view(self):
        incorrect_forward = ReadCoordinate(0, 0, 999, 999, 0)

        with self.assertRaisesRegex(ValueError, "does not match"):
            PairAlignment(
                self.forward_view,
                self.reverse_view,
                [AlignmentColumn(0, incorrect_forward, self.reverse_view.coordinate_at(0))],
            )

    def test_pair_alignment_rejects_non_contiguous_column_indexes(self):
        with self.assertRaisesRegex(ValueError, "contiguous"):
            PairAlignment(
                self.forward_view,
                self.reverse_view,
                [AlignmentColumn(1, self.forward_view.coordinate_at(0), None)],
            )

    def test_pair_alignment_rejects_out_of_order_side_indexes(self):
        with self.assertRaisesRegex(ValueError, "complete AssemblyReadView"):
            PairAlignment(
                self.forward_view,
                self.reverse_view,
                [
                    AlignmentColumn(
                        0,
                        self.forward_view.coordinate_at(0),
                        self.reverse_view.coordinate_at(0),
                    ),
                    AlignmentColumn(
                        1,
                        self.forward_view.coordinate_at(2),
                        self.reverse_view.coordinate_at(1),
                    ),
                    AlignmentColumn(
                        2,
                        self.forward_view.coordinate_at(1),
                        self.reverse_view.coordinate_at(2),
                    ),
                    AlignmentColumn(
                        3,
                        self.forward_view.coordinate_at(3),
                        self.reverse_view.coordinate_at(3),
                    ),
                ],
            )

    def test_pair_alignment_rejects_incomplete_view_coverage(self):
        with self.assertRaisesRegex(ValueError, "complete AssemblyReadView"):
            PairAlignment(
                self.forward_view,
                self.reverse_view,
                [
                    AlignmentColumn(
                        0,
                        self.forward_view.coordinate_at(1),
                        self.reverse_view.coordinate_at(0),
                    ),
                ],
            )

    def test_pair_alignment_rejects_no_overlap_columns(self):
        with self.assertRaisesRegex(ValueError, "overlap column"):
            PairAlignment(
                self.forward_view,
                self.reverse_view,
                [
                    AlignmentColumn(0, self.forward_view.coordinate_at(0), None),
                    AlignmentColumn(1, self.forward_view.coordinate_at(1), None),
                    AlignmentColumn(2, self.forward_view.coordinate_at(2), None),
                    AlignmentColumn(3, self.forward_view.coordinate_at(3), None),
                    AlignmentColumn(4, None, self.reverse_view.coordinate_at(0)),
                    AlignmentColumn(5, None, self.reverse_view.coordinate_at(1)),
                    AlignmentColumn(6, None, self.reverse_view.coordinate_at(2)),
                    AlignmentColumn(7, None, self.reverse_view.coordinate_at(3)),
                ],
            )


if __name__ == "__main__":
    unittest.main()
