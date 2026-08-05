import tempfile
import unittest
from pathlib import Path

from tools.launch_multiple_consensus_viewer import (
    _right_pad_for_display_preview,
    build_parser,
    build_view_model_from_fasta,
    load_aligned_consensus_fasta,
    show_multiple_consensus_viewer,
)


class MultipleConsensusViewerLauncherTests(unittest.TestCase):
    def test_loads_multiple_aligned_fasta_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "consensus.fasta"
            path.write_text(">IK345\nATG-C\n>IK346\nATGTC\n", encoding="utf-8")

            records = load_aligned_consensus_fasta((path,))
            view_model = build_view_model_from_fasta((path,))

        self.assertEqual(
            records,
            [
                {"sample_id": "IK345", "sequence": "ATG-C"},
                {"sample_id": "IK346", "sequence": "ATGTC"},
            ],
        )
        self.assertEqual(view_model.alignment_length, 5)
        self.assertTrue(view_model.column_at(3).is_variable)

    def test_validation_preview_padding_is_display_only_and_preserves_prefixes(self):
        preview = _right_pad_for_display_preview(
            [
                {"sample_id": "IK345", "sequence": "ATGC"},
                {"sample_id": "IK346", "sequence": "ATGCAA"},
            ]
        )

        self.assertEqual(preview[0], {"sample_id": "IK345", "sequence": "ATGC--"})
        self.assertEqual(preview[1], {"sample_id": "IK346", "sequence": "ATGCAA"})

    def test_parser_accepts_aligned_fasta_and_validation_preview_options(self):
        args = build_parser().parse_args(("aligned.fasta",))
        preview_args = build_parser().parse_args(("--validation-known-pairs",))

        self.assertEqual(args.fasta_files, ["aligned.fasta"])
        self.assertFalse(args.validation_known_pairs)
        self.assertTrue(preview_args.validation_known_pairs)

    def test_show_window_uses_hidden_root_and_supplied_factories(self):
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
                self.root = root
                self.view_model = view_model
                calls.append(("window", view_model.alignment_length))

            def protocol(self, name, callback):
                self.name = name
                self.callback = callback
                calls.append(("protocol", name))

        view_model = build_view_model_from_fasta_records_for_test()
        show_multiple_consensus_viewer(
            view_model,
            root_factory=FakeRoot,
            window_factory=FakeWindow,
        )

        self.assertEqual(
            calls,
            ["withdraw", ("window", 2), ("protocol", "WM_DELETE_WINDOW"), "mainloop"],
        )


def build_view_model_from_fasta_records_for_test():
    from gui.multiple_consensus_viewer import build_multiple_alignment_view_model

    return build_multiple_alignment_view_model(
        (
            {"sample_id": "IK345", "sequence": "AT"},
            {"sample_id": "IK346", "sequence": "AT"},
        )
    )


if __name__ == "__main__":
    unittest.main()
