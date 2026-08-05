from unittest.mock import patch
import unittest

from core.consensus_alignment import (
    AlignedConsensusSequence,
    AlignedConsensusSet,
    build_consensus_position_mapping,
)
from core.models import SangerRead
from tools.launch_consensus_alignment_viewer import (
    _group_explicit_pairs,
    align_candidates_for_viewer,
    build_consensus_candidates_from_ab1_pairs,
    build_parser,
    show_consensus_alignment_viewer,
)


def make_read(filename, sequence):
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[40] * len(sequence),
        traces={base: list(range(40)) for base in "ACGT"},
        base_positions=[5 + (index * 5) for index in range(len(sequence))],
    )


def make_aligned_set():
    sequences = tuple(
        AlignedConsensusSequence(
            sample_id=sample_id,
            original_sequence="ACGT",
            aligned_sequence="ACGT",
            consensus_position_mapping=build_consensus_position_mapping("ACGT", "ACGT"),
        )
        for sample_id in ("IK345_COl-1", "IK346_COl-1")
    )
    return AlignedConsensusSet(
        sequences=sequences,
        alignment_length=4,
        gap_count=0,
        gap_percentage=0.0,
    )


class ConsensusAlignmentViewerLauncherTests(unittest.TestCase):
    def test_explicit_pair_grouping_never_infers_pairs_from_filenames(self):
        pairs = _group_explicit_pairs(
            ["first.ab1", "second.ab1", "third.ab1", "fourth.ab1"],
            sample_ids=["IK345", "IK346"],
        )

        self.assertEqual(
            pairs,
            [
                ("IK345", "first.ab1", "second.ab1"),
                ("IK346", "third.ab1", "fourth.ab1"),
            ],
        )

    def test_candidate_builder_uses_existing_ab1_to_v21_pipeline(self):
        reads = (
            make_read("IK345_COl-1_F.ab1", "ACGT"),
            make_read("IK345_COl-1_R.ab1", "ACGT"),
            make_read("IK346_COl-1_F.ab1", "ACGT"),
            make_read("IK346_COl-1_R.ab1", "ACGT"),
        )
        with patch(
            "tools.launch_consensus_alignment_viewer.read_ab1",
            side_effect=reads,
        ) as read_ab1:
            candidates = build_consensus_candidates_from_ab1_pairs(
                [
                    "IK345_COl-1_F.ab1",
                    "IK345_COl-1_R.ab1",
                    "IK346_COl-1_F.ab1",
                    "IK346_COl-1_R.ab1",
                ]
            )

        self.assertEqual(read_ab1.call_count, 4)
        self.assertEqual(
            [(candidate["sample_id"], candidate["sequence"]) for candidate in candidates],
            [("IK345_COl-1", "ACGT"), ("IK346_COl-1", "ACGT")],
        )
        self.assertEqual(candidates[0]["metadata"]["forward_filename"], "IK345_COl-1_F.ab1")

    def test_alignment_adapter_delegates_to_the_consensus_alignment_core(self):
        candidates = [
            {"sample_id": "IK345", "sequence": "ACGT"},
            {"sample_id": "IK346", "sequence": "ACGT"},
        ]
        aligned_set = make_aligned_set()
        with patch(
            "tools.launch_consensus_alignment_viewer.run_consensus_alignment",
            return_value=aligned_set,
        ) as run_alignment:
            result = align_candidates_for_viewer(candidates)

        self.assertIs(result, aligned_set)
        run_alignment.assert_called_once_with(candidates, alignment_id="v2.1-prototype")

    def test_parser_accepts_explicit_pairs_and_optional_sample_ids(self):
        args = build_parser().parse_args(
            ["f1.ab1", "r1.ab1", "f2.ab1", "r2.ab1", "--sample-id", "IK345", "--sample-id", "IK346"]
        )

        self.assertEqual(args.ab1_files, ["f1.ab1", "r1.ab1", "f2.ab1", "r2.ab1"])
        self.assertEqual(args.sample_ids, ["IK345", "IK346"])

    def test_show_window_adapts_core_alignment_result_without_running_mafft(self):
        calls = []

        class FakeRoot:
            def withdraw(self):
                calls.append("withdraw")

            def destroy(self):
                calls.append("destroy")

            def mainloop(self):
                calls.append("mainloop")

        class FakeWindow:
            def __init__(self, root, view_model):
                calls.append(("window", root, view_model.alignment_length))

            def protocol(self, name, callback):
                calls.append(("protocol", name))

        root = FakeRoot()
        show_consensus_alignment_viewer(
            make_aligned_set(),
            root_factory=lambda: root,
            window_factory=FakeWindow,
        )

        self.assertEqual(
            calls,
            ["withdraw", ("window", root, 4), ("protocol", "WM_DELETE_WINDOW"), "mainloop"],
        )


if __name__ == "__main__":
    unittest.main()
