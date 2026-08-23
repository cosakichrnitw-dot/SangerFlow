import unittest

from core.models import SangerRead
from core.samples import (
    PairingStatus,
    ReadOrientation,
    SampleClassification,
    classify_reads_by_filename,
    parse_read_filename,
)


def make_read(filename: str) -> SangerRead:
    return SangerRead(
        filename=filename,
        sequence="ACGT",
        quality=[30, 30, 30, 30],
        traces={"A": [], "C": [], "G": [], "T": []},
        base_positions=[1, 2, 3, 4],
    )


class FilenameParsingTests(unittest.TestCase):
    def test_recognises_short_forward_suffix(self):
        self.assertEqual(
            parse_read_filename("Sample_001_F.ab1"),
            ("Sample_001", ReadOrientation.FORWARD),
        )

    def test_recognises_long_reverse_suffix(self):
        self.assertEqual(
            parse_read_filename("Sample-001-Reverse.ab1"),
            ("Sample-001", ReadOrientation.REVERSE),
        )

    def test_keeps_unoriented_name_as_single_candidate(self):
        self.assertEqual(
            parse_read_filename("Sample_001.ab1"),
            ("Sample_001", ReadOrientation.UNSPECIFIED),
        )


class SampleClassificationTests(unittest.TestCase):
    def test_clear_pair(self):
        sample = classify_reads_by_filename(
            [make_read("Sample_001_F.ab1"), make_read("Sample_001_R.ab1")]
        )[0]

        self.assertEqual(sample.classification, SampleClassification.PAIR)
        self.assertEqual(sample.pairing_status, PairingStatus.CLEAR_PAIR)
        self.assertEqual(sample.forward_read.filename, "Sample_001_F.ab1")
        self.assertEqual(sample.reverse_read.filename, "Sample_001_R.ab1")
        self.assertEqual(
            tuple(read.filename for read in sample.forward_candidates),
            ("Sample_001_F.ab1",),
        )
        self.assertEqual(
            tuple(read.filename for read in sample.reverse_candidates),
            ("Sample_001_R.ab1",),
        )

    def test_forward_only_is_a_valid_single(self):
        sample = classify_reads_by_filename([make_read("Sample_002_F.ab1")])[0]

        self.assertEqual(sample.classification, SampleClassification.SINGLE)
        self.assertEqual(sample.pairing_status, PairingStatus.ORPHAN_FORWARD)
        self.assertEqual(sample.pairing_status.value, "ORPHAN_FORWARD")
        # The legacy spelling remains a compatible alias.
        self.assertIs(sample.pairing_status, PairingStatus.SINGLE_FORWARD)
        self.assertEqual(len(sample.forward_candidates), 1)

    def test_unoriented_file_is_a_valid_single(self):
        sample = classify_reads_by_filename([make_read("Sample_003.ab1")])[0]

        self.assertEqual(sample.classification, SampleClassification.SINGLE)
        self.assertEqual(sample.pairing_status, PairingStatus.SINGLE_UNSPECIFIED)

    def test_orphan_reverse_requires_review(self):
        sample = classify_reads_by_filename([make_read("Sample_004_R.ab1")])[0]

        self.assertEqual(sample.classification, SampleClassification.SINGLE)
        self.assertEqual(sample.pairing_status, PairingStatus.ORPHAN_REVERSE)
        self.assertTrue(sample.reasons)
        self.assertEqual(len(sample.reverse_candidates), 1)

    def test_duplicate_forward_reads_are_ambiguous(self):
        sample = classify_reads_by_filename(
            [make_read("Sample_005_F.ab1"), make_read("Sample_005_Forward.ab1")]
        )[0]

        self.assertEqual(sample.classification, SampleClassification.AMBIGUOUS)
        self.assertEqual(sample.pairing_status, PairingStatus.AMBIGUOUS)
        self.assertEqual(
            tuple(read.filename for read in sample.forward_candidates),
            ("Sample_005_F.ab1", "Sample_005_Forward.ab1"),
        )

    def test_duplicate_reverse_candidates_are_preserved(self):
        sample = classify_reads_by_filename(
            [
                make_read("Sample_006_F.ab1"),
                make_read("Sample_006_R.ab1"),
                make_read("Sample_006_Reverse.ab1"),
            ]
        )[0]

        self.assertEqual(sample.classification, SampleClassification.AMBIGUOUS)
        self.assertEqual(sample.pairing_status, PairingStatus.AMBIGUOUS)
        self.assertEqual(len(sample.forward_candidates), 1)
        self.assertEqual(
            tuple(read.filename for read in sample.reverse_candidates),
            ("Sample_006_R.ab1", "Sample_006_Reverse.ab1"),
        )

    def test_unspecified_candidates_are_not_reclassified(self):
        sample = classify_reads_by_filename([make_read("Sample_007.ab1")])[0]

        self.assertEqual(sample.pairing_status, PairingStatus.SINGLE_UNSPECIFIED)
        self.assertEqual(len(sample.forward_candidates), 0)
        self.assertEqual(len(sample.reverse_candidates), 0)
        self.assertEqual(len(sample.unspecified_candidates), 1)


if __name__ == "__main__":
    unittest.main()
