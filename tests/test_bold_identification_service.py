"""Tests for the BOLD identification service boundary."""

from __future__ import annotations

import unittest

from workflow.bold_identification_service import (
    BoldIdentificationRunner,
    BoldIdentificationUnavailableError,
)


class BoldIdentificationServiceTests(unittest.TestCase):
    def test_default_bold_runner_is_explicitly_unavailable(self) -> None:
        runner = BoldIdentificationRunner()

        with self.assertRaisesRegex(BoldIdentificationUnavailableError, "supported programmatic API"):
            runner("ATGC")


if __name__ == "__main__":
    unittest.main()
