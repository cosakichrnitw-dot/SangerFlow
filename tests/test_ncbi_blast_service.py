"""Tests for the NCBI BLAST Common URL API runner."""

from __future__ import annotations

import io
import json
import unittest
from urllib.parse import parse_qs
import zipfile

from core.blast_result import BlastAnalysisMode
from core.sequence_dataset import SequenceDataset, SourceType
from workflow.ncbi_blast_service import (
    BlastQueryStatus,
    NcbiBlastRunner,
    NcbiBlastSettings,
    parse_blast_json2,
)


def blast_json2() -> str:
    return json.dumps(
        {
            "BlastOutput2": {
                "report": {
                    "results": {
                        "search": {
                            "query_len": 100,
                            "hits": [
                                {
                                    "description": [
                                        {
                                            "accession": "OR123456",
                                            "title": "Rhynchobatus springeri COI",
                                            "sciname": "Rhynchobatus springeri",
                                        }
                                    ],
                                    "hsps": [
                                        {
                                            "align_len": 98,
                                            "identity": 97,
                                            "query_from": 1,
                                            "query_to": 98,
                                            "evalue": 1e-80,
                                            "bit_score": 510.4,
                                        }
                                    ],
                                }
                            ],
                        }
                    }
                }
            }
        }
    )


def _blast_json2_zip() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("RID123.json", json.dumps({"BlastJSON": [{"File": "RID123_1.json"}]}))
        archive.writestr("RID123_1.json", blast_json2())
    return payload.getvalue()


class _Response:
    def __init__(self, payload: str | bytes) -> None:
        self._payload = payload
        self.status = 200

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return self._payload.encode("utf-8")


class _FakeUrlOpen:
    def __init__(self, responses: list[str | bytes]) -> None:
        self.responses = responses
        self.requests: list[dict[str, list[str]]] = []

    def __call__(self, request) -> _Response:
        self.requests.append(parse_qs(request.data.decode("utf-8")))
        return _Response(self.responses.pop(0))


