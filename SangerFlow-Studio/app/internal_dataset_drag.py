"""Small, internal-only drag payloads for Project Dataset workflow routing.

The payload deliberately carries identity only.  Sequence data, metadata, and
Project values stay in the normal model/controller path.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from PySide6.QtCore import QMimeData


PROJECT_DATASET_MIME_TYPE = "application/x-sangerflow-project-dataset+json"


class InternalDatasetDragError(ValueError):
    """Raised when an internal Dataset drag cannot be safely decoded."""


@dataclass(frozen=True)
class InternalDatasetDrag:
    project_id: str
    dataset_id: str
    dataset_type: str


def create_project_dataset_mime_data(
    *, project_id: str, dataset_id: str, dataset_type: str,
) -> QMimeData:
    """Create a minimal identity-only MIME payload for one Project Dataset."""

    payload = _validate_payload(
        {"project_id": project_id, "dataset_id": dataset_id, "dataset_type": dataset_type}
    )
    mime_data = QMimeData()
    mime_data.setData(
        PROJECT_DATASET_MIME_TYPE,
        json.dumps(payload.__dict__, separators=(",", ":")).encode("utf-8"),
    )
    return mime_data


def decode_project_dataset_drag(mime_data: QMimeData) -> InternalDatasetDrag:
    """Decode a Dataset drag without looking up or reconstructing data values."""

    if not mime_data.hasFormat(PROJECT_DATASET_MIME_TYPE):
        raise InternalDatasetDragError("This is not a SangerFlow Project Dataset drag.")
    try:
        raw = bytes(mime_data.data(PROJECT_DATASET_MIME_TYPE)).decode("utf-8")
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InternalDatasetDragError("The Project Dataset drag data is invalid.") from error
    return _validate_payload(value)


def _validate_payload(value: object) -> InternalDatasetDrag:
    if not isinstance(value, dict):
        raise InternalDatasetDragError("The Project Dataset drag data is invalid.")
    project_id = value.get("project_id")
    dataset_id = value.get("dataset_id")
    dataset_type = value.get("dataset_type")
    if not all(isinstance(item, str) and item.strip() for item in (project_id, dataset_id, dataset_type)):
        raise InternalDatasetDragError("The Project Dataset drag data is incomplete.")
    return InternalDatasetDrag(
        project_id=project_id,
        dataset_id=dataset_id,
        dataset_type=dataset_type,
    )
