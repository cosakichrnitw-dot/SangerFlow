import unittest

from core.consensus_alignment import (
    AlignedConsensusSequence,
    AlignedConsensusSet,
    build_consensus_position_mapping,
)
from gui.consensus_review_manager import (
    ConsensusReviewCandidate,
    ConsensusReviewManagerState,
    ReviewMode,
    ReviewSelectionError,
    dispatch_selected_review,
)


def make_candidates():
    return (
        ConsensusReviewCandidate("IK345", "ACGT", single_review_input="single-345"),
        ConsensusReviewCandidate("IK346", "ACGA", single_review_input="single-346"),
        ConsensusReviewCandidate("IK347", "ACGG", single_review_input="single-347"),
    )


def make_aligned_set():
    sequences = tuple(
        AlignedConsensusSequence(
            sample_id=candidate.sample_id,
            original_sequence=candidate.sequence,
            aligned_sequence=candidate.sequence,
            consensus_position_mapping=build_consensus_position_mapping(
                candidate.sequence,
                candidate.sequence,
            ),
        )
        for candidate in make_candidates()[:2]
    )
    return AlignedConsensusSet(
        sequences=sequences,
        alignment_length=4,
        gap_count=0,
        gap_percentage=0.0,
    )


class ConsensusReviewManagerTests(unittest.TestCase):
    def test_candidate_selection_keeps_original_candidate_order(self):
        state = ConsensusReviewManagerState(make_candidates())
        state.set_selected("IK347", True)
        state.set_selected("IK345", True)

        self.assertEqual(
            [candidate.sample_id for candidate in state.selected_candidates()],
            ["IK345", "IK347"],
        )

    def test_mode_switch_is_explicit(self):
        state = ConsensusReviewManagerState(make_candidates())
        state.set_mode(ReviewMode.MULTIPLE)

        self.assertIs(state.mode, ReviewMode.MULTIPLE)

    def test_single_mode_routes_exactly_one_candidate_to_callback(self):
        state = ConsensusReviewManagerState(make_candidates())
        state.set_selected("IK346", True)
        received = []

        dispatch_selected_review(
            state,
            on_open_single=received.append,
            on_open_multiple=None,
        )

        self.assertEqual([candidate.sample_id for candidate in received], ["IK346"])

    def test_multiple_mode_aligns_only_selected_candidates_then_calls_callback(self):
        state = ConsensusReviewManagerState(make_candidates())
        state.set_mode(ReviewMode.MULTIPLE)
        state.set_selected("IK345", True)
        state.set_selected("IK347", True)
        captured_inputs = []
        received = []
        aligned_set = make_aligned_set()

        def runner(inputs):
            captured_inputs.extend(inputs)
            return aligned_set

        dispatch_selected_review(
            state,
            on_open_single=None,
            on_open_multiple=received.append,
            alignment_runner=runner,
        )

        self.assertEqual([item["sample_id"] for item in captured_inputs], ["IK345", "IK347"])
        self.assertEqual(received, [aligned_set])

    def test_invalid_selection_does_not_route_a_viewer_request(self):
        state = ConsensusReviewManagerState(make_candidates())
        with self.assertRaisesRegex(ReviewSelectionError, "exactly one"):
            dispatch_selected_review(
                state,
                on_open_single=lambda _candidate: None,
                on_open_multiple=None,
            )


if __name__ == "__main__":
    unittest.main()