class NcbiBlastServiceTests(unittest.TestCase):
    def test_parse_json2_uses_scientific_name_and_alignment_metrics(self) -> None:
        hits = parse_blast_json2(blast_json2(), query_length=100, database="nt")

        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["scientific_name"], "Rhynchobatus springeri")
        self.assertEqual(hits[0]["accession"], "OR123456")
        self.assertEqual(hits[0]["identity"], 98.98)
        self.assertEqual(hits[0]["coverage"], 98.0)
        self.assertEqual(hits[0]["bit_score"], 510.4)
        self.assertEqual(hits[0]["title"], "Rhynchobatus springeri COI")

    def test_runner_submit_poll_retrieve_builds_result_dataset(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID123\nRTOE = 1\n",
                "Status=WAITING\n",
                "Status=READY\nThereAreHits=yes\n",
                blast_json2(),
            ]
        )
        settings = NcbiBlastSettings(
            database="nt",
            max_target_sequences=5,
            request_interval_seconds=0,
            poll_interval_seconds=0,
            endpoint="https://blast.ncbi.nlm.nih.gov/Blast.cgi",
        )
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=lambda _seconds: None)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100),)
        )

        result = runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION)

        self.assertEqual(result.hit_count(), 1)
        self.assertEqual(result.get_hits("IK345")[0].scientific_name, "Rhynchobatus springeri")
        self.assertEqual(result.get_hits("IK345")[0].bit_score, 510.4)
        self.assertEqual(result.get_hits("IK345")[0].description, "Rhynchobatus springeri COI")
        self.assertEqual(result.metadata["service"], "NCBI BLAST Common URL API")
        self.assertEqual(result.metadata["parameters"]["format_type"], "JSON2")
        self.assertEqual(result.metadata["query_statuses"]["IK345"]["rid"], "RID123")
        self.assertEqual(fake.requests[0]["CMD"], ["Put"])
        self.assertEqual(fake.requests[0]["PROGRAM"], ["blastn"])
        self.assertEqual(fake.requests[0]["DATABASE"], ["nt"])
        self.assertEqual(fake.requests[0]["HITLIST_SIZE"], ["5"])
        self.assertEqual(fake.requests[-1]["FORMAT_TYPE"], ["JSON2"])

    def test_runner_respects_rtoe_before_first_poll_and_reports_poll_debug(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID123\nRTOE = 120\n",
                "Status=READY\nThereAreHits=yes\n",
                blast_json2(),
            ]
        )
        sleeps: list[float] = []
        progress = []
        settings = NcbiBlastSettings(
            request_interval_seconds=0,
            poll_interval_seconds=60,
        )
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=sleeps.append, now=lambda: 0.0)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100),)
        )

        result = runner.run_dataset(
            dataset,
            analysis_mode=BlastAnalysisMode.IDENTIFICATION,
            progress=progress.append,
        )

        self.assertEqual(result.hit_count(), 1)
        self.assertEqual(sleeps[0], 120.0)
        polling_events = [event for event in progress if event.state == "Polling"]
        self.assertEqual(polling_events[0].poll_number, 1)
        self.assertEqual(polling_events[0].search_status, "READY")
        self.assertEqual(polling_events[0].http_status, 200)

    def test_runner_waits_a_safe_minimum_before_first_poll_when_rtoe_is_zero(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID123\nRTOE = 0\n",
                "Status=READY\nThereAreHits=yes\n",
                blast_json2(),
            ]
        )
        sleeps: list[float] = []
        progress = []
        runner = NcbiBlastRunner(
            NcbiBlastSettings(request_interval_seconds=0, poll_interval_seconds=0),
            urlopen=fake,
            sleep=sleeps.append,
            now=lambda: 0.0,
        )
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100),)
        )

        runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION, progress=progress.append)

        self.assertEqual(sleeps[0], 60.0)
        initial = [event for event in progress if event.state == "Initial wait"]
        self.assertEqual(initial[0].message, "RTOE=0; waiting 60s before first poll")

    def test_repeated_waiting_polls_remain_one_minute_apart(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID123\nRTOE = 0\n",
                "Status=WAITING\n",
                "Status=WAITING\n",
                "Status=READY\nThereAreHits=yes\n",
                blast_json2(),
            ]
        )
        sleeps: list[float] = []
        clock = [0.0]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            clock[0] += seconds

        runner = NcbiBlastRunner(
            NcbiBlastSettings(request_interval_seconds=0, poll_interval_seconds=1),
            urlopen=fake,
            sleep=sleep,
            now=lambda: clock[0],
        )
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100),)
        )

        runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION)

        self.assertEqual(sleeps[:3], [60.0, 60.0, 60.0])

    def test_runner_decodes_ncbi_json2_zip_payload(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID123\nRTOE = 0\n",
                "<html><title>NCBI Blast:</title></html>",
                _blast_json2_zip(),
            ]
        )
        settings = NcbiBlastSettings(
            request_interval_seconds=0,
            poll_interval_seconds=0,
        )
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=lambda _seconds: None)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100),)
        )

        result = runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION)

        self.assertEqual(result.hit_count(), 1)
        self.assertEqual(result.get_hits("IK345")[0].hit_accession, "OR123456")
        self.assertEqual(fake.requests[-1]["FORMAT_TYPE"], ["JSON2"])

    def test_partial_failure_keeps_successful_hits(self) -> None:
        fake = _FakeUrlOpen(
            [
                "RID = RID1\nRTOE = 0\n",
                "Status=READY\nThereAreHits=yes\n",
                blast_json2(),
                "RID = RID2\nRTOE = 0\n",
                "Status=FAILED\n",
            ]
        )
        settings = NcbiBlastSettings(request_interval_seconds=0, poll_interval_seconds=0)
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=lambda _seconds: None)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100), ("IK346", "T" * 100))
        )

        result = runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION)

        self.assertEqual(result.query_ids(), ("IK345",))
        self.assertEqual(result.metadata["query_statuses"]["IK345"]["status"], BlastQueryStatus.SUCCESS.value)
        self.assertEqual(result.metadata["query_statuses"]["IK346"]["status"], BlastQueryStatus.FAILED.value)
        self.assertEqual(result.metadata["failed_queries"], 1)

    def test_memory_cache_reuses_same_sequence_with_distinct_query_ids(self) -> None:
        fake = _FakeUrlOpen(["RID = RID1\nRTOE = 0\n", "Status=READY\nThereAreHits=yes\n", blast_json2()])
        settings = NcbiBlastSettings(request_interval_seconds=0, poll_interval_seconds=0)
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=lambda _seconds: None)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100), ("IK346", "A" * 100))
        )

        result = runner.run_dataset(dataset, analysis_mode=BlastAnalysisMode.IDENTIFICATION)

        self.assertEqual(len(fake.requests), 3)
        self.assertEqual(result.query_ids(), ("IK345", "IK346"))
        self.assertEqual(result.metadata["query_statuses"]["IK346"]["rid"], "memory-cache")

    def test_cancel_marks_pending_query_without_crashing(self) -> None:
        fake = _FakeUrlOpen(["RID = RID1\nRTOE = 0\n", "Status=READY\nThereAreHits=yes\n", blast_json2()])
        settings = NcbiBlastSettings(request_interval_seconds=0, poll_interval_seconds=0)
        runner = NcbiBlastRunner(settings, urlopen=fake, sleep=lambda _seconds: None)
        dataset = SequenceDataset.from_sequence_pairs(
            "input", "Input", SourceType.IMPORTED_FASTA, (("IK345", "A" * 100), ("IK346", "T" * 100))
        )
        def should_cancel() -> bool:
            return len(fake.requests) >= 3

        result = runner.run_dataset(
            dataset,
            analysis_mode=BlastAnalysisMode.IDENTIFICATION,
            should_cancel=should_cancel,
        )

        self.assertEqual(result.query_ids(), ("IK345",))
        self.assertEqual(result.metadata["query_statuses"]["IK346"]["status"], BlastQueryStatus.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
