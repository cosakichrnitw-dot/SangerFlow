from unittest.mock import patch
import unittest

from gui.consensus_review_manager import ConsensusReviewCandidate
from tools.launch_consensus_review_manager import (
    build_parser,
    build_review_candidates_from_ab1_pairs,
    show_consensus_review_manager,
)
class LaunchConsensusReviewManagerTests(unittest.TestCase):
    def test_candidate_builder_uses_existing_single_pair_workflow(self):
        class ViewModel:
            consensus_sequence = "ACGT"

        with patch(
            "tools.launch_consensus_review_manager.build_view_model_from_ab1_pair",
            return_value=ViewModel(),
        ) as builder:
            candidates = build_review_candidates_from_ab1_pairs(
                ["IK345_COl-1_F.ab1", "IK345_COl-1_R.ab1", "IK346_COl-1_F.ab1", "IK346_COl-1_R.ab1"],
            )

        self.assertEqual([candidate.sample_id for candidate in candidates], ["IK345_COl-1", "IK346_COl-1"])
        self.assertEqual([candidate.sequence for candidate in candidates], ["ACGT", "ACGT"])
        self.assertEqual(builder.call_count, 2)

    def test_parser_accepts_validation_or_explicit_pair_input(self):
        validation_args = build_parser().parse_args(("--validation-known-pairs",))
        explicit_args = build_parser().parse_args(("f1.ab1", "r1.ab1", "f2.ab1", "r2.ab1"))

        self.assertTrue(validation_args.validation_known_pairs)
        self.assertEqual(explicit_args.ab1_files, ["f1.ab1", "r1.ab1", "f2.ab1", "r2.ab1"])

    def test_show_manager_routes_single_and_multiple_callbacks_to_window_factories(self):
        calls = []

        class FakeRoot:
            def withdraw(self):
                calls.append("withdraw")

            def destroy(self):
                calls.append("destroy")

            def mainloop(self):
                calls.append("mainloop")

        class FakeManager:
            def __init__(self, root, candidates, on_open_single, on_open_multiple):
                calls.append(("manager", root, len(candidates)))
                on_open_single(candidates[0])
                on_open_multiple("aligned-result")

            def protocol(self, name, callback):
                calls.append(("protocol", name))

        class FakeSingleWindow:
            def __init__(self, root, view_model):
                calls.append(("single", root, view_model))

        class FakeMultipleWindow:
            def __init__(self, root, aligned_result, *, evidence_map, on_trace_jump):
                calls.append(("multiple", root, aligned_result, evidence_map, on_trace_jump))

        root = FakeRoot()
        candidate = ConsensusReviewCandidate(
            "IK345",
            "ACGT",
            single_review_input="single-model",
        )
        with patch(
            "tools.launch_consensus_review_manager.build_evidence_map_from_review_candidates",
            return_value="evidence-map",
        ):
            show_consensus_review_manager(
                (candidate,),
                root_factory=lambda: root,
                manager_factory=FakeManager,
                single_window_factory=FakeSingleWindow,
                multiple_window_factory=FakeMultipleWindow,
            )

        self.assertEqual(
            calls,
            [
                "withdraw",
                ("manager", root, 1),
                ("single", root, "single-model"),
                ("multiple", root, "aligned-result", "evidence-map", None),
                ("protocol", "WM_DELETE_WINDOW"),
                "mainloop",
            ],
        )


if __name__ == "__main__":
    unittest.main()
