import unittest

from core.models import SangerRead
from gui.consensus_review_entry import (
    build_consensus_review_manager_inputs,
    build_consensus_review_pair_rows,
    build_review_view_model,
    discover_clear_pairs,
)


def make_read(filename, sequence="ACGTACGT"):
    return SangerRead(
        filename=filename,
        sequence=sequence,
        quality=[40] * len(sequence),
        traces={base: list(range(100)) for base in "ACGT"},
        base_positions=[5 + (index * 5) for index in range(len(sequence))],
    )


class ConsensusReviewEntryTests(unittest.TestCase):
    def test_discovery_selects_only_clear_filename_pairs(self):
        pairs = discover_clear_pairs(
            (
                make_read("sample_a_F.ab1"),
                make_read("sample_a_R.ab1"),
                make_read("single_F.ab1"),
                make_read("orphan_R.ab1"),
            )
        )

        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].sample_id, "sample_a")
        self.assertEqual(pairs[0].forward_read.filename, "sample_a_F.ab1")
        self.assertEqual(pairs[0].reverse_read.filename, "sample_a_R.ab1")

    def test_selected_clear_pair_uses_existing_workflow_to_build_view_model(self):
        pair = discover_clear_pairs(
            (make_read("sample_a_F.ab1"), make_read("sample_a_R.ab1"))
        )[0]

        view_model = build_review_view_model(pair)

        self.assertEqual(view_model.sample_identifier, "sample_a")
        self.assertEqual(view_model.consensus_sequence, "ACGTACGT")
        self.assertEqual(len(view_model.columns), 8)
        self.assertEqual(
            view_model.columns[0].review_evidence.forward_read_identifier,
            "sample_a_F.ab1",
        )
        self.assertEqual(
            view_model.columns[0].review_evidence.reverse_read_identifier,
            "sample_a_R.ab1",
        )

    def test_pair_rows_keep_filenames_and_existing_input_lengths(self):
        forward = make_read("sample_a_F.ab1", "ACGT")
        reverse = make_read("sample_a_R.ab1", "ACGTAC")
        forward.trimmed_sequence = "ACG"
        pair = discover_clear_pairs((forward, reverse))[0]

        row = build_consensus_review_pair_rows((pair,))[0]

        self.assertEqual(row.sample_id, "sample_a")
        self.assertEqual(row.forward_filename, "sample_a_F.ab1")
        self.assertEqual(row.reverse_filename, "sample_a_R.ab1")
        self.assertEqual(row.forward_input_length, 3)
        self.assertEqual(row.reverse_input_length, 6)

    def test_clear_pairs_build_manager_candidates_and_evidence_without_viewer_imports(self):
        pairs = discover_clear_pairs(
            (
                make_read("sample_a_F.ab1"),
                make_read("sample_a_R.ab1"),
                make_read("sample_b_F.ab1"),
                make_read("sample_b_R.ab1"),
            )
        )

        inputs = build_consensus_review_manager_inputs(pairs)

        self.assertEqual([candidate.sample_id for candidate in inputs.candidates], ["sample_a", "sample_b"])
        self.assertEqual(inputs.candidates[0].sequence, "ACGTACGT")
        self.assertEqual(
            inputs.evidence_map.lookup("sample_a", 0).forward_read_identifier,
            "sample_a_F.ab1",
        )
        self.assertEqual(
            inputs.evidence_map.lookup("sample_b", 0).reverse_read_identifier,
            "sample_b_R.ab1",
        )


if __name__ == "__main__":
    unittest.main()
