from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.consensus_alignment import (
    MafftExecutableNotFoundError,
    build_consensus_position_mapping,
    run_consensus_alignment,
)


class ConsensusAlignmentTests(unittest.TestCase):
    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_normal_multiple_alignment_preserves_input_order_and_metrics(self, _which):
        result = run_consensus_alignment(
            (
                {"sample_id": "IK345", "sequence": "ATGCAA"},
                {"sample_id": "IK346", "sequence": "ATGTCAA"},
            ),
            alignment_id="test-alignment",
            runner=_runner_for(">IK346\nATGTCAA\n>IK345\nATG-CAA\n"),
        )

        self.assertEqual(result.alignment_id, "test-alignment")
        self.assertEqual(result.number_of_sequences, 2)
        self.assertEqual(result.alignment_length, 7)
        self.assertEqual(result.aligned_sequences, ("ATG-CAA", "ATGTCAA"))
        self.assertEqual(result.gap_count, 1)
        self.assertAlmostEqual(result.gap_percentage, 100 / 14)

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_gap_mapping_uses_none_without_position_inference(self, _which):
        mapping = build_consensus_position_mapping("ATGCAA", "ATG-CAA")

        self.assertEqual(mapping, (0, 1, 2, None, 3, 4, 5))

        result = run_consensus_alignment(
            (
                {"sample_id": "IK345", "sequence": "ATGCAA"},
                {"sample_id": "IK346", "sequence": "ATGTCAA"},
            ),
            runner=_runner_for(">IK345\nATG-CAA\n>IK346\nATGTCAA\n"),
        )
        self.assertIsNone(result.sequence_for_sample("IK345").consensus_position_at(3))
        self.assertEqual(result.sequence_for_sample("IK345").consensus_position_at(4), 3)
        self.assertEqual(result.column_mappings[0], mapping)

    def test_mafft_unavailable_has_actionable_exception(self):
        with patch("core.consensus_alignment.shutil.which", return_value=None):
            with self.assertRaisesRegex(
                MafftExecutableNotFoundError,
                "MAFFT executable not found. Install MAFFT to enable consensus alignment.",
            ):
                run_consensus_alignment(
                    (
                        {"sample_id": "IK345", "sequence": "ATGC"},
                        {"sample_id": "IK346", "sequence": "ATGA"},
                    )
                )

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_runner_receives_consensus_fasta_through_standard_input(self, _which):
        observed = {}

        def runner(command, **kwargs):
            observed["command"] = command
            observed["input"] = kwargs["input"]
            return SimpleNamespace(
                returncode=0,
                stdout=">IK345\nATGC\n>IK346\nATGA\n",
                stderr="",
            )

        result = run_consensus_alignment(
            (
                {"sample_id": "IK345", "sequence": "ATGC"},
                {"sample_id": "IK346", "sequence": "ATGA"},
            ),
            runner=runner,
        )

        self.assertEqual(observed["command"], ["/fake/mafft", "--auto", "-"])
        self.assertEqual(observed["input"], ">IK345\nATGC\n>IK346\nATGA\n")
        self.assertEqual(result.alignment_length, 4)

    @patch("core.consensus_alignment.shutil.which", return_value="/fake/mafft")
    def test_rejects_mafft_output_that_changes_non_gap_consensus_bases(self, _which):
        with self.assertRaisesRegex(ValueError, "does not match original consensus"):
            run_consensus_alignment(
                (
                    {"sample_id": "IK345", "sequence": "ATGC"},
                    {"sample_id": "IK346", "sequence": "ATGA"},
                ),
                runner=_runner_for(">IK345\nATGT\n>IK346\nATGA\n"),
            )


def _runner_for(stdout):
    def runner(_command, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=stdout, stderr="")

    return runner


if __name__ == "__main__":
    unittest.main()
