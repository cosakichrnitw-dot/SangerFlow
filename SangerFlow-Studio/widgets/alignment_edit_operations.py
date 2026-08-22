"""Typed, session-only operations shared by Studio sequence editors.

These operations intentionally do not serialize Project state.  They describe
pending edits to an immutable alignment and make Undo/Redo durable-ID based.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PendingEditTarget(Protocol):
    def _apply_base_changes(self, changes: object, *, use_new: bool = True) -> None: ...
    def _set_deleted_row_ids(self, row_ids: frozenset[str]) -> None: ...
    def _set_excluded_column_ids(self, column_ids: frozenset[int]) -> None: ...
    def _set_row_label(self, record_id: str, label: str) -> None: ...
    def _apply_delete_columns(self, column_ids: tuple[int, ...]) -> None: ...
    def _revert_delete_columns(self, column_ids: tuple[int, ...], removed: object) -> None: ...


@dataclass(frozen=True)
class BaseEditOperation:
    changes: tuple[tuple[str, int, str, str], ...]

    @property
    def kind(self) -> str:
        return "base_edit"

    @property
    def description(self) -> str:
        return f"Edited {len(self.changes)} base(s)"

    def apply(self, target: PendingEditTarget) -> None:
        target._apply_base_changes(self.changes, use_new=True)

    def revert(self, target: PendingEditTarget) -> None:
        target._apply_base_changes(self.changes, use_new=False)


@dataclass(frozen=True)
class BulkBaseEditOperation(BaseEditOperation):
    @property
    def kind(self) -> str:
        return "bulk_base_edit"


@dataclass(frozen=True)
class DeleteRowsOperation:
    before: frozenset[str]
    after: frozenset[str]

    @property
    def kind(self) -> str:
        return "delete_rows"

    @property
    def description(self) -> str:
        return f"Deleted {len(self.after - self.before)} row(s)"

    def apply(self, target: PendingEditTarget) -> None:
        target._set_deleted_row_ids(self.after)

    def revert(self, target: PendingEditTarget) -> None:
        target._set_deleted_row_ids(self.before)


@dataclass(frozen=True)
class DeleteColumnsOperation:
    """Delete stable original-column IDs, not fragile current indices."""

    column_ids: tuple[int, ...]
    removed: object

    @property
    def kind(self) -> str:
        return "delete_columns"

    @property
    def description(self) -> str:
        return f"Deleted {len(self.column_ids)} column(s)"

    def apply(self, target: PendingEditTarget) -> None:
        target._apply_delete_columns(self.column_ids)

    def revert(self, target: PendingEditTarget) -> None:
        target._revert_delete_columns(self.column_ids, self.removed)


@dataclass(frozen=True)
class ExcludeColumnsOperation:
    before: frozenset[int]
    after: frozenset[int]

    @property
    def kind(self) -> str:
        return "exclude_columns"

    @property
    def description(self) -> str:
        return f"Updated exclusion for {len(self.before ^ self.after)} column(s)"

    def apply(self, target: PendingEditTarget) -> None:
        target._set_excluded_column_ids(self.after)

    def revert(self, target: PendingEditTarget) -> None:
        target._set_excluded_column_ids(self.before)


@dataclass(frozen=True)
class RenameOperation:
    record_id: str
    before: str
    after: str

    @property
    def kind(self) -> str:
        return "rename"

    @property
    def description(self) -> str:
        return f"Renamed {self.before} to {self.after}"

    def apply(self, target: PendingEditTarget) -> None:
        target._set_row_label(self.record_id, self.after)

    def revert(self, target: PendingEditTarget) -> None:
        target._set_row_label(self.record_id, self.before)


@dataclass(frozen=True)
class PasteBlockOperation(BaseEditOperation):
    """A validated, substitution-only paste represented as base changes."""

    @property
    def kind(self) -> str:
        return "paste_block"
