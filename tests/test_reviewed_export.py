from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from core.consensus_review_session import ConsensusReviewSession
from core.human_review import DecisionType, HumanReviewDecision
from core.reviewed_consensus import build_reviewed_consensus
from core.reviewed_export import export_reviewed_consensus_fasta, export_review_report


TIMESTAMP = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def decision(position, original, reviewed, decision_type):
    return HumanReviewDecision(
        sample_id="IK345",
        consensus_position=position,
        original_base=original,
        reviewed_base=reviewed,
        decision_type=decision_type,
        reason=f"{decision_type.value} test",
        evidence_reference=None,
        reviewer="researcher",
        timestamp=TIMESTAMP,
    )


def session_with(*decisions):
    return ConsensusReviewSession(
        sample_id="IK345",
        candidate_reference=object(),
        decisions=list(decisions),
    )


class ReviewedExportTests(unittest.TestCase):
    def test_exports_reviewed_consensus_as_fasta(self):
        reviewed = build_reviewed_consensus(
            "IK345",
            "ATGC",
            session_with(decision(3, "C", "T", DecisionType.CHANGE)),
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            filepath = Path(temporary_directory) / "IK345_reviewed.fasta"
            export_reviewed_consensus_fasta(reviewed, filepath)

            self.assertEqual(filepath.read_text(encoding="utf-8"), ">IK345_reviewed\nATGT\n")

    def test_exports_change_decision_to_tsv(self):
        self._assert_report_row(
            decision(3, "C", "T", DecisionType.CHANGE),
            "IK345\t3\tC\tT\tCHANGE\tCHANGE test",
        )

    def test_exports_accept_decision_to_tsv(self):
        self._assert_report_row(
            decision(1, "T", "T", DecisionType.ACCEPT),
            "IK345\t1\tT\tT\tACCEPT\tACCEPT test",
        )

    def test_exports_ambiguous_decision_to_tsv(self):
        self._assert_report_row(
            decision(0, "A", "R", DecisionType.AMBIGUOUS),
            "IK345\t0\tA\tR\tAMBIGUOUS\tAMBIGUOUS test",
        )

    def test_exports_do_not_change_the_source_values(self):
        original_sequence = "ATGC"
        session = session_with(decision(2, "G", None, DecisionType.REJECT))
        reviewed = build_reviewed_consensus("IK345", original_sequence, session)
        original_decisions = session.get_decisions()
        with tempfile.TemporaryDirectory() as temporary_directory:
            export_reviewed_consensus_fasta(
                reviewed,
                Path(temporary_directory) / "reviewed.fasta",
            )
            export_review_report(session, Path(temporary_directory) / "report.tsv")

        self.assertEqual(original_sequence, "ATGC")
        self.assertEqual(reviewed.reviewed_sequence, "ATGC")
        self.assertEqual(session.get_decisions(), original_decisions)

    def _assert_report_row(self, review_decision, expected_row):
        with tempfile.TemporaryDirectory() as temporary_directory:
            filepath = Path(temporary_directory) / "review.tsv"
            export_review_report(session_with(review_decision), filepath)
            lines = filepath.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            lines[0],
            "sample_id\tconsensus_position\toriginal_base\treviewed_base\tdecision_type\treason",
        )
        self.assertEqual(lines[1], expected_row)


if __name__ == "__main__":
    unittest.main()
