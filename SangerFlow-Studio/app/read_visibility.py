"""Shared read visibility state for Studio chromatogram-oriented viewers."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ReadVisibilityManager(QObject):
    """Coordinate visible read IDs across viewers and quality docks."""

    visibility_changed = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._visible_ids_by_source: dict[str, tuple[str, ...]] = {}
        self._all_ids_by_source: dict[str, tuple[str, ...]] = {}

    def initialize_source(self, source_key: str, read_ids: tuple[str, ...]) -> None:
        if source_key not in self._all_ids_by_source:
            self._all_ids_by_source[source_key] = tuple(read_ids)
        if source_key not in self._visible_ids_by_source:
            self._visible_ids_by_source[source_key] = tuple(read_ids)

    def visible_ids(self, source_key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
        return self._visible_ids_by_source.get(source_key, default)

    def set_visible(self, source_key: str, read_id: str, visible: bool) -> None:
        all_ids = self._all_ids_by_source.get(source_key, ())
        visible_ids = list(self._visible_ids_by_source.get(source_key, all_ids))
        if visible and read_id not in visible_ids:
            visible_ids.append(read_id)
        elif not visible and read_id in visible_ids:
            visible_ids.remove(read_id)
        ordered = tuple(read_id for read_id in all_ids if read_id in visible_ids)
        self._visible_ids_by_source[source_key] = ordered
        self.visibility_changed.emit(source_key, ordered)

    def set_visible_ids(self, source_key: str, read_ids: tuple[str, ...]) -> None:
        all_ids = self._all_ids_by_source.get(source_key, read_ids)
        selected = set(read_ids)
        ordered = tuple(read_id for read_id in all_ids if read_id in selected)
        self._visible_ids_by_source[source_key] = ordered
        self.visibility_changed.emit(source_key, ordered)
