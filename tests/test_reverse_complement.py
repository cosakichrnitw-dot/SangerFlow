import copy
import unittest

from core.models import SangerRead
from core.reverse_complement import build_reverse_complement_view


def make_read(
    *,
    sequence="AACGTRYNTA",
    trim_start=2,
    trim_end=7,
    trimmed_sequence=None,
    trimmed_quality=None,
    trimmed_base_positions=None,
):
    quality = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]
    base_positions = [100 + index * 10 for index in range(len(sequence))]
    if trimmed_sequence is None:
        trimmed_sequence = sequence[trim_start:trim_end]
    if trimmed_quality is None:
        trimmed_quality = quality[trim_start:trim_end]
    if trimmed_base_positions is None:
        trace_start = base_positions[trim_start] if trim_start < len(sequence) else 0
        trimmed_base_positions = [
            position - trace_start for position in base_positions[trim_start:trim_end]
        ]
    return SangerRead(
        filename="reverse.ab1",
        sequence=sequence,
        quality=quality,
        traces={"A": [0] * 300},
        base_positions=base_positions,
        trim_start=trim_start,
        trim_end=trim_end,
        trimmed_sequence=trimmed_sequence,
        trimmed_quality=trimmed_quality,
        trimmed_base_positions=trimmed_base_positions,
    )


class ReverseComplementViewTests(unittest.TestCase):
    def test_reverse_complement_quality_and_coordinate_mappings(self):
        read = make_read()

        view = build_reverse_complement_view(read)

        self.assertEqual(view.sequence, "RYACG")
        self.assertEqual(view.quality, (16, 15, 14, 13, 12))
        self.assertEqual(view.assembly_to_trimmed_index, (4, 3, 2, 1, 0))
        self.assertEqual(view.assembly_to_raw_index, (6, 5, 4, 3, 2))
        self.assertEqual(
            view.assembly_to_raw_trace_position, (160, 150, 140, 130, 120)
        )
        self.assertEqual(
            view.assembly_to_trimmed_trace_position, (40, 30, 20, 10, 0)
        )
        self.assertEqual(view.length, 5)

    def test_first_and_last_assembly_bases_map_to_trim_boundaries(self):
        view = build_reverse_complement_view(make_read())

        self.assertEqual(view.assembly_to_trimmed_index[0], 4)
        self.assertEqual(view.assembly_to_raw_index[0], 6)
        self.assertEqual(view.assembly_to_trimmed_index[-1], 0)
        self.assertEqual(view.assembly_to_raw_index[-1], 2)

    def test_single_base_read(self):
        read = make_read(
            sequence="A",
            trim_start=0,
            trim_end=1,
            trimmed_sequence="A",
            trimmed_quality=[30],
            trimmed_base_positions=[0],
        )
        read.quality = [30]
        read.base_positions = [42]

        view = build_reverse_complement_view(read)

        self.assertEqual(view.sequence, "T")
        self.assertEqual(view.quality, (30,))
        self.assertEqual(view.assembly_to_trimmed_index, (0,))
        self.assertEqual(view.assembly_to_raw_index, (0,))
        self.assertEqual(view.assembly_to_raw_trace_position, (42,))

    def test_n_and_standard_iupac_ambiguity_codes_are_supported(self):
        sequence = "RYSWKMBDHVN"
        read = make_read(
            sequence=sequence,
            trim_start=0,
            trim_end=len(sequence),
            trimmed_sequence=sequence,
            trimmed_quality=list(range(len(sequence))),
            trimmed_base_positions=list(range(len(sequence))),
        )
        read.quality = list(range(len(sequence)))
        read.base_positions = list(range(100, 100 + len(sequence)))

        view = build_reverse_complement_view(read)

        self.assertEqual(view.sequence, "NBDHVKMWSRY")

    def test_empty_trimmed_sequence_is_rejected(self):
        read = make_read(trim_start=0, trim_end=0, trimmed_sequence="")

        with self.assertRaisesRegex(ValueError, "non-empty"):
            build_reverse_complement_view(read)

    def test_mismatched_trimmed_quality_is_rejected(self):
        read = make_read(trimmed_quality=[12, 13])

        with self.assertRaisesRegex(ValueError, "trimmed_quality"):
            build_reverse_complement_view(read)

    def test_mismatched_trimmed_base_positions_are_rejected(self):
        read = make_read(trimmed_base_positions=[0, 10])

        with self.assertRaisesRegex(ValueError, "trimmed_base_positions"):
            build_reverse_complement_view(read)

    def test_unsupported_base_is_rejected(self):
        read = make_read(trimmed_sequence="CGZRY")
        read.sequence = "AACGZRYNTA"

        with self.assertRaisesRegex(ValueError, "Unsupported"):
            build_reverse_complement_view(read)

    def test_source_read_is_not_modified(self):
        read = make_read()
        before = copy.deepcopy(read)

        build_reverse_complement_view(read)

        self.assertEqual(read, before)


if __name__ == "__main__":
    unittest.main()
