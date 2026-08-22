"""Pluggable external storage for concrete analysis-result payloads.

``Project`` stores only the shared :class:`AnalysisResult` reference.  This
module owns optional payload storage for BLAST and BOLD results, without
making Project depend on a filesystem, database, or result implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import json
from collections.abc import Mapping
from math import isfinite
from pathlib import Path
from typing import Union

from core.analysis_result import AnalysisResult, AnalysisResultType
from core.blast_result import BlastAnalysisMode, BlastHit, BlastResultDataset
from core.bold_result import BoldHit, BoldResultDataset


StoredAnalysisResult = Union[BlastResultDataset, BoldResultDataset]


class ResultRepositoryError(ValueError):
    """Raised when a result payload cannot be registered or resolved."""


class ResultRepository(ABC):
    """Storage interface for concrete analysis result payloads.

    Alternative implementations may use SQLite, a network service, or another
    persistent store while preserving this small application-facing contract.
    """

    @abstractmethod
    def register_result(self, result: StoredAnalysisResult) -> str:
        """Persist a result payload and return its stable result ID."""

    @abstractmethod
    def get_result(self, result_id: str) -> StoredAnalysisResult:
        """Return the payload identified by ``result_id``."""

    @abstractmethod
    def remove_result(self, result_id: str) -> None:
        """Remove one stored payload."""

    @abstractmethod
    def has_result(self, result_id: str) -> bool:
        """Whether the repository currently contains ``result_id``."""

    def get_for_analysis_result(self, analysis_result: AnalysisResult) -> StoredAnalysisResult:
        """Resolve a Project-held common reference without importing Project."""
        if not isinstance(analysis_result, AnalysisResult):
            raise ResultRepositoryError("analysis_result must be an AnalysisResult")
        result = self.get_result(analysis_result.result_id)
        actual = result.analysis_result
        if (
            actual.result_type is not analysis_result.result_type
            or actual.parent_dataset_id != analysis_result.parent_dataset_id
        ):
            raise ResultRepositoryError(
                "stored result does not match the supplied AnalysisResult reference"
            )
        return result


class FilesystemResultRepository(ResultRepository):
    """JSON-files backend for BLAST/BOLD result payloads.

    ``root_directory/results/index.json`` maps stable result IDs to payload
    filenames.  Individual files retain each result's complete hit payload;
    Project JSON stores only the corresponding common reference.
    """

    _INDEX_FILENAME = "index.json"
    _FORMAT_VERSION = 1

    def __init__(self, root_directory: str | Path) -> None:
        if not isinstance(root_directory, (str, Path)):
            raise ResultRepositoryError("root_directory must be a string or Path")
        self.root_directory = Path(root_directory)
        if not str(self.root_directory).strip():
            raise ResultRepositoryError("root_directory must not be empty")
        self.results_directory = self.root_directory / "results"

    def register_result(self, result: StoredAnalysisResult) -> str:
        _validate_stored_result(result)
        result_id = result.result_id
        self._ensure_directory()
        index = self._load_index()
        if result_id in index:
            raise ResultRepositoryError(f"result_id already exists in repository: {result_id}")

        result_kind = _result_kind(result)
        filename = f"{result_kind.lower()}_{_safe_result_token(result_id)}.json"
        payload_path = self.results_directory / filename
        if payload_path.exists():
            raise ResultRepositoryError(f"result payload path already exists: {payload_path.name}")

        _write_json(payload_path, _serialize_result(result))
        index[result_id] = filename
        _write_json(self.results_directory / self._INDEX_FILENAME, {"results": index})
        return result_id

    def get_result(self, result_id: str) -> StoredAnalysisResult:
        result_id = _required_result_id(result_id)
        index = self._load_index()
        filename = index.get(result_id)
        if filename is None:
            raise ResultRepositoryError(f"result_id does not exist in repository: {result_id}")
        payload_path = self.results_directory / filename
        try:
            with payload_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError as error:
            raise ResultRepositoryError(
                f"result payload is missing for result_id: {result_id}"
            ) from error
        except (OSError, json.JSONDecodeError) as error:
            raise ResultRepositoryError(f"could not read result payload: {error}") from error
        result = _deserialize_result(payload)
        if result.result_id != result_id:
            raise ResultRepositoryError("result payload ID does not match repository index")
        return result

    def remove_result(self, result_id: str) -> None:
        result_id = _required_result_id(result_id)
        index = self._load_index()
        filename = index.get(result_id)
        if filename is None:
            raise ResultRepositoryError(f"result_id does not exist in repository: {result_id}")
        payload_path = self.results_directory / filename
        try:
            payload_path.unlink()
        except FileNotFoundError as error:
            raise ResultRepositoryError(
                f"result payload is missing for result_id: {result_id}"
            ) from error
        except OSError as error:
            raise ResultRepositoryError(f"could not remove result payload: {error}") from error
        del index[result_id]
        _write_json(self.results_directory / self._INDEX_FILENAME, {"results": index})

    def has_result(self, result_id: str) -> bool:
        result_id = _required_result_id(result_id)
        return result_id in self._load_index()

    def _ensure_directory(self) -> None:
        try:
            self.results_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ResultRepositoryError(f"could not create result repository: {error}") from error

    def _load_index(self) -> dict[str, str]:
        index_path = self.results_directory / self._INDEX_FILENAME
        if not index_path.exists():
            return {}
        try:
            with index_path.open("r", encoding="utf-8") as handle:
                document = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise ResultRepositoryError(f"could not read result repository index: {error}") from error
        if not isinstance(document, Mapping) or not isinstance(document.get("results"), Mapping):
            raise ResultRepositoryError("invalid result repository index")
        index: dict[str, str] = {}
        for result_id, filename in document["results"].items():
            if not isinstance(result_id, str) or not isinstance(filename, str):
                raise ResultRepositoryError("invalid result repository index entry")
            if Path(filename).name != filename:
                raise ResultRepositoryError("invalid result repository payload filename")
            index[result_id] = filename
        return index


def _serialize_result(result: StoredAnalysisResult) -> dict[str, object]:
    if isinstance(result, BlastResultDataset):
        return {
            "format_version": FilesystemResultRepository._FORMAT_VERSION,
            "result_kind": "BLAST",
            "result": {
                "result_id": result.result_id,
                "name": result.name,
                "parent_dataset_id": result.parent_dataset_id,
                "metadata": _json_metadata(result.metadata),
                "analysis_mode": result.analysis_mode.value,
                "marker": result.marker,
                "database": result.database,
                "hits": [
                    {
                        "query_id": hit.query_id,
                        "hit_accession": hit.hit_accession,
                        "scientific_name": hit.scientific_name,
                        "organism": hit.organism,
                        "identity": hit.identity,
                        "query_coverage": hit.query_coverage,
                        "evalue": hit.evalue,
                        "alignment_length": hit.alignment_length,
                        "database": hit.database,
                        "bit_score": hit.bit_score,
                        "description": hit.description,
                    }
                    for hit in result.hits
                ],
            },
        }
    if isinstance(result, BoldResultDataset):
        return {
            "format_version": FilesystemResultRepository._FORMAT_VERSION,
            "result_kind": "BOLD",
            "result": {
                "result_id": result.result_id,
                "name": result.name,
                "parent_dataset_id": result.parent_dataset_id,
                "marker": result.marker,
                "database": result.database,
                "metadata": _json_metadata(result.metadata),
                "hits": [
                    {
                        "query_id": hit.query_id,
                        "process_id": hit.process_id,
                        "record_id": hit.record_id,
                        "species_name": hit.species_name,
                        "genus": hit.genus,
                        "family": hit.family,
                        "order": hit.order,
                        "phylum": hit.phylum,
                        "bin_uri": hit.bin_uri,
                        "similarity": hit.similarity,
                        "database": hit.database,
                        "country": hit.country,
                        "institution": hit.institution,
                        "specimen_id": hit.specimen_id,
                        "collection_date": hit.collection_date,
                    }
                    for hit in result.hits
                ],
            },
        }
    raise ResultRepositoryError("unsupported result type")


def _deserialize_result(document: object) -> StoredAnalysisResult:
    if not isinstance(document, Mapping):
        raise ResultRepositoryError("invalid result payload")
    if document.get("format_version") != FilesystemResultRepository._FORMAT_VERSION:
        raise ResultRepositoryError("unsupported result payload format_version")
    kind = document.get("result_kind")
    payload = document.get("result")
    if not isinstance(payload, Mapping):
        raise ResultRepositoryError("invalid result payload body")
    try:
        if kind == "BLAST":
            return BlastResultDataset(
                result_id=payload["result_id"],
                name=payload["name"],
                parent_dataset_id=payload["parent_dataset_id"],
                metadata=payload.get("metadata"),
                analysis_mode=BlastAnalysisMode(payload["analysis_mode"]),
                marker=payload.get("marker"),
                database=payload.get("database"),
                hits=tuple(BlastHit(**hit) for hit in _hits(payload)),
            )
        if kind == "BOLD":
            return BoldResultDataset(
                result_id=payload["result_id"],
                name=payload["name"],
                parent_dataset_id=payload["parent_dataset_id"],
                marker=payload.get("marker"),
                database=payload["database"],
                metadata=payload.get("metadata"),
                hits=tuple(BoldHit(**hit) for hit in _hits(payload)),
            )
    except (KeyError, TypeError, ValueError) as error:
        raise ResultRepositoryError(f"invalid {kind!r} result payload: {error}") from error
    raise ResultRepositoryError(f"unsupported result payload kind: {kind!r}")


def _hits(payload: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    hits = payload.get("hits")
    if not isinstance(hits, list) or any(not isinstance(hit, Mapping) for hit in hits):
        raise ResultRepositoryError("result payload hits must be an array of objects")
    return tuple(dict(hit) for hit in hits)


def _validate_stored_result(result: object) -> None:
    if not isinstance(result, (BlastResultDataset, BoldResultDataset)):
        raise ResultRepositoryError(
            "result must be a BlastResultDataset or BoldResultDataset"
        )


def _result_kind(result: StoredAnalysisResult) -> str:
    return "BLAST" if isinstance(result, BlastResultDataset) else "BOLD"


def _required_result_id(result_id: object) -> str:
    if not isinstance(result_id, str) or not result_id.strip():
        raise ResultRepositoryError("result_id must be a non-empty string")
    return result_id


def _safe_result_token(result_id: str) -> str:
    """Use a readable, traversal-safe filename stem with collision resistance."""
    readable = "".join(character if character.isalnum() else "_" for character in result_id)
    readable = readable.strip("_") or "result"
    digest = hashlib.sha256(result_id.encode("utf-8")).hexdigest()[:12]
    return f"{readable[:48]}_{digest}"


def _json_metadata(metadata: Mapping[str, object]) -> dict[str, object]:
    value = _json_value(metadata, "result metadata")
    if not isinstance(value, dict):  # Defensive: Mapping must produce a dict.
        raise ResultRepositoryError("result metadata must be an object")
    return value


def _json_value(value: object, context: str) -> object:
    """Deep-copy immutable metadata into standard JSON container values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ResultRepositoryError(f"{context} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        converted: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ResultRepositoryError(f"{context} contains a non-string key")
            converted[key] = _json_value(item, f"{context}.{key}")
        return converted
    if isinstance(value, (list, tuple)):
        return [_json_value(item, context) for item in value]
    raise ResultRepositoryError(
        f"{context} contains a value that is not JSON-compatible: {type(value).__name__}"
    )


def _write_json(path: Path, value: object) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except (OSError, TypeError, ValueError) as error:
        raise ResultRepositoryError(f"could not write result repository data: {error}") from error
