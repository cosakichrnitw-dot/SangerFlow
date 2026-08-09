"""Base class for typed SangerFlow-Studio workspace viewers."""

from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class BaseViewer(QWidget):
    """Common GUI contract for future viewer tabs."""

    selection_changed = Signal(object)
    status_message_changed = Signal(str)
    export_requested = Signal(object)
    open_related_requested = Signal(object)

    def __init__(
        self,
        *,
        viewer_id: str | None = None,
        viewer_title: str = "Viewer",
        viewer_kind: str = "viewer",
        source_object_id: str | None = None,
    ) -> None:
        super().__init__()
        self._viewer_id = viewer_id or f"{viewer_kind}-{uuid4().hex}"
        self._viewer_title = viewer_title
        self._viewer_kind = viewer_kind
        self._source_object_id = source_object_id
        self._is_dirty = False

    @property
    def viewer_id(self) -> str:
        return self._viewer_id

    @property
    def viewer_title(self) -> str:
        return self._viewer_title

    @property
    def viewer_kind(self) -> str:
        return self._viewer_kind

    @property
    def source_object_id(self) -> str | None:
        return self._source_object_id

    @property
    def is_dirty(self) -> bool:
        return self._is_dirty

    @property
    def supported_actions(self) -> tuple[str, ...]:
        return ()

    def open_dataset(self, dataset: object) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not open datasets")

    def open_result(self, result: object) -> None:
        raise NotImplementedError(f"{type(self).__name__} does not open results")

    def refresh(self) -> None:
        return

    def export(self, target: object | None = None) -> None:
        self.export_requested.emit(target)

    def save_state(self) -> dict[str, object]:
        return {
            "viewer_id": self.viewer_id,
            "viewer_title": self.viewer_title,
            "viewer_kind": self.viewer_kind,
            "source_object_id": self.source_object_id,
        }

    def close_viewer(self) -> bool:
        return True
