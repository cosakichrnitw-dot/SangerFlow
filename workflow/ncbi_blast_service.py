"""NCBI BLAST Common URL API runner for SangerFlow workflows.

This module is deliberately isolated from GUI code.  It implements the
network-facing runner used by ``workflow.blast_workflow`` and converts NCBI
JSON2 results into the raw hit mapping shape already accepted by the existing
BLAST workflow.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import io
import json
import ssl
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen as _stdlib_urlopen
import zipfile

try:  # pragma: no cover - exercised when certifi is installed in runtime
    import certifi
except Exception:  # pragma: no cover - fallback keeps stdlib verification
    certifi = None

from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.sequence_dataset import SequenceDataset


NCBI_BLAST_ENDPOINT = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"
NCBI_TOOL_NAME = "SangerFlow"
NCBI_MIN_REQUEST_INTERVAL_SECONDS = 10.0
NCBI_MIN_POLL_INTERVAL_SECONDS = 60.0


class NcbiBlastError(RuntimeError):
    """Base error for safe NCBI BLAST service failures."""


class NcbiBlastTimeout(NcbiBlastError):
    """Raised when a BLAST RID never becomes ready before the timeout."""


class NcbiBlastCancelled(NcbiBlastError):
    """Raised when a caller requests cancellation."""


class BlastQueryStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_HIT = "NO_HIT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class NcbiBlastSettings:
    """Minimal v1.0 BLAST URL API parameters."""

    program: str = "blastn"
    database: str = "nt"
    max_target_sequences: int = 10
    expect: float | None = None
    email: str | None = None
    tool: str = NCBI_TOOL_NAME
    endpoint: str = NCBI_BLAST_ENDPOINT
    request_interval_seconds: float = 10.0
    poll_interval_seconds: float = 60.0
    request_timeout_seconds: float = 60.0
    max_wait_seconds: float = 900.0
    max_retries: int = 2
    use_memory_cache: bool = True

    def __post_init__(self) -> None:
        if self.program not in {"blastn", "blastp", "blastx", "tblastn", "tblastx"}:
            raise ValueError("program must be one of blastn, blastp, blastx, tblastn, tblastx")
        _required_text(self.database, "database")
        _required_text(self.endpoint, "endpoint")
        _required_text(self.tool, "tool")
        if self.max_target_sequences <= 0:
            raise ValueError("max_target_sequences must be a positive integer")
        if self.expect is not None and self.expect <= 0:
            raise ValueError("expect must be greater than zero")
        if self.email is not None and not self.email.strip():
            raise ValueError("email must be non-empty when provided")
        if self.request_interval_seconds < 0:
            raise ValueError("request_interval_seconds must be non-negative")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be non-negative")
        if self.request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if self.max_wait_seconds <= 0:
            raise ValueError("max_wait_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


@dataclass(frozen=True)
class NcbiBlastProgress:
    """Progress event emitted by the real BLAST runner."""

    state: str
    query_id: str | None = None
    completed: int = 0
    total: int = 0
    successful: int = 0
    no_hit: int = 0
    failed: int = 0
    rid: str | None = None
    message: str | None = None
    poll_number: int | None = None
    elapsed_seconds: float | None = None
    http_status: int | None = None
    search_status: str | None = None


ProgressCallback = Callable[[NcbiBlastProgress], None]
CancelCallback = Callable[[], bool]
SleepCallback = Callable[[float], None]
UrlOpenCallback = Callable[[Request], object]


@dataclass(frozen=True)
class NcbiBlastQueryResult:
    query_id: str
    status: BlastQueryStatus
    hits: tuple[BlastHit, ...] = ()
    rid: str | None = None
    error: str | None = None


class NcbiBlastRunner:
    """Sequential, paced NCBI BLAST Common URL API client.

    The runner intentionally submits one query at a time for v1.0.  This keeps
    query IDs unambiguous and respects NCBI's shared-service usage guidance.
    """

    def __init__(
        self,
        settings: NcbiBlastSettings | None = None,
        *,
        urlopen: UrlOpenCallback | None = None,
        sleep: SleepCallback | None = None,
        now: Callable[[], float] | None = None,
    ) -> None:
        self.settings = settings or NcbiBlastSettings()
        self._urlopen = urlopen or _stdlib_urlopen
        self._sleep = sleep or time.sleep
        self._now = now or time.monotonic
        self._last_request_at: float | None = None
        self._last_http_status: int | None = None
        self._memory_cache: dict[tuple[object, ...], tuple[Mapping[str, object], ...]] = {}

    def __call__(self, sequence: str) -> Iterable[Mapping[str, object]]:
        """Workflow-compatible single-query runner."""

        result = self.run_query("query", sequence)
        if result.status is BlastQueryStatus.SUCCESS:
            return tuple(_raw_hit_mapping(hit) for hit in result.hits)
        if result.status is BlastQueryStatus.NO_HIT:
            return ()
        raise NcbiBlastError(result.error or "NCBI BLAST query failed")

    def run_dataset(
        self,
        dataset: SequenceDataset,
        *,
        analysis_mode: BlastAnalysisMode,
        marker: str | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> BlastResultDataset:
        if not isinstance(dataset, SequenceDataset):
            raise ValueError("dataset must be a SequenceDataset")
        if not dataset.records:
            raise ValueError("dataset must contain at least one sequence record")
        if not isinstance(analysis_mode, BlastAnalysisMode):
            raise ValueError("analysis_mode must be a BlastAnalysisMode")

        query_results: list[NcbiBlastQueryResult] = []
        hits: list[BlastHit] = []
        total = dataset.sequence_count
        counters = {BlastQueryStatus.SUCCESS: 0, BlastQueryStatus.NO_HIT: 0, BlastQueryStatus.FAILED: 0}

        for record in dataset.records:
            if should_cancel is not None and should_cancel():
                query_results.append(NcbiBlastQueryResult(record.sequence_id, BlastQueryStatus.CANCELLED))
                _emit(progress, "Cancelled", record.sequence_id, len(query_results), total, counters)
                break
            _emit(progress, "Submitting", record.sequence_id, len(query_results), total, counters)
            result = self.run_query(record.sequence_id, record.sequence, progress=progress, should_cancel=should_cancel)
            query_results.append(result)
            if result.status in counters:
                counters[result.status] += 1
            hits.extend(result.hits)
            _emit(
                progress,
                "Complete" if result.status is BlastQueryStatus.SUCCESS else result.status.value,
                record.sequence_id,
                len(query_results),
                total,
                counters,
                rid=result.rid,
                message=result.error,
            )

        if not hits:
            raise NcbiBlastError("NCBI BLAST returned no successful hits")

        return BlastResultDataset(
            result_id=f"{dataset.dataset_id}_blast_{analysis_mode.value.lower()}",
            name=f"{dataset.name} BLAST ({analysis_mode.value})",
            hits=tuple(hits),
            parent_dataset_id=dataset.dataset_id,
            analysis_mode=analysis_mode,
            marker=marker,
            database=self.settings.database,
            metadata={
                "workflow": "BLAST",
                "service": "NCBI BLAST Common URL API",
                "remote_service": self.settings.endpoint,
                "program": self.settings.program,
                "database": self.settings.database,
                "parameters": {
                    "hitlist_size": self.settings.max_target_sequences,
                    "expect": self.settings.expect,
                    "format_type": "JSON2",
                    "tool": self.settings.tool,
                },
                "query_date": datetime.now(timezone.utc).isoformat(),
                "result_format": "JSON2",
                "query_statuses": {
                    result.query_id: {
                        "status": result.status.value,
                        "rid": result.rid,
                        "error": result.error,
                    }
                    for result in query_results
                },
                "input_source_type": dataset.source_type.value,
                "input_sequence_count": dataset.sequence_count,
                "successful_queries": counters[BlastQueryStatus.SUCCESS],
                "no_hit_queries": counters[BlastQueryStatus.NO_HIT],
                "failed_queries": counters[BlastQueryStatus.FAILED],
            },
        )

    def run_query(
        self,
        query_id: str,
        sequence: str,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> NcbiBlastQueryResult:
        _required_text(query_id, "query_id")
        _required_text(sequence, "sequence")
        try:
            cache_key = self._cache_key(sequence)
            if self.settings.use_memory_cache and cache_key in self._memory_cache:
                raw_hits = self._memory_cache[cache_key]
                hits = tuple(_blast_hit_from_raw(query_id, raw_hit, self.settings.database) for raw_hit in raw_hits)
                return NcbiBlastQueryResult(query_id, BlastQueryStatus.SUCCESS if hits else BlastQueryStatus.NO_HIT, hits=hits, rid="memory-cache")
            rid, rtoe = self.submit(query_id, sequence)
            _emit_single(progress, "Waiting", query_id, rid=rid, message=f"RTOE={rtoe}")
            payload = self.wait_for_result(
                rid,
                rtoe,
                query_id=query_id,
                progress=progress,
                should_cancel=should_cancel,
            )
            raw_hits = parse_blast_json2(payload, query_length=len(sequence), database=self.settings.database)
            if self.settings.use_memory_cache:
                self._memory_cache[cache_key] = raw_hits
            if not raw_hits:
                return NcbiBlastQueryResult(query_id, BlastQueryStatus.NO_HIT, rid=rid)
            hits = tuple(_blast_hit_from_raw(query_id, raw_hit, self.settings.database) for raw_hit in raw_hits)
            return NcbiBlastQueryResult(query_id, BlastQueryStatus.SUCCESS, hits=hits, rid=rid)
        except NcbiBlastCancelled:
            return NcbiBlastQueryResult(query_id, BlastQueryStatus.CANCELLED)
        except Exception as error:
            return NcbiBlastQueryResult(query_id, BlastQueryStatus.FAILED, error=str(error))

    def submit(self, query_id: str, sequence: str) -> tuple[str, int]:
        fasta = f">{query_id}\n{sequence}\n"
        params: dict[str, object] = {
            "CMD": "Put",
            "PROGRAM": self.settings.program,
            "DATABASE": self.settings.database,
            "QUERY": fasta,
            "HITLIST_SIZE": self.settings.max_target_sequences,
            "FORMAT_TYPE": "JSON2",
            "TOOL": self.settings.tool,
        }
        if self.settings.email:
            params["EMAIL"] = self.settings.email
        if self.settings.expect is not None:
            params["EXPECT"] = self.settings.expect
        response = self._request(params)
        rid = _extract_response_value(response, "RID")
        rtoe_text = _extract_response_value(response, "RTOE", required=False)
        try:
            rtoe = int(rtoe_text) if rtoe_text else 0
        except ValueError:
            rtoe = 0
        if not rid:
            raise NcbiBlastError("NCBI BLAST submission response did not include RID")
        return rid, rtoe

    def wait_for_result(
        self,
        rid: str,
        rtoe: int,
        *,
        query_id: str | None = None,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCallback | None = None,
    ) -> str:
        start = self._now()
        poll_interval = max(self.settings.poll_interval_seconds, NCBI_MIN_POLL_INTERVAL_SECONDS)
        # The Common URL API requires a RID to be polled no more often than
        # once per minute.  RTOE is an estimate, not permission to poll an
        # RTOE=0 RID immediately, so the first poll is always conservative.
        initial_wait = max(float(rtoe), poll_interval)
        _emit_single(
            progress,
            "Initial wait",
            query_id or "",
            rid=rid,
            message=f"RTOE={rtoe}; waiting {initial_wait:g}s before first poll",
            elapsed_seconds=0.0,
        )
        self._sleep(initial_wait)
        poll_number = 0
        while True:
            if should_cancel is not None and should_cancel():
                raise NcbiBlastCancelled("NCBI BLAST query cancelled")
            elapsed = self._now() - start
            if elapsed > self.settings.max_wait_seconds:
                raise NcbiBlastTimeout(f"NCBI BLAST timed out waiting for RID {rid}")
            status_payload = self._request({"CMD": "Get", "RID": rid})
            poll_number += 1
            status = _extract_response_value(status_payload, "Status", required=False)
            _emit_single(
                progress,
                "Polling",
                query_id or "",
                rid=rid,
                message=f"poll={poll_number}; status={status or 'RESULT_PAYLOAD'}",
                poll_number=poll_number,
                elapsed_seconds=elapsed,
                http_status=self._last_http_status,
                search_status=status or None,
            )
            if status == "WAITING":
                self._sleep(poll_interval)
                continue
            if status in {"FAILED", "UNKNOWN"}:
                raise NcbiBlastError(f"NCBI BLAST RID {rid} status is {status}")
            if status == "READY":
                hits = _extract_response_value(status_payload, "ThereAreHits", required=False)
                if hits and hits.lower() == "no":
                    return _empty_blast_json2()
                return self.retrieve(rid)
            if status_payload.lstrip().startswith(("{", "[")):
                return status_payload
            if _looks_like_blast_result_page(status_payload):
                return self.retrieve(rid)
            self._sleep(poll_interval)

    def retrieve(self, rid: str) -> str:
        return self._request({"CMD": "Get", "RID": rid, "FORMAT_TYPE": "JSON2"})

    def _request(self, params: Mapping[str, object]) -> str:
        encoded = urlencode({key: str(value) for key, value in params.items()}).encode("utf-8")
        request = Request(
            self.settings.endpoint,
            data=encoded,
            headers={"User-Agent": f"{self.settings.tool}/1.0"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            self._pace()
            try:
                response = self._urlopen_with_context(request)
                data = response.read()
                self._last_http_status = getattr(response, "status", None) or getattr(response, "code", None) or 200
                return _decode_response_data(data)
            except HTTPError as error:
                if 400 <= error.code < 500 and error.code not in {408, 429}:
                    raise NcbiBlastError(f"NCBI BLAST permanent HTTP error {error.code}") from error
                last_error = error
            except (URLError, TimeoutError, OSError) as error:
                last_error = error
            if attempt < self.settings.max_retries:
                self._sleep(min(2.0 ** attempt, 30.0))
        raise NcbiBlastError(f"NCBI BLAST request failed: {last_error}") from last_error

    def _urlopen_with_context(self, request: Request) -> object:
        if self._urlopen is not _stdlib_urlopen:
            return self._urlopen(request)
        context = _ssl_context()
        return _stdlib_urlopen(request, timeout=self.settings.request_timeout_seconds, context=context)

    def _pace(self) -> None:
        if self._last_request_at is None:
            self._last_request_at = self._now()
            return
        elapsed = self._now() - self._last_request_at
        request_interval = max(self.settings.request_interval_seconds, NCBI_MIN_REQUEST_INTERVAL_SECONDS)
        wait = request_interval - elapsed
        if wait > 0:
            self._sleep(wait)
        self._last_request_at = self._now()

    def _cache_key(self, sequence: str) -> tuple[object, ...]:
        digest = hashlib.sha256(sequence.upper().encode("ascii", errors="ignore")).hexdigest()
        return (
            digest,
            self.settings.program,
            self.settings.database,
            self.settings.max_target_sequences,
            self.settings.expect,
            "JSON2",
        )


def parse_blast_json2(payload: str, *, query_length: int, database: str) -> tuple[Mapping[str, object], ...]:
    """Parse NCBI JSON2 BLAST output into existing workflow raw-hit mappings."""

    data = json.loads(payload)
    records = data if isinstance(data, list) else (data,)
    hits: list[Mapping[str, object]] = []
    for record in records:
        search = _json_search(record)
        if not search:
            continue
        qlen = int(search.get("query_len") or query_length)
        for hit in search.get("hits", ()) or ():
            descriptions = hit.get("description", ()) or ()
            description = descriptions[0] if descriptions else {}
            hsps = hit.get("hsps", ()) or ()
            if not hsps:
                continue
            hsp = hsps[0]
            align_len = int(hsp.get("align_len") or hsp.get("align_length") or 0)
            identities = int(hsp.get("identity") or hsp.get("identities") or 0)
            if align_len <= 0:
                continue
            query_from = hsp.get("query_from")
            query_to = hsp.get("query_to")
            if isinstance(query_from, int) and isinstance(query_to, int):
                coverage = abs(query_to - query_from) + 1
            else:
                coverage = align_len
            scientific_name = _clean_text(description.get("sciname")) or "Unknown"
            title = _clean_text(description.get("title")) or scientific_name
            accession = _clean_text(description.get("accession")) or _accession_from_id(description.get("id")) or "unknown"
            hits.append(
                {
                    "scientific_name": scientific_name,
                    "organism": scientific_name,
                    "species": scientific_name,
                    "identity": round(identities / align_len * 100.0, 3),
                    "coverage": round(min(coverage / qlen * 100.0, 100.0), 3) if qlen > 0 else 0.0,
                    "alignment_length": align_len,
                    "e_value": float(hsp.get("evalue") or hsp.get("expect") or 0.0),
                    "accession": accession,
                    "title": title,
                    "database": database,
                    "bit_score": hsp.get("bit_score"),
                }
            )
    return tuple(hits)


def _blast_hit_from_raw(query_id: str, raw_hit: Mapping[str, object], database: str) -> BlastHit:
    return BlastHit(
        query_id=query_id,
        hit_accession=str(raw_hit["accession"]),
        scientific_name=str(raw_hit.get("scientific_name") or raw_hit.get("species") or "Unknown"),
        organism=str(raw_hit.get("organism") or raw_hit.get("scientific_name") or raw_hit.get("species") or "Unknown"),
        identity=float(raw_hit["identity"]),
        query_coverage=float(raw_hit["coverage"]),
        evalue=float(raw_hit["e_value"]),
        alignment_length=int(raw_hit["alignment_length"]),
        database=str(raw_hit.get("database") or database),
        bit_score=raw_hit.get("bit_score"),
        description=raw_hit.get("description") or raw_hit.get("title"),
    )


def _raw_hit_mapping(hit: BlastHit) -> Mapping[str, object]:
    return {
        "scientific_name": hit.scientific_name,
        "organism": hit.organism,
        "species": hit.scientific_name,
        "identity": hit.identity,
        "coverage": hit.query_coverage,
        "alignment_length": hit.alignment_length,
        "e_value": hit.evalue,
        "accession": hit.hit_accession,
        "database": hit.database,
        "bit_score": hit.bit_score,
        "description": hit.description,
    }


def _emit(
    progress: ProgressCallback | None,
    state: str,
    query_id: str | None,
    completed: int,
    total: int,
    counters: Mapping[BlastQueryStatus, int],
    *,
    rid: str | None = None,
    message: str | None = None,
) -> None:
    if progress is None:
        return
    progress(
        NcbiBlastProgress(
            state=state,
            query_id=query_id,
            completed=completed,
            total=total,
            successful=counters.get(BlastQueryStatus.SUCCESS, 0),
            no_hit=counters.get(BlastQueryStatus.NO_HIT, 0),
            failed=counters.get(BlastQueryStatus.FAILED, 0),
            rid=rid,
            message=message,
        )
    )


def _emit_single(
    progress: ProgressCallback | None,
    state: str,
    query_id: str,
    *,
    rid: str | None = None,
    message: str | None = None,
    poll_number: int | None = None,
    elapsed_seconds: float | None = None,
    http_status: int | None = None,
    search_status: str | None = None,
) -> None:
    if progress is not None:
        progress(
            NcbiBlastProgress(
                state=state,
                query_id=query_id,
                rid=rid,
                message=message,
                poll_number=poll_number,
                elapsed_seconds=elapsed_seconds,
                http_status=http_status,
                search_status=search_status,
            )
        )


def _json_search(record: object) -> Mapping[str, Any] | None:
    if not isinstance(record, Mapping):
        return None
    node = record.get("BlastOutput2", record)
    if isinstance(node, Mapping):
        node = node.get("report", node)
    if isinstance(node, Mapping):
        node = node.get("results", node)
    if isinstance(node, Mapping):
        node = node.get("search", node)
    return node if isinstance(node, Mapping) else None


def _extract_response_value(text: str, key: str, *, required: bool = True) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if "=" not in stripped:
            continue
        left, right = stripped.split("=", 1)
        if left.strip() == key:
            return right.strip()
    if required:
        raise NcbiBlastError(f"NCBI BLAST response did not include {key}")
    return ""


def _empty_blast_json2() -> str:
    return json.dumps({"BlastOutput2": {"report": {"results": {"search": {"hits": []}}}}})


def _decode_response_data(data: bytes) -> str:
    """Decode NCBI responses, including JSON2 zip payloads returned for RIDs."""

    if data.startswith(b"PK\x03\x04"):
        records: list[object] = []
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for member_name in sorted(archive.namelist()):
                if not member_name.lower().endswith(".json"):
                    continue
                payload = archive.read(member_name).decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping) and "BlastJSON" in parsed:
                    continue
                records.append(parsed)
        if not records:
            raise NcbiBlastError("NCBI BLAST JSON2 zip did not contain result JSON")
        if len(records) == 1:
            return json.dumps(records[0])
        return json.dumps(records)
    return data.decode("utf-8", errors="replace")


def _looks_like_blast_result_page(payload: str) -> bool:
    lowered = payload[:1000].casefold()
    return "<html" in lowered and "ncbi blast" in lowered


def _clean_text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _accession_from_id(value: object) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    parts = [part for part in text.split("|") if part]
    for part in reversed(parts):
        if "." in part or part.isalnum():
            return part
    return text


def _ssl_context() -> ssl.SSLContext:
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value
