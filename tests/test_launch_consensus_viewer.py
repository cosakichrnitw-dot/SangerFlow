from unittest.mock import patch
import unittest

from core.models import SangerRead
from tools.launch_consensus_viewer import (
    build_parser,
    build_view_model_from_ab1_pair,
    show_single_consensus_viewer,
)


def make_read(filename, sequence):
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[40] * len(sequence),
        traces={base: list(range(40)) for base in "ACGT"},
        base_positions=[5 + (index * 5) for index in range(len(sequence))],
    )


class FakeRoot:
    def __init__(self):
        self.withdrawn = False
        self.mainloop_called = False
        self.destroyed = False

    def withdraw(self):
        self.withdrawn = True

    def mainloop(self):
        self.mainloop_called = True

    def destroy(self):
        self.destroyed = True


class FakeWindow:
    def __init__(self, master, view_model):
        self.master = master
        self.view_model = view_model
        self.protocol_name = None
        self.protocol_callback = None

    def protocol(self, name, callback):
        self.protocol_name = name
        self.protocol_callback = callback


class ConsensusViewerLauncherTests(unittest.TestCase):
    def test_build_view_model_runs_the_existing_ab1_to_v21_pipeline(self):
        forward = make_read("forward.ab1", "ACGT")
        # The reverse complement of ACGT is ACGT, providing a full overlap.
        reverse = make_read("reverse.ab1", "ACGT")

        with patch(
            "tools.launch_consensus_viewer.read_ab1",
            side_effect=(forward, reverse),
        ) as read_ab1:
            model = build_view_model_from_ab1_pair(
                "forward.ab1",
                "reverse.ab1",
                sample_identifier="pair-1",
            )

        self.assertEqual(read_ab1.call_count, 2)
        self.assertEqual(model.sample_identifier, "pair-1")
        self.assertEqual(model.consensus_sequence, "ACGT")
        self.assertEqual(len(model.columns), 4)
        self.assertEqual(
            model.column_at(0).review_evidence.forward_raw_trace_position, 5
        )
        self.assertEqual(
            model.column_at(0).review_evidence.reverse_raw_trace_position, 20
        )

    def test_show_window_uses_a_standalone_hidden_root(self):
        root = FakeRoot()
        model = type("ViewModel", (), {})()

        show_single_consensus_viewer(
            model,
            root_factory=lambda: root,
            window_factory=FakeWindow,
        )

        self.assertTrue(root.withdrawn)
        self.assertTrue(root.mainloop_called)

    def test_parser_accepts_the_two_ab1_paths(self):
        args = build_parser().parse_args(
            [
                "forward.ab1",
                "reverse.ab1",
                "--sample-id",
                "sample-1",
                "--with-main-viewer",
            ]
        )

        self.assertEqual(args.forward_ab1, "forward.ab1")
        self.assertEqual(args.reverse_ab1, "reverse.ab1")
        self.assertEqual(args.sample_id, "sample-1")
        self.assertTrue(args.with_main_viewer)


if __name__ == "__main__":
    unittest.main()
