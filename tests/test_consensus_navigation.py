from types import SimpleNamespace
import unittest

from gui.main_window import MainWindow


class ConsensusNavigationTests(unittest.TestCase):
    def test_main_window_adapter_delegates_bridge_coordinates_unchanged(self):
        received = []
        fake_window = SimpleNamespace(
            alignment_clicked=lambda read_identifier, raw_trace_position, base: received.append(
                (read_identifier, raw_trace_position, base)
            )
        )

        MainWindow._jump_to_consensus_trace(
            fake_window,
            "reverse.ab1",
            7867,
        )

        self.assertEqual(received, [("reverse.ab1", 7867, None)])


if __name__ == "__main__":
    unittest.main()
