from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gui.consensus_review_manager import ConsensusReviewCandidate
from gui.main_window import MainWindow


class MainConsensusReviewManagerTests(unittest.TestCase):
    def _make_window_adapter(self):
        window = SimpleNamespace(
            root=object(),
            reads=(object(),),
            status_bar=SimpleNamespace(set_text=Mock()),
            open_single_consensus_review=Mock(),
        )
        window._jump_to_consensus_trace = Mock()
        window._open_consensus_review_candidate = MethodType(
            MainWindow._open_consensus_review_candidate,
            window,
        )
        window._open_multiple_consensus_review = MethodType(
            MainWindow._open_multiple_consensus_review,
            window,
        )
        return window

    def test_loaded_clear_pairs_open_existing_manager_with_both_viewer_routes(self):
        window = self._make_window_adapter()
        candidate = ConsensusReviewCandidate(
            "IK345",
            "ATGC",
            single_review_input="single-review-input",
        )
        review_inputs = SimpleNamespace(
            candidates=(candidate,),
            evidence_map="evidence-map",
        )
        manager_window = object()
        multiple_window = object()

        with (
            patch("gui.main_window.discover_clear_pairs", return_value=("clear-pair",)),
            patch(
                "gui.main_window.build_consensus_review_manager_inputs",
                return_value=review_inputs,
            ) as build_inputs,
            patch(
                "gui.main_window.ConsensusReviewManagerWindow",
                return_value=manager_window,
            ) as manager_factory,
            patch(
                "gui.main_window.MultipleConsensusAlignmentWindow",
                return_value=multiple_window,
            ) as multiple_factory,
        ):
            result = MainWindow.open_consensus_review_manager(window)

            self.assertIs(result, manager_window)
            build_inputs.assert_called_once_with(("clear-pair",))
            window.status_bar.set_text.assert_called_once_with(
                "1 consensus candidate(s) ready for review"
            )
            manager_factory.assert_called_once()
            callbacks = manager_factory.call_args.kwargs
            callbacks["on_open_single"](candidate)
            window.open_single_consensus_review.assert_called_once_with("single-review-input")
            callbacks["on_open_multiple"]("aligned-set")
            multiple_factory.assert_called_once_with(
                window.root,
                "aligned-set",
                evidence_map="evidence-map",
                on_trace_jump=window._jump_to_consensus_trace,
            )

    def test_legacy_selector_alias_uses_the_manager_entry(self):
        window = SimpleNamespace(open_consensus_review_manager=Mock(return_value="manager"))

        result = MainWindow.open_consensus_review_selector(window)

        self.assertEqual(result, "manager")
        window.open_consensus_review_manager.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
