"""Versioned JSON persistence for the serializable Project description.

The JSON file contains Project membership, sequence datasets, and common
analysis-result references.  It intentionally omits opaque source references
and concrete BLAST/BOLD payloads; those belong to their own repositories.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.alignment_dataset import AlignmentDataset, AlignmentRecord, MarkerRegion
from core.analysis_result import AnalysisResult, AnalysisResultType
from core.project import DerivationType, Project, ProjectAnalysisEntry, ProjectDatasetEntry
from core.sequence_dataset import SequenceDataset, SequenceRecord, SourceType


PROJECT_SCHEMA_VERSION = 1


class ProjectPersistenceError(ValueError):
    """Raised when a Project JSON file cannot be safely written or restored."""


def save_project(project: Project, filepath: str | Path) -> None:
    """Write the serializable Project state to a versioned JSON document.

    Concrete analysis payloads are not embedded.  ``AnalysisResult`` metadata
    is retained as a repository reference for a future result-repository layer.
    """
    if not isinstance(project, Project):
        raise ProjectPersistenceError("project must be a Project")
    path = _coerce_path(filepath)
    payload = {
        "schema_version": PROJECT_SCHEMA_VERSION,
        "project": _serialize_project(project),
    }
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
    except (OSError, TypeError, ValueError) as error:
        if isinstance(error, ProjectPersistenceError):
            raise
        raise ProjectPersistenceError(f"could not save project JSON: {error}") from error


def load_project(filepath: str | Path) -> Project:
    """Load a Project saved by :func:`save_project` for this schema version."""
    path = _coerce_path(filepath)
    try:
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
    except FileNotFoundError as error:
        raise ProjectPersistenceError(f"project JSON file does not exist: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectPersistenceError(f"could not load project JSON: {error}") from error

    document_mapping = _mapping(document, "project JSON root")
    schema_version = document_mapping.get("schema_version")
    if schema_version != PROJECT_SCHEMA_VERSION:
        raise ProjectPersistenceError(
            "unsupported project schema_version: "
            f"{schema_version!r}; expected {PROJECT_SCHEMA_VERSION}"
        )
    project_payload = _mapping(document_mapping.get("project"), "project")
    try:
        return _deserialize_project(project_payload)
    except (KeyError, TypeError, ValueError) as error:
        raise ProjectPersistenceError(f"invalid project JSON: {error}") from error


def _serialize_project(project: Project) -> dict[str, object]:
    return {
        "project_id": project.project_id,
        "name": project.name,
        "metadata": _json_value(project.metadata, "project.metadata"),
        "datasets": [_serialize_dataset_entry(entry) for entry in project.dataset_entries],
        "analysis_results": [
            _serialize_analysis_entry(entry) for entry in project.analysis_results
        ],
    }


def _serialize_dataset_entry(entry: ProjectDatasetEntry) -> dict[str, object]:
    dataset = entry.dataset
    if isinstance(dataset, AlignmentDataset):
        dataset_payload = {
            "dataset_model": "AlignmentDataset",
            "alignment_id": dataset.alignment_id,
            "name": dataset.name,
            "parent_dataset_id": dataset.parent_dataset_id,
            "metadata": _json_value(dataset.metadata, f"alignment {dataset.alignment_id} metadata"),
            "marker_regions": [
                {"name": region.name, "start": region.start, "end": region.end}
                for region in dataset.marker_regions
            ],
            "records": [
                {
                    "record_id": record.record_id,
                    "source_record_id": record.source_record_id,
                    "aligned_sequence": record.aligned_sequence,
                    "metadata": _json_value(
                        record.metadata,
                        f"alignment record {record.record_id} metadata",
                    ),
                }
                for record in dataset.records
            ],
        }
        dataset_id = dataset.alignment_id
    else:
        dataset_payload = {
            "dataset_model": "SequenceDataset",
            "dataset_id": dataset.dataset_id,
            "name": dataset.name,
            "source_type": dataset.source_type.value,
            "metadata": _json_value(dataset.metadata, f"dataset {dataset.dataset_id} metadata"),
            "records": [
                {
                    "sequence_id": record.sequence_id,
                    "sequence": record.sequence,
                    "description": record.description,
                    "metadata": _json_value(
                        record.metadata,
                        f"record {record.sequence_id} metadata",
                    ),
                }
                for record in dataset.records
            ],
        }
        dataset_id = dataset.dataset_id
    return {
        "dataset": dataset_payload,
        "display_name": entry.display_name,
        "parent_dataset_id": entry.parent_dataset_id,
        "derivation_type": (
            entry.derivation_type.value if entry.derivation_type is not None else None
        ),
        "metadata": _json_value(entry.metadata, f"dataset entry {dataset_id} metadata"),
    }


def _serialize_analysis_entry(entry: ProjectAnalysisEntry) -> dict[str, object]:
    result = entry.analysis_result
    return {
        # This is intentionally an AnalysisResult reference, not a concrete
        # BlastResultDataset/BoldResultDataset payload.
        "analysis_result": {
            "result_id": result.result_id,
            "name": result.name,
            "result_type": result.result_type.value,
            "parent_dataset_id": result.parent_dataset_id,
            "metadata": _json_value(result.metadata, f"analysis result {result.result_id} metadata"),
        },
        "display_name": entry.display_name,
        "metadata": _json_value(entry.metadata, f"analysis entry {result.result_id} metadata"),
    }


def _deserialize_project(payload: Mapping[str, Any]) -> Project:
    dataset_entries = tuple(
        _deserialize_dataset_entry(_mapping(item, "dataset entry"))
        for item in _sequence(payload.get("datasets"), "datasets")
    )
    analysis_entries = tuple(
        _deserialize_analysis_entry(_mapping(item, "analysis result entry"))
        for item in _sequence(payload.get("analysis_results"), "analysis_results")
    )
    return Project(
        project_id=_text(payload["project_id"], "project_id"),
        name=_text(payload["name"], "project name"),
        dataset_entries=dataset_entries,
        metadata=_metadata(payload.get("metadata"), "project metadata"),
        analysis_results=analysis_entries,
    )


def _deserialize_dataset_entry(payload: Mapping[str, Any]) -> ProjectDatasetEntry:
    dataset_payload = _mapping(payload.get("dataset"), "dataset")
    dataset_model = dataset_payload.get("dataset_model", "SequenceDataset")
    if dataset_model == "AlignmentDataset":
        records = tuple(
            AlignmentRecord(
                record_id=_text(record_payload["record_id"], "record_id"),
                source_record_id=_text(record_payload["source_record_id"], "source_record_id"),
                aligned_sequence=_text(record_payload["aligned_sequence"], "aligned_sequence"),
                metadata=_metadata(record_payload.get("metadata"), "alignment record metadata"),
            )
            for record_payload in (
                _mapping(item, "alignment record")
                for item in _sequence(dataset_payload.get("records"), "records")
            )
        )
        marker_regions = tuple(
            MarkerRegion(
                name=_text(region_payload["name"], "marker region name"),
                start=_integer(region_payload["start"], "marker region start"),
                end=_integer(region_payload["end"], "marker region end"),
            )
            for region_payload in (
                _mapping(item, "marker region")
                for item in _sequence(dataset_payload.get("marker_regions", []), "marker_regions")
            )
        )
        dataset = AlignmentDataset(
            alignment_id=_text(dataset_payload["alignment_id"], "alignment_id"),
            name=_text(dataset_payload["name"], "alignment name"),
            parent_dataset_id=_text(dataset_payload["parent_dataset_id"], "alignment parent_dataset_id"),
            records=records,
            marker_regions=marker_regions,
            metadata=_metadata(dataset_payload.get("metadata"), "alignment metadata"),
        )
    elif dataset_model == "SequenceDataset":
        records = tuple(
            SequenceRecord(
                sequence_id=_text(record_payload["sequence_id"], "sequence_id"),
                sequence=_text(record_payload["sequence"], "sequence"),
                description=_optional_text(record_payload.get("description"), "description"),
                # source_reference is deliberately omitted from persistence.
                metadata=_metadata(record_payload.get("metadata"), "record metadata"),
            )
            for record_payload in (
                _mapping(item, "sequence record")
                for item in _sequence(dataset_payload.get("records"), "records")
            )
        )
        dataset = SequenceDataset(
            dataset_id=_text(dataset_payload["dataset_id"], "dataset_id"),
            name=_text(dataset_payload["name"], "dataset name"),
            source_type=_enum(SourceType, dataset_payload.get("source_type"), "source_type"),
            records=records,
            metadata=_metadata(dataset_payload.get("metadata"), "dataset metadata"),
        )
    else:
        raise ValueError(f"invalid dataset_model: {dataset_model!r}")
    derivation_value = payload.get("derivation_type")
    return ProjectDatasetEntry(
        dataset=dataset,
        display_name=_text(payload["display_name"], "display_name"),
        parent_dataset_id=_optional_text(payload.get("parent_dataset_id"), "parent_dataset_id"),
        derivation_type=(
            None
            if derivation_value is None
            else _enum(DerivationType, derivation_value, "derivation_type")
        ),
        metadata=_metadata(payload.get("metadata"), "dataset entry metadata"),
    )


def _deserialize_analysis_entry(payload: Mapping[str, Any]) -> ProjectAnalysisEntry:
    result_payload = _mapping(payload.get("analysis_result"), "analysis_result")
    result = AnalysisResult(
        result_id=_text(result_payload["result_id"], "result_id"),
        name=_text(result_payload["name"], "result name"),
        result_type=_enum(
            AnalysisResultType,
            result_payload.get("result_type"),
            "result_type",
        ),
        parent_dataset_id=_text(result_payload["parent_dataset_id"], "parent_dataset_id"),
        metadata=_metadata(result_payload.get("metadata"), "analysis result metadata"),
    )
    return ProjectAnalysisEntry(
        analysis_result=result,
        display_name=_text(payload["display_name"], "analysis display_name"),
        metadata=_metadata(payload.get("metadata"), "analysis entry metadata"),
    )


def _coerce_path(filepath: str | Path) -> Path:
    if not isinstance(filepath, (str, Path)):
        raise ProjectPersistenceError("filepath must be a string or Path")
    path = Path(filepath)
    if not str(path).strip() or path.name in ("", "."):
        raise ProjectPersistenceError("filepath must name a file")
    return path


def _json_value(value: object, context: str) -> object:
    """Return a JSON-compatible deep copy or reject unsupported metadata."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ProjectPersistenceError(f"{context} contains a non-finite float")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, nested_value in value.items():
            if not isinstance(key, str):
                raise ProjectPersistenceError(f"{context} contains a non-string metadata key")
            result[key] = _json_value(nested_value, f"{context}.{key}")
        return result
    if isinstance(value, (tuple, list)):
        return [_json_value(item, context) for item in value]
    raise ProjectPersistenceError(
        f"{context} contains a value that cannot be represented in JSON: {type(value).__name__}"
    )


def _mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be an object")
    return value


def _sequence(value: object, context: str) -> tuple[object, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{context} must be an array")
    return tuple(value)


def _metadata(value: object, context: str) -> Mapping[str, object]:
    if value is None:
        return {}
    mapping = _mapping(value, context)
    return _json_value(mapping, context)  # type: ignore[return-value]


def _text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _integer(value: object, context: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{context} must be an integer")
    return value


def _optional_text(value: object, context: str) -> str | None:
    if value is None:
        return None
    return _text(value, context)


def _enum(enum_type, value: object, context: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {context}: {value!r}") from error
